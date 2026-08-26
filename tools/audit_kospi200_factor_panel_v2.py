#!/usr/bin/env python3
"""v2 일별 펀더멘털 Factor 패널의 경계·identity·스키마를 감사한다."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import pandas as pd

from kospi200_fundamental import FACTOR_IDS


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_identity(path: Path) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("model_eligible") == "true":
                result.add((str(row["ticker"]).zfill(6), str(row["membership_name"])))
    return result


def audit(panel_path: Path, manifest_path: Path, identity_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if sha256(panel_path) != manifest.get("output_sha256"):
        raise ValueError("Factor panel hash가 manifest와 다릅니다.")
    frame = pd.read_csv(panel_path, dtype={"ticker": str})
    required = {"date", "ticker", "membership_name", "rank_eligible", *FACTOR_IDS}
    for factor in FACTOR_IDS:
        required.update({f"{factor}__percentile", f"{factor}__robust_z"})
    missing = sorted(required - set(frame.columns))
    dates = pd.to_datetime(frame["date"], errors="raise")
    confirmed = load_identity(identity_path)
    identity_violations = int(sum((str(row.ticker).zfill(6), str(row.membership_name)) not in confirmed for row in frame.itertuples()))
    duplicate_rows = int(frame.duplicated(["date", "ticker"]).sum())
    post_2023_rows = int((dates > pd.Timestamp("2023-12-31")).sum())
    daily_counts = frame.groupby("date")["ticker"].nunique()
    daily_rank_eligible = frame.loc[frame["rank_eligible"].astype(str).str.casefold().isin({"true", "1"})].groupby("date")["ticker"].nunique()
    failures = {
        "missing_columns": missing, "identity_violations": identity_violations,
        "duplicate_date_ticker_rows": duplicate_rows, "post_2023_rows": post_2023_rows,
        "manifest_row_mismatch": int(len(frame) != int(manifest.get("rows", -1))),
    }
    passed = not missing and not any(value for key, value in failures.items() if key != "missing_columns")
    return {
        "schema_version": "kospi200-fundamental-factor-panel-audit-v1",
        "status": "PASS_FACTOR_PANEL_MODEL_NOT_STARTED" if passed else "FAIL_FACTOR_PANEL_AUDIT",
        "rows": len(frame), "tickers": int(frame["ticker"].nunique()),
        "min_date": dates.min().date().isoformat(), "max_date": dates.max().date().isoformat(),
        "daily_ticker_count": {"min": int(daily_counts.min()), "median": float(daily_counts.median()), "max": int(daily_counts.max())},
        "daily_rank_eligible_count": {"min": int(daily_rank_eligible.min()), "median": float(daily_rank_eligible.median()), "max": int(daily_rank_eligible.max())},
        "dates_with_at_least_30_tickers": int((daily_counts >= 30).sum()), "dates_total": int(len(daily_counts)),
        "factor_coverage": {factor: float(frame[factor].notna().mean()) for factor in FACTOR_IDS},
        "failures": failures, "panel_sha256": sha256(panel_path), "identity_sha256": sha256(identity_path),
        "protected_oos_accessed": False, "model_started": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KOSPI 200 fundamental factor panel audit")
    parser.add_argument("--panel-root", type=Path, default=Path("data/processed/v2_kospi200_fundamental_factor_panel"))
    parser.add_argument("--identity", type=Path, default=Path("data/processed/v2_kospi200_identity_frozen/identity_spells.csv"))
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/v2_phase1_factor_panel_audit"))
    args = parser.parse_args(argv)
    result = audit(args.panel_root / "fundamental_factor_panel.csv.gz", args.panel_root / "manifest.json", args.identity)
    args.output_root.mkdir(parents=True, exist_ok=True)
    target = args.output_root / "factor_panel_audit.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "rows": result["rows"], "tickers": result["tickers"], "output": str(target)}, ensure_ascii=False))
    return 0 if result["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
