from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import tempfile
from datetime import date
from pathlib import Path
from typing import TextIO


PARTITION_ROLE = "phase4_train_validation"
SOURCE_ROLE = "development"
MAXIMUM_DATE = date(2021, 12, 31)
SOURCE_MAXIMUM_DATE = "2023-12-31"
REQUIRED_FILES = {
    "corporate_actions.csv.gz": "feature_boundary_date",
    "feature_price_panel.csv.gz": "date",
    "full_history_ohlcv.csv.gz": "date",
    "index_ohlcv.csv.gz": "date",
}
MANIFEST_COLUMNS = ("file", "bytes", "sha256", "date_column", "min_date", "max_date", "rows")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _forbidden_path(path: Path) -> bool:
    return any(part.lower() == "sealed" or "final_oos" in part.lower() for part in path.resolve().parts)


def _read_source_manifest(source_root: Path) -> tuple[dict[str, dict[str, str]], str]:
    manifest_path = source_root / "manifest.csv"
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_file = {str(row.get("file", "")): row for row in rows}
    missing = sorted(set(REQUIRED_FILES) - set(by_file))
    if missing:
        raise ValueError(f"원본 development manifest 필수 파일 누락: {missing}")
    if len(by_file) != len(rows):
        raise ValueError("원본 development manifest에 중복 파일이 있습니다")

    selected: dict[str, dict[str, str]] = {}
    for name in sorted(REQUIRED_FILES):
        path = source_root / name
        row = by_file[name]
        expected_bytes = int(row["bytes"])
        expected_hash = str(row["sha256"])
        if path.stat().st_size != expected_bytes:
            raise ValueError(f"원본 development 파일 크기 불일치: {name}")
        if sha256_file(path) != expected_hash:
            raise ValueError(f"원본 development 파일 hash 불일치: {name}")
        selected[name] = {"bytes": str(expected_bytes), "sha256": expected_hash}
    return selected, sha256_file(manifest_path)


def _open_deterministic_gzip(path: Path) -> tuple[TextIO, TextIO]:
    raw = path.open("wb")
    compressed = gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0)
    text = io.TextIOWrapper(compressed, encoding="utf-8", newline="")
    return raw, text


def _copy_through_date(source: Path, destination: Path, date_column: str, maximum_date: date) -> dict[str, object]:
    minimum_written: date | None = None
    maximum_written: date | None = None
    written = 0
    raw, output = _open_deterministic_gzip(destination)
    try:
        with gzip.open(source, "rt", encoding="utf-8-sig", newline="") as input_handle:
            reader = csv.DictReader(input_handle)
            if reader.fieldnames is None or date_column not in reader.fieldnames:
                raise ValueError(f"{source.name} 날짜 열 누락: {date_column}")
            writer = csv.DictWriter(output, fieldnames=reader.fieldnames, lineterminator="\n")
            writer.writeheader()
            for row in reader:
                raw_date = str(row.get(date_column, "")).strip()
                try:
                    row_date = date.fromisoformat(raw_date[:10])
                except ValueError as exc:
                    raise ValueError(f"{source.name} 유효하지 않은 날짜: {raw_date!r}") from exc
                if row_date > maximum_date:
                    continue
                writer.writerow(row)
                written += 1
                minimum_written = row_date if minimum_written is None else min(minimum_written, row_date)
                maximum_written = row_date if maximum_written is None else max(maximum_written, row_date)
    finally:
        output.close()
        raw.close()
    return {
        "file": destination.name,
        "bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
        "date_column": date_column,
        "min_date": minimum_written.isoformat() if minimum_written else "",
        "max_date": maximum_written.isoformat() if maximum_written else "",
        "rows": written,
    }


def _data_hash(rows: list[dict[str, object]]) -> str:
    material = "\n".join(f"{row['file']}:{row['sha256']}" for row in sorted(rows, key=lambda row: str(row["file"])))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def build_phase4_partition(
    source_root: Path,
    output_root: Path,
    *,
    maximum_date: date = MAXIMUM_DATE,
) -> dict[str, object]:
    source_root = source_root.resolve()
    output_root = output_root.resolve()
    if _forbidden_path(source_root) or _forbidden_path(output_root):
        raise PermissionError("Phase 4 물리 파티션 생성은 Final OOS 또는 sealed 경로를 사용할 수 없습니다")
    if maximum_date != MAXIMUM_DATE:
        raise ValueError("Phase 4 Train/Validation 물리 경계는 2021-12-31로 동결돼 있습니다")
    if output_root.exists():
        raise FileExistsError(f"출력 파티션이 이미 존재합니다: {output_root}")

    source_partition_path = source_root / "partition.json"
    source_partition = json.loads(source_partition_path.read_text(encoding="utf-8"))
    if source_partition.get("role") != SOURCE_ROLE or source_partition.get("max_date") != SOURCE_MAXIMUM_DATE:
        raise ValueError("등록된 development 원본 파티션 역할 또는 최대일이 다릅니다")
    source_files, source_manifest_hash = _read_source_manifest(source_root)

    output_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{output_root.name}-", dir=output_root.parent) as temporary:
        staging = Path(temporary)
        manifest_rows = [
            _copy_through_date(source_root / name, staging / name, date_column, maximum_date)
            for name, date_column in sorted(REQUIRED_FILES.items())
        ]
        if any(not row["rows"] or row["max_date"] > maximum_date.isoformat() for row in manifest_rows):
            raise ValueError("Phase 4 물리 파티션에 빈 파일 또는 허용일 이후 행이 있습니다")

        with (staging / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(manifest_rows)

        partition = {
            "version": "phase4-train-validation-partition-v1",
            "role": PARTITION_ROLE,
            "max_date": maximum_date.isoformat(),
            "created_by": "kospi100_data.phase4_partition",
            "builder_sha256": sha256_file(Path(__file__)),
            "source": {
                "role": SOURCE_ROLE,
                "max_date": SOURCE_MAXIMUM_DATE,
                "partition_sha256": sha256_file(source_partition_path),
                "manifest_sha256": source_manifest_hash,
                "files": source_files,
            },
            "selection": {
                "method": "streaming_date_cutoff",
                "maximum_included_date": maximum_date.isoformat(),
                "date_columns": REQUIRED_FILES,
                "excluded_rows_retained_or_aggregated": False,
            },
            "data_hash": _data_hash(manifest_rows),
        }
        (staging / "partition.json").write_text(
            json.dumps(partition, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staging.replace(output_root)

    return {
        "status": "PASS",
        "output_root": output_root.as_posix(),
        "maximum_date": maximum_date.isoformat(),
        "data_hash": partition["data_hash"],
        "files": manifest_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 4 Train/Validation 전용 물리 파티션 생성")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = build_phase4_partition(args.source_root, args.output_root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
