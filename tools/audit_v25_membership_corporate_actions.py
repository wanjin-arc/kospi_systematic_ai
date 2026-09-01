#!/usr/bin/env python3
"""Cross-check the uploaded PIT membership file against v25 KRX/DART evidence.

The result is an audit and triage report only. It does not create a corporate
action adjustment table or alter any v24 input.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def truth(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "y", "yes"}


def event_type(title: str) -> str:
    compact = title.replace(" ", "")
    for name, terms in EVENT_RULES:
        if any(term.replace(" ", "") in compact for term in terms):
            return name
    return "OTHER_CANDIDATE"


def load_membership(path: Path, start: str, end: str) -> tuple[dict[str, set[str]], Counter, set[str], dict[str, int]]:
    by_date: dict[str, set[str]] = defaultdict(set)
    daily_counts: Counter = Counter()
    all_tickers: set[str] = set()
    official_counts: dict[str, int] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            day = row.get("date", "")
            ticker = row.get("ticker", "").strip().zfill(6)
            if not (start <= day <= end) or not ticker or not truth(row.get("is_member", "")):
                continue
            by_date[day].add(ticker)
            all_tickers.add(ticker)
            if row.get("source", "") == "KRX_11006" and row.get("official_count", "").isdigit():
                count = int(row["official_count"])
                if day in official_counts and official_counts[day] != count:
                    raise ValueError(f"Conflicting official counts for {day}")
                official_counts[day] = count
    daily_counts.update(len(values) for values in by_date.values())
    return by_date, daily_counts, all_tickers, official_counts


def load_krx_sets(raw_root: Path) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for path in sorted((raw_root / "raw" / "market_stk").glob("*/*.csv.gz")):
        compact_day = path.stem.split(".")[0]
        day = f"{compact_day[:4]}-{compact_day[4:6]}-{compact_day[6:8]}"
        tickers: set[str] = set()
        with gzip.open(path, "rt", encoding="cp949", newline="") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            for row in reader:
                if row and row[0].strip().isdigit():
                    tickers.add(row[0].strip().zfill(6))
        result[day] = tickers
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit PIT membership and v25 corporate-action candidates")
    parser.add_argument("--membership", type=Path, required=True)
    parser.add_argument("--krx-root", type=Path, default=Path("data/incoming/v25_kospi_raw"))
    parser.add_argument("--dart-root", type=Path, default=Path("data/incoming/v25_kospi_dart_audit_raw_complete"))
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/v25_membership_corporate_action_audit"))
    parser.add_argument("--start", default="2011-01-01")
    parser.add_argument("--end", default="2025-12-31")
    args = parser.parse_args(argv)
    args.output_root.mkdir(parents=True, exist_ok=True)

    membership, daily_counts, all_members, official_counts = load_membership(args.membership, args.start, args.end)
    krx = load_krx_sets(args.krx_root)

    date_rows: list[dict[str, object]] = []
    missing_total = 0
    for day in sorted(set(membership) | set(krx)):
        if not (args.start <= day <= args.end):
            continue
        members = membership.get(day, set())
        observed = krx.get(day, set())
        missing = sorted(members - observed)
        missing_total += len(missing)
        official_partial = bool(members) and official_counts.get(day) == len(members)
        date_rows.append({
            "date": day,
            "membership_members": len(members),
            "krx_observed_tickers": len(observed),
            "membership_missing_from_krx": len(missing),
            "missing_tickers": ";".join(missing),
            "membership_available": bool(members),
            "membership_count_ok": bool(members) and (len(members) == 100 or official_partial),
            "coverage_status": "NO_PIT_MEMBERSHIP" if not members else ("OK" if len(members) == 100 else ("OFFICIAL_PARTIAL_99" if official_partial else "COUNT_NOT_100")),
        })
    with (args.output_root / "membership_date_audit.csv").open("w", encoding="utf-8", newline="") as handle:
        columns = list(date_rows[0]) if date_rows else ["date", "membership_members", "krx_observed_tickers", "membership_missing_from_krx", "missing_tickers", "membership_available", "membership_count_ok", "coverage_status"]
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader(); writer.writerows(date_rows)

    ordered_membership_dates = sorted(membership)
    gap_rows: list[dict[str, object]] = []
    for index, day in enumerate(ordered_membership_dates):
        current = membership[day]
        if len(current) == 100:
            continue
        previous_day = ordered_membership_dates[index - 1] if index else ""
        next_day = ordered_membership_dates[index + 1] if index + 1 < len(ordered_membership_dates) else ""
        previous = membership.get(previous_day, set())
        following = membership.get(next_day, set())
        gap_rows.append({
            "date": day,
            "count": len(current),
            "previous_date": previous_day,
            "next_date": next_day,
            "missing_vs_previous": ";".join(sorted(previous - current)),
            "added_vs_previous": ";".join(sorted(current - previous)),
            "missing_vs_next": ";".join(sorted(following - current)),
        })
    with (args.output_root / "membership_gap_transitions.csv").open("w", encoding="utf-8", newline="") as handle:
        columns = ["date", "count", "previous_date", "next_date", "missing_vs_previous", "added_vs_previous", "missing_vs_next"]
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader(); writer.writerows(gap_rows)

    candidate_path = args.dart_root / "corporate_action_candidates.csv"
    candidate_rows: list[dict[str, object]] = []
    event_counts: Counter = Counter()
    with candidate_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            kind = event_type(row.get("report_nm", ""))
            filing_day = row.get("rcept_dt", "")
            filing_members = membership.get(filing_day, set())
            in_any_membership = row.get("ticker", "").zfill(6) in all_members
            event_counts[kind] += 1
            candidate_rows.append({
                "ticker": row.get("ticker", "").zfill(6),
                "corp_code": row.get("corp_code", ""),
                "rcept_no": row.get("rcept_no", ""),
                "rcept_dt": filing_day,
                "report_nm": row.get("report_nm", ""),
                "event_type_candidate": kind,
                "document_status": row.get("document_status", ""),
                "member_on_filing_date": row.get("ticker", "").zfill(6) in filing_members,
                "member_at_any_observed_date": in_any_membership,
                "identity_status": "CURRENT_CODE_ONLY_UNPROVEN",
                "resolution_status": "REQUIRES_EFFECTIVE_DATE_RATIO_AND_PIT_IDENTITY",
            })
    with (args.output_root / "candidate_triage.csv").open("w", encoding="utf-8", newline="") as handle:
        columns = list(candidate_rows[0]) if candidate_rows else []
        writer = csv.DictWriter(handle, fieldnames=columns)
        if columns: writer.writeheader()
        writer.writerows(candidate_rows)

    manifest = {
        "schema_version": "v25-membership-corporate-action-audit-v1",
        "membership_source": str(args.membership),
        "membership_source_sha256": sha256_file(args.membership),
        "krx_root": str(args.krx_root),
        "dart_candidate_source": str(candidate_path),
        "dart_candidate_source_sha256": sha256_file(candidate_path),
        "date_range": [args.start, args.end],
        "membership_dates": len(membership),
        "krx_dates": len(krx),
        "membership_first_date": min(membership) if membership else None,
        "membership_last_date": max(membership) if membership else None,
        "daily_membership_count_distribution": {str(k): v for k, v in sorted(daily_counts.items())},
        "membership_dates_not_100": sum(v for k, v in daily_counts.items() if k != 100),
        "official_partial_membership_dates": sum(1 for day, count in official_counts.items() if len(membership.get(day, set())) == count),
        "krx_dates_without_membership": sum(1 for day in krx if day not in membership),
        "membership_ticker_rows_missing_from_krx": missing_total,
        "candidate_rows": len(candidate_rows),
        "candidate_event_type_counts": dict(sorted(event_counts.items())),
        "automatic_adjustments_emitted": 0,
        "identity_resolved_rows": 0,
        "limitations": [
            "Current-code DART mapping is not proof of historical security identity.",
            "Filing date is not an effective trading date.",
            "No corporate-action multiplier is inferred from KRX price or share-count changes.",
            "This report is not a v24 Phase 1 input release.",
        ],
    }
    (args.output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"membership_dates={len(membership)} krx_dates={len(krx)} candidate_rows={len(candidate_rows)}")
    print(f"membership_dates_not_100={manifest['membership_dates_not_100']} missing_membership_tickers_in_krx={missing_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
