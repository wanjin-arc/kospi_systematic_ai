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


FILES = {
    "feature_price_panel.csv.gz": "date",
    "full_history_ohlcv.csv.gz": "date",
    "index_ohlcv.csv.gz": "date",
    "corporate_actions.csv.gz": "feature_boundary_date",
    "removal_orders.csv.gz": "execution_date",
}
SOURCE_ROLE = "phase5_train_validation"
OUTPUT_ROLE = "phase4b_train_internal"
SOURCE_MAXIMUM = date(2021, 12, 31)
OUTPUT_MAXIMUM = date(2018, 12, 31)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["file"]: row for row in csv.DictReader(handle)}


def _data_hash(rows: list[dict[str, object]]) -> str:
    material = "\n".join(
        f"{row['file']}:{row['sha256']}" for row in sorted(rows, key=lambda item: str(item["file"]))
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _filter_gzip_csv(
    source: Path,
    target: Path,
    date_column: str,
) -> tuple[dict[str, object], dict[str, object]]:
    source_rows = 0
    included_rows = 0
    source_min: date | None = None
    source_max: date | None = None
    included_min: date | None = None
    included_max: date | None = None
    with gzip.open(source, "rt", encoding="utf-8-sig", newline="") as input_handle:
        reader = csv.DictReader(input_handle)
        if not reader.fieldnames or date_column not in reader.fieldnames:
            raise ValueError(f"날짜 열 누락: {source.name} {date_column}")
        with target.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as output_handle:
                    writer = csv.DictWriter(output_handle, fieldnames=reader.fieldnames, lineterminator="\n")
                    writer.writeheader()
                    for row in reader:
                        value = date.fromisoformat(row[date_column][:10])
                        source_rows += 1
                        source_min = value if source_min is None else min(source_min, value)
                        source_max = value if source_max is None else max(source_max, value)
                        if value > OUTPUT_MAXIMUM:
                            continue
                        writer.writerow(row)
                        included_rows += 1
                        included_min = value if included_min is None else min(included_min, value)
                        included_max = value if included_max is None else max(included_max, value)
    if not included_rows or included_min is None or included_max is None:
        raise ValueError(f"2018년 이하 파티션 행이 없습니다: {source.name}")
    manifest_row = {
        "file": source.name,
        "bytes": target.stat().st_size,
        "sha256": _sha256(target),
        "date_column": date_column,
        "min_date": included_min.isoformat(),
        "max_date": included_max.isoformat(),
        "rows": included_rows,
    }
    audit = {
        "file": source.name,
        "source_rows_scanned": source_rows,
        "source_min_date_observed": source_min.isoformat() if source_min else None,
        "source_max_date_observed": source_max.isoformat() if source_max else None,
        "output_rows": included_rows,
        "output_min_date": included_min.isoformat(),
        "output_max_date": included_max.isoformat(),
        "rows_excluded_after_2018": source_rows - included_rows,
    }
    return manifest_row, audit


def build_phase4b_partition(source_root: Path, output_root: Path) -> dict[str, object]:
    source_root = source_root.resolve()
    output_root = output_root.resolve()
    lowered = {part.lower() for part in source_root.parts}
    if "sealed" in lowered or "final_oos_v24" in lowered:
        raise PermissionError("Phase 4B 파티션은 봉인 경로에서 만들 수 없습니다")
    source_partition = json.loads((source_root / "partition.json").read_text(encoding="utf-8"))
    if source_partition.get("role") != SOURCE_ROLE:
        raise PermissionError("Phase 4B 원천은 검증된 Phase 5 Selection 파티션이어야 합니다")
    if source_partition.get("max_date") != SOURCE_MAXIMUM.isoformat():
        raise PermissionError("Phase 4B 원천 파티션 날짜 경계가 다릅니다")
    source_manifest = _manifest(source_root / "manifest.csv")
    if set(source_manifest) != set(FILES):
        raise ValueError("Phase 4B 원천 manifest 파일 집합이 다릅니다")
    for name, date_column in FILES.items():
        row = source_manifest[name]
        if row["date_column"] != date_column:
            raise ValueError(f"원천 날짜 열 불일치: {name}")
        if date.fromisoformat(row["max_date"]) > SOURCE_MAXIMUM:
            raise PermissionError(f"원천 manifest가 허용 날짜를 넘습니다: {name}")
        path = source_root / name
        if path.stat().st_size != int(row["bytes"]) or _sha256(path) != row["sha256"]:
            raise ValueError(f"원천 파일 무결성 실패: {name}")

    if output_root.exists():
        raise FileExistsError(f"기존 Phase 4B 파티션을 덮어쓰지 않습니다: {output_root}")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phase4b_partition_", dir=output_root.parent) as temporary:
        staging = Path(temporary) / output_root.name
        staging.mkdir()
        rows: list[dict[str, object]] = []
        audits: list[dict[str, object]] = []
        for name, date_column in FILES.items():
            row, audit = _filter_gzip_csv(source_root / name, staging / name, date_column)
            rows.append(row)
            audits.append(audit)
        with (staging / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["file", "bytes", "sha256", "date_column", "min_date", "max_date", "rows"],
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(sorted(rows, key=lambda item: str(item["file"])))
        partition = {
            "version": "phase4b-train-internal-partition-v1",
            "role": OUTPUT_ROLE,
            "min_date": min(str(row["min_date"]) for row in rows),
            "max_date": OUTPUT_MAXIMUM.isoformat(),
            "created_at": "2026-08-23T00:00:00+09:00",
            "data_hash": _data_hash(rows),
            "source": {
                "partition_role": SOURCE_ROLE,
                "partition_data_hash": source_partition["data_hash"],
                "source_maximum_date": SOURCE_MAXIMUM.isoformat(),
            },
            "research_boundary": {
                "maximum_included_date": OUTPUT_MAXIMUM.isoformat(),
                "post_2018_rows_in_output": 0,
                "development_test_input_loaded": False,
                "final_oos_accessed": False,
            },
            "selection": {
                "post_2021_rows_loaded": 0,
                "post_2018_rows_in_output": 0,
                "development_test_partition_created": False,
            },
            "builder_audit": audits,
        }
        with (staging / "partition.json").open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(partition, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        staging.replace(output_root)
    return {
        "status": "PASS",
        "output_root": output_root.as_posix(),
        "data_hash": partition["data_hash"],
        "maximum_date": OUTPUT_MAXIMUM.isoformat(),
        "files": rows,
        "builder_audit": audits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 4B 2018년 이하 물리 파티션 생성")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = build_phase4b_partition(args.source_root, args.output_root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
