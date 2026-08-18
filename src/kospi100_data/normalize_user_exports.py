from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

from .schema import SOURCE_MANIFEST_COLUMNS, TABLE_SPECS
from .validation import sha256_file


MEMBERSHIP_SOURCE_COLUMNS = ("date", "ticker", "name", "is_member")
INDEX_SOURCE_COLUMNS = (
    "일자",
    "종가",
    "대비",
    "등락률",
    "시가",
    "고가",
    "저가",
    "거래량(천주)",
    "거래대금(백만원)",
    "상장시가총액",
)


def _read_csv(path: Path, encoding: str) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    return fieldnames, rows


def _require_columns(actual: Iterable[str], required: Iterable[str], source: Path) -> None:
    missing = [column for column in required if column not in actual]
    if missing:
        raise ValueError(f"{source}: missing columns: {', '.join(missing)}")


def _parse_decimal(value: str, *, column: str, row_number: int) -> Decimal:
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"row {row_number}: {column} is not numeric: {value!r}") from exc


def _format_decimal(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _weekday_grid(start: date, end: date) -> list[date]:
    values: list[date] = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            values.append(cursor)
        cursor += timedelta(days=1)
    return values


def load_membership_snapshots(path: Path) -> tuple[dict[date, dict[str, str]], dict[str, object]]:
    fieldnames, rows = _read_csv(path, "utf-8-sig")
    _require_columns(fieldnames, MEMBERSHIP_SOURCE_COLUMNS, path)
    snapshots: dict[date, dict[str, str]] = {}
    duplicate_keys: list[str] = []
    invalid_member_values: Counter[str] = Counter()
    ticker_names: dict[str, set[str]] = {}
    blank_names = 0

    for row_number, row in enumerate(rows, start=2):
        try:
            session = date.fromisoformat(row["date"])
        except ValueError as exc:
            raise ValueError(f"row {row_number}: invalid membership date {row['date']!r}") from exc
        ticker = row["ticker"]
        if len(ticker) != 6 or not ticker.isdigit():
            raise ValueError(f"row {row_number}: ticker must be six digits: {ticker!r}")
        if row["is_member"] != "1":
            invalid_member_values[row["is_member"]] += 1
        if not row["name"]:
            blank_names += 1
        daily = snapshots.setdefault(session, {})
        if ticker in daily:
            duplicate_keys.append(f"{session.isoformat()}|{ticker}")
        daily[ticker] = row["name"]
        ticker_names.setdefault(ticker, set()).add(row["name"])

    if not snapshots:
        raise ValueError(f"{path}: no membership rows")
    dates = sorted(snapshots)
    if dates != _weekday_grid(dates[0], dates[-1]):
        raise ValueError("membership snapshots do not form a complete weekday grid; interval inference is unsafe")
    if duplicate_keys:
        raise ValueError(f"duplicate membership keys found: {duplicate_keys[:5]}")
    if invalid_member_values:
        raise ValueError(f"unsupported is_member values: {dict(invalid_member_values)}")
    if blank_names:
        raise ValueError(f"blank company names found: {blank_names}")

    counts = Counter(len(values) for values in snapshots.values())
    set_change_days = 0
    name_change_events = 0
    for previous_date, current_date in zip(dates, dates[1:]):
        previous = snapshots[previous_date]
        current = snapshots[current_date]
        if set(previous) != set(current):
            set_change_days += 1
        name_change_events += sum(
            previous[ticker] != current[ticker]
            for ticker in set(previous) & set(current)
        )
    profile: dict[str, object] = {
        "source_rows": len(rows),
        "date_start": dates[0].isoformat(),
        "date_end": dates[-1].isoformat(),
        "unique_dates": len(dates),
        "complete_weekday_grid": True,
        "daily_member_count_distribution": {str(key): counts[key] for key in sorted(counts)},
        "non_100_dates": [
            {"date": session.isoformat(), "member_count": len(snapshots[session])}
            for session in dates
            if len(snapshots[session]) != 100
        ],
        "unique_tickers": len(ticker_names),
        "unique_names": len({name for values in ticker_names.values() for name in values}),
        "tickers_with_multiple_names": sum(len(values) > 1 for values in ticker_names.values()),
        "constituent_set_change_days": set_change_days,
        "consecutive_snapshot_name_change_events": name_change_events,
    }
    return snapshots, profile


def compress_memberships(
    snapshots: dict[date, dict[str, str]],
    *,
    source_file: str,
    source_sha256: str,
    received_at_kst: str,
    index_code: str,
    index_name: str,
) -> list[dict[str, str]]:
    dates = sorted(snapshots)
    active: dict[str, dict[str, object]] = {}
    intervals: list[dict[str, object]] = []

    def close_interval(ticker: str, end: date) -> None:
        state = active.pop(ticker)
        intervals.append(
            {
                "ticker": ticker,
                "name": str(state["name"]),
                "valid_from": state["valid_from"],
                "valid_to": end,
                "membership_effective": state["membership_effective"],
            }
        )

    for snapshot_date in dates:
        current = snapshots[snapshot_date]
        for ticker in sorted(set(active) - set(current)):
            close_interval(ticker, snapshot_date)
        for ticker in sorted(current):
            name = current[ticker]
            if ticker not in active:
                active[ticker] = {
                    "name": name,
                    "valid_from": snapshot_date,
                    "membership_effective": snapshot_date,
                }
            elif active[ticker]["name"] != name:
                membership_effective = active[ticker]["membership_effective"]
                close_interval(ticker, snapshot_date)
                active[ticker] = {
                    "name": name,
                    "valid_from": snapshot_date,
                    "membership_effective": membership_effective,
                }

    terminal = dates[-1] + timedelta(days=1)
    for ticker in sorted(list(active)):
        close_interval(ticker, terminal)

    output: list[dict[str, str]] = []
    for interval in sorted(intervals, key=lambda row: (row["valid_from"], row["ticker"])):
        output.append(
            {
                "index_name": index_name,
                "index_code": index_code,
                "symbol_id": f"KRX_CODE:{interval['ticker']}",
                "symbol": str(interval["ticker"]),
                "company_name": str(interval["name"]),
                "valid_from": interval["valid_from"].isoformat(),
                "valid_to": interval["valid_to"].isoformat(),
                "announcement_at": "",
                "effective_date": interval["membership_effective"].isoformat(),
                "source_file": source_file,
                "source_sha256": source_sha256,
                "retrieved_at_kst": received_at_kst,
            }
        )
    return output


def derive_symbol_master(memberships: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "symbol_id": row["symbol_id"],
            "symbol": row["symbol"],
            "isin": "",
            "company_name": row["company_name"],
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
            "listing_date": "",
            "delisting_date": "",
            "source_file": row["source_file"],
            "source_sha256": row["source_sha256"],
        }
        for row in memberships
    ]


