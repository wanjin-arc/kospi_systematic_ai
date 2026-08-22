from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import shutil
import tempfile
from datetime import date
from pathlib import Path


COPIED_FILES = {
    "feature_price_panel.csv.gz": "date",
    "full_history_ohlcv.csv.gz": "date",
    "index_ohlcv.csv.gz": "date",
    "corporate_actions.csv.gz": "feature_boundary_date",
}
CONTROL_FILE = "removal_orders.csv.gz"
MAXIMUM_DATE = date(2021, 12, 31)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _data_hash(rows: list[dict[str, object]]) -> str:
    material = "\n".join(f"{row['file']}:{row['sha256']}" for row in sorted(rows, key=lambda x: str(x["file"])))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_manifest(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["file"]: row for row in csv.DictReader(handle)}


def _control_rows(paths: tuple[Path, ...]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("reason") != "UNIVERSE_REMOVAL_EXIT":
                    continue
                execution = date.fromisoformat(row["execute_date"])
                if execution > MAXIMUM_DATE:
                    raise PermissionError("Selection 제어표에 2022년 이후 행이 포함되었습니다")
                rows.append(
                    {
                        "order_id": row["order_id"],
                        "membership_spell_id": row["order_id"].rsplit(":", 2)[-2] + ":" + row["order_id"].rsplit(":", 1)[-1],
                        "signal_date": row["signal_date"],
                        "execution_date": row["execute_date"],
                        "execution_security_id": row["security_id"],
                        "resolution_type": (
                            "SUCCESSOR_TRANSITION_REQUIRES_RESOLVED_POSITION"
                            if row["security_id"].startswith("REMOVAL_SUCCESSOR:")
                            else "DIRECT_OLD_SECURITY_FIRST_TRADABLE_OPEN"
                        ),
                    }
                )
    unique = {(row["order_id"], row["execution_date"]): row for row in rows}
    return sorted(unique.values(), key=lambda row: (row["execution_date"], row["order_id"]))


def _write_gzip_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "order_id",
        "membership_spell_id",
        "signal_date",
        "execution_date",
        "execution_security_id",
        "resolution_type",
    ]
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text_handle:
                writer = csv.DictWriter(text_handle, fieldnames=fieldnames, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)


def build_phase5_selection_partition(
    phase4_root: Path,
    phase3_train_orders: Path,
    phase3_validation_orders: Path,
    output_root: Path,
) -> dict[str, object]:
    phase4_root = phase4_root.resolve()
    output_root = output_root.resolve()
    source_partition = _read_json(phase4_root / "partition.json")
    if source_partition.get("role") != "phase4_train_validation":
        raise PermissionError("Phase 5 Selection 파티션은 검증된 Phase 4 물리 파티션에서만 파생할 수 있습니다")
    if source_partition.get("max_date") != MAXIMUM_DATE.isoformat():
        raise PermissionError("Phase 4 원천 파티션이 2021년 경계를 넘습니다")
    source_manifest = _read_manifest(phase4_root / "manifest.csv")
    if set(source_manifest) != set(COPIED_FILES):
        raise ValueError("Phase 4 원천 manifest 파일 집합이 예상과 다릅니다")
    for name, row in source_manifest.items():
        path = phase4_root / name
        if _sha256(path) != row["sha256"]:
            raise ValueError(f"Phase 4 원천 hash 불일치: {name}")
        if date.fromisoformat(row["max_date"]) > MAXIMUM_DATE:
            raise PermissionError(f"Phase 4 원천 날짜 경계 위반: {name}")

    control_sources = (phase3_train_orders.resolve(), phase3_validation_orders.resolve())
    controls = _control_rows(control_sources)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    if output_root.exists():
        raise FileExistsError(f"기존 파티션을 덮어쓰지 않습니다: {output_root}")
    with tempfile.TemporaryDirectory(prefix="phase5_partition_", dir=output_root.parent) as temporary:
        staging = Path(temporary) / output_root.name
        staging.mkdir()
        manifest_rows: list[dict[str, object]] = []
        for name, date_column in COPIED_FILES.items():
            source = phase4_root / name
            target = staging / name
            shutil.copyfile(source, target)
            row = source_manifest[name]
            manifest_rows.append(
                {
                    "file": name,
                    "bytes": target.stat().st_size,
                    "sha256": _sha256(target),
                    "date_column": date_column,
                    "min_date": row["min_date"],
                    "max_date": row["max_date"],
                    "rows": int(row["rows"]),
                }
            )
        control_target = staging / CONTROL_FILE
        _write_gzip_csv(control_target, controls)
        control_dates = [date.fromisoformat(row["execution_date"]) for row in controls]
        manifest_rows.append(
            {
                "file": CONTROL_FILE,
                "bytes": control_target.stat().st_size,
                "sha256": _sha256(control_target),
                "date_column": "execution_date",
                "min_date": min(control_dates).isoformat(),
                "max_date": max(control_dates).isoformat(),
                "rows": len(controls),
            }
        )
        with (staging / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["file", "bytes", "sha256", "date_column", "min_date", "max_date", "rows"],
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(sorted(manifest_rows, key=lambda row: str(row["file"])))
        partition = {
            "version": "phase5-selection-partition-v1",
            "role": "phase5_train_validation",
            "min_date": min(str(row["min_date"]) for row in manifest_rows),
            "max_date": MAXIMUM_DATE.isoformat(),
            "created_at": "2026-08-22T00:00:00+09:00",
            "source": {
                "partition_role": source_partition["role"],
                "partition_data_hash": source_partition["data_hash"],
                "control_artifacts": [
                    {"path": path.as_posix(), "sha256": _sha256(path)} for path in control_sources
                ],
            },
            "selection": {
                "maximum_included_date": MAXIMUM_DATE.isoformat(),
                "post_2021_rows_loaded": 0,
                "development_test_partition_created": False,
            },
            "data_hash": _data_hash(manifest_rows),
        }
        with (staging / "partition.json").open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(partition, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        staging.replace(output_root)
    return {
        "status": "PASS",
        "output_root": output_root.as_posix(),
        "data_hash": partition["data_hash"],
        "maximum_date": MAXIMUM_DATE.isoformat(),
        "files": manifest_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 5 Train/Validation 물리 파티션 생성")
    parser.add_argument("--phase4-root", type=Path, required=True)
    parser.add_argument("--phase3-train-orders", type=Path, required=True)
    parser.add_argument("--phase3-validation-orders", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = build_phase5_selection_partition(
        args.phase4_root,
        args.phase3_train_orders,
        args.phase3_validation_orders,
        args.output_root,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
