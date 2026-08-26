#!/usr/bin/env python3
"""Build a fail-closed corporate-action audit from v25 KRX and DART raw data.

This script intentionally does not create an executable adjustment table.  KRX
listed-share changes and DART filings are evidence, not sufficient proof of a
point-in-time multiplier and effective trading session.  Every unresolved event
therefore remains barred from integration until separately verified.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


EVENT_RULES = (
    ("STOCK_SPLIT_OR_REVERSE_SPLIT", ("액면분할", "주식분할", "주식병합")),
    ("BONUS_ISSUE", ("무상증자",)),
    ("CAPITAL_REDUCTION", ("감자",)),
    ("COMPANY_SPLIT_MERGER", ("분할합병",)),
    ("COMPANY_SPLIT", ("회사분할",)),
    ("MERGER", ("합병",)),
    ("SHARE_EXCHANGE_TRANSFER", ("주식교환", "주식이전")),
    ("PAID_ISSUE", ("유상증자",)),
)
LABELS_FOR_EVENT = {
    "BONUS_ISSUE": ("bonus_issue", "paid_or_bonus_issue"),
    "CAPITAL_REDUCTION": ("capital_reduction",),
    "COMPANY_SPLIT_MERGER": ("split_merger",),
    "COMPANY_SPLIT": ("company_split",),
    "MERGER": ("merger",),
    "SHARE_EXCHANGE_TRANSFER": ("share_exchange_transfer",),
    "PAID_ISSUE": ("paid_or_bonus_issue",),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def event_type(report_name: str) -> str:
    normalized = report_name.replace(" ", "")
    for name, terms in EVENT_RULES:
        if any(term.replace(" ", "") in normalized for term in terms):
            return name
    return "OTHER_CANDIDATE"


def response_status(root: Path, label: str, corp_code: str, year: str) -> str:
    path = root / "structured" / label / corp_code / f"{year}.json"
    if not path.exists():
        return "MISSING"
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("status", "MALFORMED"))
    except (OSError, json.JSONDecodeError):
        return "MALFORMED"


def consolidated_status(primary_root: Path, repaired_root: Path | None, labels: tuple[str, ...], corp_code: str, year: str) -> str:
    statuses: list[str] = []
    if repaired_root:
        statuses.extend(response_status(repaired_root, label, corp_code, year) for label in labels)
    statuses.extend(response_status(primary_root, label, corp_code, year) for label in labels)
    if "000" in statuses:
        return "000"
    if "101" in statuses:
        return "101_REPAIR_REQUIRED"
    if any(status not in {"MISSING", "013"} for status in statuses):
        return next(status for status in statuses if status not in {"MISSING", "013"})
    return "NO_STRUCTURED_EVIDENCE"


def resolve_row(row: dict[str, str], primary_root: Path, repaired_root: Path | None) -> dict[str, str]:
    kind = event_type(row.get("report_nm", ""))
    labels = LABELS_FOR_EVENT.get(kind, ())
    structured = consolidated_status(primary_root, repaired_root, labels, row["corp_code"], row["rcept_dt"][:4]) if labels else "NOT_APPLICABLE"
    return {
        "ticker": row["ticker"],
        "corp_code": row["corp_code"],
        "rcept_no": row["rcept_no"],
        "rcept_dt": row["rcept_dt"],
        "report_nm": row["report_nm"],
        "event_type_candidate": kind,
        "document_status": row["document_status"],
        "structured_status": structured,
        "resolution_status": "UNRESOLVED_BLOCK_IF_IN_UNIVERSE",
        "integration_status": "NOT_FOR_FEATURE_OR_PORTFOLIO_USE",
        "reason": "No verified point-in-time effective session and multiplier; do not infer from price or listed-share changes.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a v25 corporate-action fail-closed audit; no adjustment table is emitted")
    parser.add_argument("--dart-root", type=Path, default=Path("data/incoming/v25_kospi_dart_audit_raw_complete"))
    parser.add_argument("--repaired-dart-root", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/v25_kospi_corporate_action_audit"))
    args = parser.parse_args(argv)
    source = args.dart_root / "corporate_action_candidates.csv"
    if not source.exists():
        raise FileNotFoundError(f"Candidate input is missing: {source}")
    args.output_root.mkdir(parents=True, exist_ok=True)
    with source.open("r", encoding="utf-8", newline="") as handle:
        rows = [resolve_row(row, args.dart_root, args.repaired_dart_root) for row in csv.DictReader(handle)]
    columns = list(rows[0]) if rows else ["ticker", "corp_code", "rcept_no", "rcept_dt", "report_nm", "event_type_candidate", "document_status", "structured_status", "resolution_status", "integration_status", "reason"]
    output = args.output_root / "corporate_action_resolution.csv"
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: (row["rcept_dt"], row["ticker"], row["rcept_no"])))
    counts = Counter(row["event_type_candidate"] for row in rows)
    structured_counts = Counter(row["structured_status"] for row in rows)
    manifest = {
        "schema_version": "v25-kospi-corporate-action-audit-v1",
        "purpose": "audit_only_not_factor_or_portfolio_input",
        "source_candidate_csv": str(source),
        "source_candidate_sha256": sha256_file(source),
        "repaired_dart_root": str(args.repaired_dart_root) if args.repaired_dart_root else None,
        "rows": len(rows),
        "event_type_counts": dict(sorted(counts.items())),
        "structured_status_counts": dict(sorted(structured_counts.items())),
        "resolution_status_counts": {"UNRESOLVED_BLOCK_IF_IN_UNIVERSE": len(rows)},
        "automatic_adjustments_emitted": 0,
        "output_sha256": sha256_file(output),
        "limitations": [
            "DART current stock-code mapping is not point-in-time identity proof.",
            "A filing date is not a verified effective trading session.",
            "No price or share multiplier is inferred from raw KRX observations.",
            "This audit cannot be merged into v24 or used as an investment factor.",
        ],
    }
    (args.output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} fail-closed audit rows to {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
