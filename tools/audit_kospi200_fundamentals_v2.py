#!/usr/bin/env python3
"""KOSPI 200 receipt-corrected PIT 재무 facts를 감사한다.

감사는 모델을 적합하거나 수익률을 계산하지 않는다. 원천 hash, receipt override,
다음 KRX 세션 사용, model eligibility를 순차적으로 검증한다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from normalize_dart_kospi200_fundamentals_v2 import load_membership_sessions, sha256


def audit(facts_path: Path, overrides_path: Path, membership_root: Path) -> dict[str, object]:
    if not facts_path.exists():
        raise FileNotFoundError(f"PIT facts가 없습니다: {facts_path}")
    sessions = {item.isoformat() for item in load_membership_sessions(membership_root)}
    overrides: dict[str, dict[str, str]] = {}
    with overrides_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            overrides[str(row["source_file"])] = row
    invalid: list[dict[str, str]] = []
    invalid_count = 0
    status_counts: Counter[str] = Counter()
    fs_div_counts: Counter[str] = Counter()
    scope_counts: Counter[str] = Counter()
    eligible_tickers: set[str] = set()
    rows = eligible_rows = 0
    with facts_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rows += 1
            status = str(row.get("availability_status") or "")
            status_counts[status] += 1
            fs_div_counts[str(row.get("fs_div") or "MISSING")] += 1
            scope_counts[str(row.get("statement_scope") or "MISSING")] += 1
            source = str(row.get("source_file") or "")
            override = overrides.get(source)
            eligible = row.get("model_eligible") == "true"
            if eligible:
                eligible_rows += 1
                eligible_tickers.add(str(row.get("ticker") or ""))
            receipt = str(row.get("receipt_date") or "")
            available = str(row.get("available_from") or "")
            valid = (
                override is not None
                and receipt == str(override.get("receipt_date") or "")
                and ((not eligible and not available) or (eligible and row.get("statement_scope") in {"CFS_EVIDENCED", "OFS_EVIDENCED"} and status.startswith("RESOLVED_NEXT_KRX_SESSION_") and available in sessions and available > f"{receipt[:4]}-{receipt[4:6]}-{receipt[6:8]}"))
            )
            if not valid:
                invalid_count += 1
                if len(invalid) < 20:
                    invalid.append({"source_file": source, "receipt_date": receipt, "available_from": available, "status": status, "model_eligible": row.get("model_eligible", "")})
    return {
        "schema_version": "kospi200-fundamental-pit-audit-v1",
        "facts_path": str(facts_path), "facts_sha256": sha256(facts_path),
        "receipt_overrides_path": str(overrides_path), "receipt_overrides_sha256": sha256(overrides_path),
        "membership_sessions": {"count": len(sessions), "min": min(sessions), "max": max(sessions)},
        "rows": rows, "eligible_rows": eligible_rows, "eligible_ticker_count": len(eligible_tickers),
        "availability_status_counts": dict(sorted(status_counts.items())), "api_payload_fs_div_counts": dict(sorted(fs_div_counts.items())),
        "statement_scope_counts": dict(sorted(scope_counts.items())),
        "invalid_pit_rows": invalid, "invalid_pit_row_count": invalid_count,
        "raw_modified": False, "protected_oos_accessed": False,
        "status": "PASS_PIT_FACTS_MODEL_NOT_STARTED" if not invalid_count else "FAIL_PIT_INVARIANT",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KOSPI 200 PIT 재무 facts 감사")
    parser.add_argument("--facts-root", type=Path, default=Path("data/processed/v2_kospi200_fundamentals_receipt_corrected"))
    parser.add_argument("--receipt-overrides", type=Path, default=Path("data/processed/v2_kospi200_dart_receipt_overrides/receipt_overrides.csv"))
    parser.add_argument("--membership-root", type=Path, default=Path("data/incoming/v2_kospi200_membership_raw/normalized/membership_daily"))
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/v2_phase1_fundamental_audit"))
    args = parser.parse_args(argv)
    result = audit(args.facts_root / "financial_facts_pit.csv", args.receipt_overrides, args.membership_root)
    args.output_root.mkdir(parents=True, exist_ok=True)
    target = args.output_root / "fundamental_audit.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "rows": result["rows"], "eligible_rows": result["eligible_rows"], "output": str(target)}, ensure_ascii=False))
    return 0 if result["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
