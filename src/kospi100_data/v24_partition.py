from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
from datetime import date
from pathlib import Path

import pandas as pd

from .v24_audit import sha256_file


FINAL_OOS_START = date(2024, 1, 1)
FINAL_OOS_END = date(2025, 12, 31)


TABLES = {
    "membership_daily": ("core/kospi100_membership_daily_v24.csv", "date"),
    "full_history_ohlcv": ("core/kospi100_174_full_history_ohlcv_v24.csv", "date"),
    "feature_price_panel": ("core/kospi100_feature_price_panel_v24.csv", "date"),
    "index_ohlcv": ("core/kospi100_index_ohlcv_v24.csv", "date"),
    "corporate_actions": ("core/kospi100_corporate_action_phase1_production_v24.csv", "feature_boundary_date"),
    "removal_execution": ("core/kospi100_membership_removal_execution_v24.csv", "execution_date"),
}


def _write_deterministic_gzip(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                frame.to_csv(text, index=False, lineterminator="\n")


def _write_manifest(directory: Path, metadata: dict[str, object]) -> None:
    rows = []
    for path in sorted(directory.glob("*.csv.gz")):
        rows.append({"file": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    manifest = directory / "manifest.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file", "bytes", "sha256"])
        writer.writeheader()
        writer.writerows(rows)
    (directory / "partition.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_partitions(package_root: Path, development_root: Path, sealed_root: Path) -> dict[str, object]:
    counts: dict[str, dict[str, int]] = {}
    for logical_name, (relative_path, date_column) in TABLES.items():
        frame = pd.read_csv(package_root / relative_path, encoding="utf-8-sig", low_memory=False)
        parsed = pd.to_datetime(frame[date_column], errors="coerce")
        if parsed.isna().any():
            raise ValueError(f"{logical_name}.{date_column} contains {int(parsed.isna().sum())} invalid dates")
        dev = frame.loc[parsed.dt.date < FINAL_OOS_START].copy()
        sealed = frame.loc[parsed.dt.date.between(FINAL_OOS_START, FINAL_OOS_END)].copy()
        _write_deterministic_gzip(dev, development_root / f"{logical_name}.csv.gz")
        _write_deterministic_gzip(sealed, sealed_root / f"{logical_name}.csv.gz")
        counts[logical_name] = {"source": len(frame), "development": len(dev), "final_oos": len(sealed)}
        if len(dev) + len(sealed) != len(frame):
            raise ValueError(f"{logical_name} has rows outside the frozen development/OOS bounds")

    common = {"package": "phase1-final-v24", "created_by": "kospi100_data.v24_partition", "counts": counts}
    _write_manifest(development_root, {**common, "role": "development", "max_date": "2023-12-31"})
    _write_manifest(
        sealed_root,
        {
            **common,
            "role": "sealed_final_oos",
            "min_date": FINAL_OOS_START.isoformat(),
            "max_date": FINAL_OOS_END.isoformat(),
            "access_policy": "Phase 8 frozen-release evaluation only",
        },
    )
    return {"status": "PASS", "counts": counts}


def main() -> int:
    parser = argparse.ArgumentParser(description="Create deterministic development and sealed final-OOS partitions from v24")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--development-root", type=Path, required=True)
    parser.add_argument("--sealed-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_partitions(args.root, args.development_root, args.sealed_root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
