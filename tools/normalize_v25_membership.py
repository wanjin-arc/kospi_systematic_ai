#!/usr/bin/env python3
"""Create a separate PIT-membership candidate using official KRX repairs.

The source membership file is never modified.  On the 26 audited dates the
official KRX [11006] response replaces the external snapshot; its count is
retained (99) and no missing member is imputed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ["date", "security_id", "ticker", "name", "membership_spell_id",
          "is_member", "eligible_new_entry", "tradable", "source", "official_count"]

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--membership-source", type=Path, required=True)
    p.add_argument("--repair-root", type=Path, required=True)
    p.add_argument("--output-root", type=Path, required=True)
    args = p.parse_args(argv)
    source_rows = read_csv(args.membership_source)
    repair_path = args.repair_root / "membership_repairs.csv"
    repair_rows = read_csv(repair_path)
    repair_dates = {r["date"] for r in repair_rows}
    by_date: dict[str, list[dict[str, str]]] = {}
    for r in repair_rows:
        by_date.setdefault(r["date"], []).append(r)
    normalized: list[dict[str, str]] = []
    for row in source_rows:
        if row.get("date") in repair_dates:
            continue
        normalized.append({field: row.get(field, "") for field in FIELDS})
    for day in sorted(by_date):
        for r in sorted(by_date[day], key=lambda x: x["ticker"]):
            ticker = str(r["ticker"]).zfill(6)
            normalized.append({
                "date": day, "security_id": f"KRX_COMMON:{ticker}", "ticker": ticker,
                "name": r.get("name", ""),
                "membership_spell_id": f"{ticker}:KRX11006:{day}",
                "is_member": "True", "eligible_new_entry": "", "tradable": "",
                "source": "KRX_11006", "official_count": r.get("official_count", ""),
            })
    normalized.sort(key=lambda x: (x["date"], x["ticker"]))
    args.output_root.mkdir(parents=True, exist_ok=True)
    out = args.output_root / "membership_daily_v25_candidate.csv"
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(normalized)
    manifest = {
        "schema_version": "v25-membership-normalized-candidate-v1",
        "source_membership": str(args.membership_source),
        "source_membership_sha256": sha256(args.membership_source),
        "repair_csv": str(repair_path), "repair_csv_sha256": sha256(repair_path),
        "official_repair_dates": sorted(repair_dates),
        "official_count_distribution": {"99": len(repair_dates)},
        "rows": len(normalized), "official_rows": len(repair_rows),
        "unresolved_tradability_flags": len(repair_rows),
        "imputation_performed": False,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_release": False,
        "note": "공식 KRX 응답의 99종목을 그대로 보존하며 누락 종목을 추정하지 않음",
        "output_sha256": sha256(out),
    }
    (args.output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"source_rows={len(source_rows)} output_rows={len(normalized)} official_rows={len(repair_rows)} dates={len(repair_dates)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
