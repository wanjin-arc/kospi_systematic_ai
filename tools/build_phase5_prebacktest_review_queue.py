#!/usr/bin/env python3
"""Build a fail-closed Phase 5 corporate-action review queue.

This tool never infers action terms from prices or listed shares.  It only
links the explicit Phase 5S share-change events to collected DART filings and
records the PIT identity status needed for a human/structured terms review.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path


DIRECT_TERMS_WORDS = ("주식분할결정", "무상증자결정")
FOLLOW_UP_WORDS = ("합병등종료보고서", "증권발행실적보고서", "발행결과", "청약결과")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def phase5_events(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if (row.get("member_both_sessions") or "").strip().lower() in {"true", "1"}]


def priority(report_name: str, document_status: str) -> str:
    if document_status != "DOCUMENT_ARCHIVED":
        return "SOURCE_UNAVAILABLE"
    if any(word in report_name for word in DIRECT_TERMS_WORDS):
        return "DIRECT_TERMS_CANDIDATE_REVIEW"
    if any(word in report_name for word in FOLLOW_UP_WORDS):
        return "FOLLOW_UP_TERMS_REVIEW"
    return "CONTEXT_REVIEW_REQUIRED"


def pit_identity(identity_rows: list[dict[str, str]], ticker: str, event_date: str) -> tuple[str, str]:
    matches = [
        row
        for row in identity_rows
        if row.get("ticker") == ticker and row.get("first_date", "") <= event_date <= row.get("last_date", "")
    ]
    if len(matches) != 1:
        return "MISSING_OR_AMBIGUOUS_PIT_IDENTITY", ""
    return matches[0].get("identity_status", ""), matches[0].get("corp_code", "")


def build_queue(
    events: list[dict[str, str]], filings: list[dict[str, str]], identity_rows: list[dict[str, str]], window_days: int
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for event in events:
        event_date = datetime.strptime(event["effective_date_candidate"], "%Y-%m-%d").date()
        identity_status, pit_corp_code = pit_identity(identity_rows, event["ticker"], event["effective_date_candidate"])
        for filing in filings:
            if filing.get("ticker") != event["ticker"]:
                continue
            filing_date = datetime.strptime(filing["rcept_dt"], "%Y%m%d").date()
            distance = abs((filing_date - event_date).days)
            if distance > window_days:
                continue
            report_name = filing.get("report_nm", "")
            rows.append(
                {
                    "candidate_id": event["candidate_id"],
                    "ticker": event["ticker"],
                    "observed_effective_date": event["effective_date_candidate"],
                    "observed_share_ratio": event.get("observed_share_ratio", ""),
                    "pit_identity_status": identity_status,
                    "pit_corp_code": pit_corp_code,
                    "rcept_no": filing["rcept_no"],
                    "rcept_dt": filing["rcept_dt"],
                    "filing_distance_days": str(distance),
                    "report_nm": report_name,
                    "document_zip": filing.get("document_zip", ""),
                    "document_status": filing.get("document_status", ""),
                    "review_priority": priority(report_name, filing.get("document_status", "")),
                    "terms_approved": "false",
                    "approval_reason": "",
                }
            )
    return sorted(rows, key=lambda row: (row["candidate_id"], int(row["filing_distance_days"]), row["rcept_no"]))


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 5 pre-backtest 기업행위 검토 대기열 생성기")
    parser.add_argument("--event-csv", type=Path, required=True)
    parser.add_argument("--filing-csv", type=Path, required=True)
    parser.add_argument("--identity-csv", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--window-days", type=int, default=730)
    args = parser.parse_args()
    if args.window_days < 0:
        raise SystemExit("--window-days는 0 이상이어야 합니다.")
    queue = build_queue(
        phase5_events(read_csv(args.event_csv)), read_csv(args.filing_csv), read_csv(args.identity_csv), args.window_days
    )
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "candidate_id", "ticker", "observed_effective_date", "observed_share_ratio", "pit_identity_status",
        "pit_corp_code", "rcept_no", "rcept_dt", "filing_distance_days", "report_nm", "document_zip",
        "document_status", "review_priority", "terms_approved", "approval_reason",
    ]
    with args.output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(queue)
    print(f"events={len(phase5_events(read_csv(args.event_csv)))} queue_rows={len(queue)} output={args.output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
