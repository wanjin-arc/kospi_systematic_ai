#!/usr/bin/env python3
"""Merge PIT KRX sector classifications into the fundamental factor panel.

The original factor panel is preserved.  This builder writes a new panel that
contains both the existing market-wide transforms and sector-relative
percentile/robust-z transforms, with a fail-closed key/date audit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from kospi200_fundamental import FACTOR_IDS, cross_sectional_transform


MAX_DATE = pd.Timestamp("2023-12-31")


def guard_path(path: Path) -> None:
    parts = {part.casefold() for part in path.resolve().parts}
    if "sealed" in parts or "final_oos_v24" in parts:
        raise ValueError("Final OOS 경로는 병합 입력·출력으로 사용할 수 없습니다.")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} 필수 열 누락: {missing}")


def build(factor_path: Path, sector_path: Path, output_root: Path) -> dict[str, object]:
    for path in (factor_path, sector_path, output_root):
        guard_path(path)
    if not factor_path.exists() or not sector_path.exists():
        raise FileNotFoundError("factor-panel 또는 sector_daily 입력이 없습니다.")

    factors = pd.read_csv(factor_path, compression="gzip", dtype={"ticker": str})
    sectors = pd.read_csv(sector_path, compression="gzip", dtype={"ticker": str})
    _require_columns(factors, {"date", "ticker", *FACTOR_IDS}, "factor-panel")
    _require_columns(sectors, {"date", "ticker", "sector", "sector_code", "sector_code_source"}, "sector")

    factors["date"] = pd.to_datetime(factors["date"], errors="raise").dt.normalize()
    sectors["date"] = pd.to_datetime(sectors["date"], errors="raise").dt.normalize()
    if factors["date"].max() > MAX_DATE or sectors["date"].max() > MAX_DATE:
        raise ValueError("2023-12-31 이후 데이터는 병합할 수 없습니다.")
    key = ["date", "ticker"]
    if factors.duplicated(key).any():
        raise ValueError("factor-panel에 date,ticker 중복이 있습니다.")
    if sectors.duplicated(key).any():
        raise ValueError("sector_daily에 date,ticker 중복이 있습니다.")

    sector_columns = sectors[key + ["sector", "sector_code", "sector_code_source"]]
    merged = factors.merge(sector_columns, on=key, how="left", validate="one_to_one", indicator=True)
    missing = merged["_merge"].ne("both")
    if missing.any():
        sample = merged.loc[missing, key].head(5).to_dict("records")
        raise ValueError(f"factor-panel의 섹터 매칭 누락 {int(missing.sum())}행; 예시={sample}")
    merged = merged.drop(columns="_merge")

    # Keep the pre-existing market-wide transforms under explicit names.
    for factor in FACTOR_IDS:
        for suffix in ("percentile", "robust_z"):
            old = f"{factor}__{suffix}"
            if old in merged:
                merged[f"{factor}__market_{suffix}"] = merged.pop(old)

    transformed = cross_sectional_transform(merged, group_column="sector")
    # The transform creates factor__percentile and factor__robust_z using the
    # PIT sector grouping (with the library's >=5-name fallback).
    transformed = transformed.sort_values(key, kind="mergesort").reset_index(drop=True)
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / "fundamental_sector_factor_panel.csv.gz"
    transformed.to_csv(output_path, index=False, compression={"method": "gzip", "mtime": 0}, lineterminator="\n")

    audit = {
        "schema_version": "kospi200-fundamental-sector-panel-v1",
        "factor_source": str(factor_path),
        "factor_source_sha256": sha256(factor_path),
        "sector_source": str(sector_path),
        "sector_source_sha256": sha256(sector_path),
        "output": str(output_path),
        "output_sha256": sha256(output_path),
        "rows": int(len(transformed)),
        "tickers": int(transformed["ticker"].nunique()),
        "min_date": transformed["date"].min().date().isoformat(),
        "max_date": transformed["date"].max().date().isoformat(),
        "sector_count": int(transformed["sector"].nunique()),
        "sector_code_sources": {str(k): int(v) for k, v in transformed["sector_code_source"].value_counts(dropna=False).items()},
        "sector_match_rows": int(len(transformed)),
        "sector_missing_rows": 0,
        "market_transforms_preserved": True,
        "sector_transforms_added": [],
        "final_oos_accessed": False,
    }
    # Expand the transform audit without relying on a non-JSON set.
    audit["sector_transforms_added"] = [f"{factor}__{suffix}" for factor in FACTOR_IDS for suffix in ("percentile", "robust_z")]
    (output_root / "manifest.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--factor-panel", type=Path, required=True)
    parser.add_argument("--sector-daily", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    result = build(args.factor_panel, args.sector_daily, args.output_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