def load_index_export(
    path: Path,
    *,
    source_file: str,
    source_sha256: str,
    index_code: str,
    index_name: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, object]]:
    fieldnames, rows = _read_csv(path, "cp949")
    _require_columns(fieldnames, INDEX_SOURCE_COLUMNS, path)
    normalized: list[dict[str, str]] = []
    seen: set[date] = set()
    duplicate_dates: list[str] = []
    ohlc_errors: list[str] = []
    market_cap_missing = 0
    concatenated_header_markers = 0
    source_changes: dict[date, tuple[Decimal, Decimal, Decimal]] = {}

    for row_number, row in enumerate(rows, start=2):
        try:
            session = date.fromisoformat(row["일자"])
        except ValueError as exc:
            raise ValueError(f"row {row_number}: invalid index date {row['일자']!r}") from exc
        if session in seen:
            duplicate_dates.append(session.isoformat())
        seen.add(session)
        close = _parse_decimal(row["종가"], column="종가", row_number=row_number)
        open_ = _parse_decimal(row["시가"], column="시가", row_number=row_number)
        high = _parse_decimal(row["고가"], column="고가", row_number=row_number)
        low = _parse_decimal(row["저가"], column="저가", row_number=row_number)
        volume_thousand = _parse_decimal(row["거래량(천주)"], column="거래량(천주)", row_number=row_number)
        traded_value_million = _parse_decimal(
            row["거래대금(백만원)"], column="거래대금(백만원)", row_number=row_number
        )
        change = _parse_decimal(row["대비"], column="대비", row_number=row_number)
        change_pct = _parse_decimal(row["등락률"], column="등락률", row_number=row_number)
        source_changes[session] = (close, change, change_pct)
        market_cap_text = row["상장시가총액"]
        if market_cap_text.endswith("일자"):
            concatenated_header_markers += 1
            market_cap_text = market_cap_text.removesuffix("일자")
        if market_cap_text:
            _parse_decimal(market_cap_text, column="상장시가총액", row_number=row_number)
        else:
            market_cap_missing += 1
        if high < low or not low <= open_ <= high or not low <= close <= high:
            ohlc_errors.append(session.isoformat())
        if min(open_, high, low, close) <= 0 or volume_thousand < 0 or traded_value_million < 0:
            ohlc_errors.append(session.isoformat())
        normalized.append(
            {
                "trade_date": session.isoformat(),
                "index_code": index_code,
                "index_name": index_name,
                "open": _format_decimal(open_),
                "high": _format_decimal(high),
                "low": _format_decimal(low),
                "close": _format_decimal(close),
                "volume": _format_decimal(volume_thousand * Decimal(1000)),
                "traded_value": _format_decimal(traded_value_million * Decimal(1_000_000)),
                "source_file": source_file,
                "source_sha256": source_sha256,
            }
        )

    if not normalized:
        raise ValueError(f"{path}: no index rows")
    if duplicate_dates:
        raise ValueError(f"duplicate index dates found: {duplicate_dates[:5]}")
    if ohlc_errors:
        raise ValueError(f"index OHLC/activity invariants failed: {ohlc_errors[:5]}")
    normalized.sort(key=lambda row: row["trade_date"])
    ordered_dates = [date.fromisoformat(row["trade_date"]) for row in normalized]
    change_mismatch_count = 0
    change_pct_mismatch_count = 0
    max_change_abs_error = Decimal(0)
    max_change_pct_abs_error = Decimal(0)
    for previous_date, current_date in zip(ordered_dates, ordered_dates[1:]):
        previous_close = source_changes[previous_date][0]
        close, reported_change, reported_change_pct = source_changes[current_date]
        change_error = abs((close - previous_close) - reported_change)
        pct_error = abs(((close - previous_close) / previous_close * Decimal(100)) - reported_change_pct)
        max_change_abs_error = max(max_change_abs_error, change_error)
        max_change_pct_abs_error = max(max_change_pct_abs_error, pct_error)
        if change_error > Decimal("0.011"):
            change_mismatch_count += 1
        if pct_error > Decimal("0.011"):
            change_pct_mismatch_count += 1
    calendar = [
        {
            "trade_date": row["trade_date"],
            "is_trading_day": "1",
            "market_open_kst": "",
            "market_close_kst": "",
            "is_early_close": "",
            "source_file": source_file,
            "source_sha256": source_sha256,
        }
        for row in normalized
    ]
    source_dates = [date.fromisoformat(row["일자"]) for row in rows]
    direction_changes = sum(
        current >= previous for previous, current in zip(source_dates, source_dates[1:])
    )
    profile: dict[str, object] = {
        "source_rows": len(rows),
        "date_start": normalized[0]["trade_date"],
        "date_end": normalized[-1]["trade_date"],
        "unique_dates": len(normalized),
        "duplicate_dates": 0,
        "ohlc_errors": 0,
        "negative_activity_rows": 0,
        "source_order_not_globally_monotonic": source_dates != sorted(source_dates)
        and source_dates != sorted(source_dates, reverse=True),
        "source_order_block_boundaries": direction_changes,
        "market_cap_missing_rows": market_cap_missing,
        "concatenated_header_markers_removed_from_unused_market_cap_field": concatenated_header_markers,
        "reported_change_mismatch_rows_tolerance_0_011": change_mismatch_count,
        "reported_change_pct_mismatch_rows_tolerance_0_011": change_pct_mismatch_count,
        "reported_change_max_abs_error": _format_decimal(max_change_abs_error),
        "reported_change_pct_max_abs_error": _format_decimal(max_change_pct_abs_error),
        "unit_conversions": {
            "volume": "거래량(천주) × 1,000",
            "traded_value": "거래대금(백만원) × 1,000,000 KRW",
        },
    }
    return normalized, calendar, profile


