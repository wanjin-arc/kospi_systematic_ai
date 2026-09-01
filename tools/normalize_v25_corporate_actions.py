#!/usr/bin/env python3
"""Normalize v25 corporate-action evidence without manufacturing terms.

Only an independently supplied, auditable terms table can promote an event.
Without confirmed effective_date, share_multiplier, price_multiplier and PIT
identity, every event remains a reset/block candidate rather than an adjustment.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


MECHANICAL = {"STOCK_SPLIT_OR_REVERSE_SPLIT", "BONUS_ISSUE", "CAPITAL_REDUCTION"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize v25 corporate-action evidence, fail closed")
    parser.add_argument("--triage-csv", type=Path, default=Path("data/processed/v25_membership_corporate_action_audit/candidate_triage.csv"))
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/v25_corporate_actions_normalized"))
    args = parser.parse_args(argv)
    args.output_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    with args.triage_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        for candidate in csv.DictReader(handle):
            kind = candidate["event_type_candidate"]
            handling = "RESET_AND_BLOCK" if kind in {"MERGER", "COMPANY_SPLIT", "COMPANY_SPLIT_MERGER", "SHARE_EXCHANGE_TRANSFER"} else "BLOCK_PENDING_TERMS"
            rows.append({
                "canonical_event_id": f"DART:{candidate['rcept_no']}", "ticker": candidate["ticker"],
                "corp_code": candidate["corp_code"], "filing_date": candidate["rcept_dt"],
                "event_type_candidate": kind, "document_status": candidate["document_status"],
                "member_on_filing_date": candidate["member_on_filing_date"],
                "effective_date": "", "share_multiplier": "", "price_multiplier": "",
                "feature_handling_candidate": handling,
                "portfolio_handling_candidate": "BLOCK_UNTIL_TERMS_VERIFIED",
                "normalization_status": "UNRESOLVED_MISSING_EFFECTIVE_DATE_RATIO_PIT_IDENTITY",
                "evidence_requirement": "KRX effective session + DART ratio + PIT security identity + KRX price/share cross-check",
            })
    output = args.output_root / "corporate_actions_v25_unresolved.csv"
    columns = list(rows[0]) if rows else []
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        if columns: writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: (row["filing_date"], row["ticker"], row["canonical_event_id"])))
    template = args.output_root / "verified_terms_required_template.csv"
    template.write_text("canonical_event_id,effective_date,share_multiplier,price_multiplier,pit_security_id,krx_crosscheck_status,primary_evidence\n", encoding="utf-8")
    counts = Counter(row["event_type_candidate"] for row in rows)
    (args.output_root / "manifest.json").write_text(json.dumps({
        "schema_version": "v25-corporate-action-normalization-v1", "source_triage": str(args.triage_csv),
        "source_triage_sha256": sha256_file(args.triage_csv), "rows": len(rows),
        "event_type_counts": dict(sorted(counts.items())), "promoted_mechanical_adjustments": 0,
        "status": "BLOCKED_PENDING_VERIFIED_TERMS", "output_sha256": sha256_file(output),
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"normalized_rows={len(rows)} promoted_mechanical_adjustments=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