def _write_csv(path: Path, fieldnames: Iterable[str], rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def normalize_exports(
    membership_source: Path,
    index_source: Path,
    input_root: Path,
    manifest_path: Path,
    profile_path: Path,
    *,
    received_at_kst: str,
    index_code: str = "KOSPI100",
    index_name: str = "KOSPI 100",
) -> dict[str, object]:
    parsed_timestamp = datetime.fromisoformat(received_at_kst)
    if parsed_timestamp.tzinfo is None:
        raise ValueError("received_at_kst must include a UTC offset")
    membership_source = Path(membership_source)
    index_source = Path(index_source)
    input_root = Path(input_root)
    membership_sha = sha256_file(membership_source)
    index_sha = sha256_file(index_source)

    snapshots, membership_profile = load_membership_snapshots(membership_source)
    memberships = compress_memberships(
        snapshots,
        source_file=membership_source.name,
        source_sha256=membership_sha,
        received_at_kst=received_at_kst,
        index_code=index_code,
        index_name=index_name,
    )
    symbol_master = derive_symbol_master(memberships)
    reconstruction_mismatches = 0
    parsed_memberships = [
        (
            date.fromisoformat(row["valid_from"]),
            date.fromisoformat(row["valid_to"]),
            row["symbol"],
            row["company_name"],
        )
        for row in memberships
    ]
    for snapshot_date, snapshot in snapshots.items():
        reconstructed = {
            symbol: name
            for start, end, symbol, name in parsed_memberships
            if start <= snapshot_date < end
        }
        if reconstructed != snapshot:
            reconstruction_mismatches += 1
    membership_profile["interval_reconstruction_mismatched_dates"] = reconstruction_mismatches
    if reconstruction_mismatches:
        raise ValueError(
            f"compressed membership intervals fail to reproduce {reconstruction_mismatches} daily snapshots"
        )
    index_rows, calendar_rows, index_profile = load_index_export(
        index_source,
        source_file=index_source.name,
        source_sha256=index_sha,
        index_code=index_code,
        index_name=index_name,
    )

    _write_csv(
        input_root / TABLE_SPECS["symbol_master"].filename,
        TABLE_SPECS["symbol_master"].required_columns,
        symbol_master,
    )
    _write_csv(
        input_root / TABLE_SPECS["universe_membership"].filename,
        TABLE_SPECS["universe_membership"].required_columns,
        memberships,
    )
    _write_csv(
        input_root / TABLE_SPECS["trading_calendar"].filename,
        TABLE_SPECS["trading_calendar"].required_columns,
        calendar_rows,
    )
    _write_csv(
        input_root / TABLE_SPECS["index_ohlcv_raw"].filename,
        TABLE_SPECS["index_ohlcv_raw"].required_columns,
        index_rows,
    )

    membership_dates = set(snapshots)
    index_dates = {date.fromisoformat(row["trade_date"]) for row in index_rows}
    non_100_sessions = [
        session.isoformat()
        for session in sorted(index_dates)
        if len(snapshots[session]) != 100
    ]
    membership_profile["dates_not_in_index_calendar"] = len(membership_dates - index_dates)
    membership_profile["index_dates_without_membership_snapshot"] = len(index_dates - membership_dates)
    membership_profile["non_100_trading_sessions"] = non_100_sessions
    profile: dict[str, object] = {
        "profile_version": "phase1-source-profile-v1",
        "received_at_kst": received_at_kst,
        "sources": {
            "membership": {"file": membership_source.name, "sha256": membership_sha},
            "index": {"file": index_source.name, "sha256": index_sha},
        },
        "membership": membership_profile,
        "index": index_profile,
        "normalized_rows": {
            "symbol_master": len(symbol_master),
            "universe_membership": len(memberships),
            "trading_calendar": len(calendar_rows),
            "index_ohlcv_raw": len(index_rows),
        },
        "audit_findings": [
            {
                "severity": "BLOCKER",
                "code": "UPSTREAM_LINEAGE_UNVERIFIED",
                "message": "The supplied CSVs do not embed upstream source URL, query parameters, retrieval time, or licence reference.",
            },
            {
                "severity": "BLOCKER",
                "code": "PROVISIONAL_SYMBOL_IDENTITY",
                "message": "symbol_id is provisionally derived from the six-digit display code; ISIN, code-change, listing, and delisting evidence is absent.",
            },
            {
                "severity": "ERROR",
                "code": "UNIVERSE_SIZE_MISMATCH",
                "message": f"{len(non_100_sessions)} exchange sessions contain 99 rather than 100 members; no constituent was invented.",
            },
            {
                "severity": "WARNING",
                "code": "CALENDAR_SESSION_METADATA_MISSING",
                "message": "Trading dates are derived from the index export; official open/close times and early-close flags are unavailable.",
            },
            {
                "severity": "WARNING",
                "code": "INDEX_IDENTITY_METADATA_MISSING",
                "message": "The index export does not contain an index code/name field; KOSPI 100 identity comes from the user's project context and remains to be tied to upstream metadata.",
            },
        ],
    }
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest_rows = [
        {
            "logical_table": "symbol_master",
            "local_file": membership_source.name,
            "source_organization": "User-supplied; upstream not declared",
            "source_product": "Daily KOSPI 100 membership compilation",
            "source_url": "",
            "retrieved_at_kst": received_at_kst,
            "coverage_start": membership_profile["date_start"],
            "coverage_end": membership_profile["date_end"],
            "row_count": str(len(symbol_master)),
            "sha256": membership_sha,
            "licence_or_terms_reference": "Unverified",
            "notes": "Provisional code-based identity; ISIN/listing/delisting/code-change metadata absent.",
        },
        {
            "logical_table": "universe_membership",
            "local_file": membership_source.name,
            "source_organization": "User-supplied; upstream not declared",
            "source_product": "Daily KOSPI 100 membership compilation",
            "source_url": "",
            "retrieved_at_kst": received_at_kst,
            "coverage_start": membership_profile["date_start"],
            "coverage_end": membership_profile["date_end"],
            "row_count": str(len(memberships)),
            "sha256": membership_sha,
            "licence_or_terms_reference": "Unverified",
            "notes": "Weekday snapshots compressed to exclusive-end intervals; upstream effective/announcement metadata absent.",
        },
        {
            "logical_table": "trading_calendar",
            "local_file": index_source.name,
            "source_organization": "User-supplied; upstream not declared",
            "source_product": "개별지수시세추이 export",
            "source_url": "",
            "retrieved_at_kst": received_at_kst,
            "coverage_start": index_profile["date_start"],
            "coverage_end": index_profile["date_end"],
            "row_count": str(len(calendar_rows)),
            "sha256": index_sha,
            "licence_or_terms_reference": "Unverified",
            "notes": "Session dates derived from index observations; official hours and early-close flags unavailable.",
        },
        {
            "logical_table": "index_ohlcv_raw",
            "local_file": index_source.name,
            "source_organization": "User-supplied; upstream not declared",
            "source_product": "개별지수시세추이 export",
            "source_url": "",
            "retrieved_at_kst": received_at_kst,
            "coverage_start": index_profile["date_start"],
            "coverage_end": index_profile["date_end"],
            "row_count": str(len(index_rows)),
            "sha256": index_sha,
            "licence_or_terms_reference": "Unverified",
            "notes": "Sorted ascending; thousand-share and KRW-million fields converted to base units; index identity metadata absent in file.",
        },
    ]
    _write_csv(manifest_path, SOURCE_MANIFEST_COLUMNS, manifest_rows)
    return profile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize the two user-supplied Phase 1 CSV exports.")
    parser.add_argument("--membership-source", type=Path, required=True)
    parser.add_argument("--index-source", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, default=Path("data/incoming"))
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/source_manifest.csv"))
    parser.add_argument("--profile", type=Path, default=Path("data/quality/source_profile.json"))
    parser.add_argument("--received-at-kst", required=True)
    parser.add_argument("--index-code", default="KOSPI100")
    parser.add_argument("--index-name", default="KOSPI 100")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    profile = normalize_exports(
        args.membership_source,
        args.index_source,
        args.input_root,
        args.manifest,
        args.profile,
        received_at_kst=args.received_at_kst,
        index_code=args.index_code,
        index_name=args.index_name,
    )
    print(f"membership_rows={profile['membership']['source_rows']}")
    print(f"index_rows={profile['index']['source_rows']}")
    print(f"profile={args.profile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
