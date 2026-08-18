from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

from .schema import PRICE_COLUMNS, SOURCE_MANIFEST_COLUMNS, TABLE_SPECS

SYMBOL_RE = re.compile(r"^[0-9]{6}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TRUE_VALUES = {"1", "true", "TRUE", "True", "Y", "y"}


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    table: str
    key: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class CsvTable:
    name: str
    path: Path
    fieldnames: list[str]
    rows: list[dict[str, str]]
    sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_tables(input_root: Path) -> tuple[dict[str, CsvTable], list[Issue]]:
    tables: dict[str, CsvTable] = {}
    issues: list[Issue] = []
    for name, spec in TABLE_SPECS.items():
        path = input_root / spec.filename
        if not path.exists():
            issues.append(
                Issue("BLOCKER", "MISSING_INPUT_FILE", name, str(path), "Required input file is absent.")
            )
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
        missing = [column for column in spec.required_columns if column not in fieldnames]
        if missing:
            issues.append(
                Issue(
                    "BLOCKER",
                    "MISSING_COLUMNS",
                    name,
                    str(path),
                    f"Missing required columns: {', '.join(missing)}",
                )
            )
        if not rows and not spec.allow_empty:
            issues.append(Issue("BLOCKER", "EMPTY_REQUIRED_TABLE", name, str(path), "Required table has no rows."))
        tables[name] = CsvTable(name, path, fieldnames, rows, sha256_file(path))
    return tables, issues


def load_source_manifest(input_root: Path) -> tuple[list[dict[str, str]], list[Issue]]:
    path = input_root.parent / "manifests" / "source_manifest.csv"
    if not path.exists():
        return [], [Issue("BLOCKER", "MISSING_SOURCE_MANIFEST", "source_manifest", str(path), "Source manifest is absent.")]
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    missing = [column for column in SOURCE_MANIFEST_COLUMNS if column not in fieldnames]
    issues: list[Issue] = []
    if missing:
        issues.append(
            Issue("BLOCKER", "MISSING_MANIFEST_COLUMNS", "source_manifest", str(path), f"Missing columns: {', '.join(missing)}")
        )
    if not rows:
        issues.append(Issue("BLOCKER", "EMPTY_SOURCE_MANIFEST", "source_manifest", str(path), "Source manifest has no rows."))
    return rows, issues


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no UTC offset")
    return parsed


def parse_decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", ""))


def is_true(value: str) -> bool:
    return value in TRUE_VALUES


def _date_issue(table: str, key: str, column: str, value: str) -> Issue | None:
    if value == "":
        return None
    try:
        parse_date(value)
    except ValueError:
        return Issue("ERROR", "INVALID_DATE", table, key, f"{column} is not ISO YYYY-MM-DD: {value!r}")
    return None


def validate_symbols(table: CsvTable) -> list[Issue]:
    issues: list[Issue] = []
    for row_number, row in enumerate(table.rows, start=2):
        symbol = row.get("symbol", "")
        if symbol and not SYMBOL_RE.fullmatch(symbol):
            issues.append(
                Issue("ERROR", "INVALID_SYMBOL", table.name, str(row_number), f"Expected six digits, got {symbol!r}.")
            )
        if "symbol_id" in table.fieldnames and not row.get("symbol_id"):
            issues.append(Issue("ERROR", "MISSING_SYMBOL_ID", table.name, str(row_number), "symbol_id is empty."))
    return issues


def validate_symbol_master(table: CsvTable) -> list[Issue]:
    issues = validate_symbols(table)
    seen: set[tuple[str, str]] = set()
    intervals: dict[str, list[tuple[date, date | None, int]]] = defaultdict(list)
    for row_number, row in enumerate(table.rows, start=2):
        key = (row.get("symbol_id", ""), row.get("valid_from", ""))
        if key in seen:
            issues.append(Issue("ERROR", "DUPLICATE_SYMBOL_VERSION", table.name, str(key), "Duplicate version key."))
        seen.add(key)
        for column in ("valid_from", "valid_to", "listing_date", "delisting_date"):
            issue = _date_issue(table.name, str(row_number), column, row.get(column, ""))
            if issue:
                issues.append(issue)
        try:
            start = parse_date(row["valid_from"])
            end = parse_date(row["valid_to"]) if row.get("valid_to") else None
            if end is not None and end <= start:
                issues.append(Issue("ERROR", "INVALID_INTERVAL", table.name, str(row_number), "valid_to must be exclusive and after valid_from."))
            intervals[row["symbol_id"]].append((start, end, row_number))
        except (KeyError, ValueError):
            pass
    issues.extend(_overlap_issues(table.name, intervals))
    return issues


def _overlap_issues(
    table_name: str, intervals: dict[str, list[tuple[date, date | None, int]]]
) -> list[Issue]:
    issues: list[Issue] = []
    for symbol_id, values in intervals.items():
        ordered = sorted(values, key=lambda item: item[0])
        for left, right in zip(ordered, ordered[1:]):
            left_end = left[1] or date.max
            if right[0] < left_end:
                issues.append(
                    Issue(
                        "ERROR",
                        "OVERLAPPING_INTERVAL",
                        table_name,
                        symbol_id,
                        f"Rows {left[2]} and {right[2]} overlap.",
                    )
                )
    return issues


def validate_memberships(table: CsvTable, calendar: CsvTable | None, expected_size: int) -> list[Issue]:
    issues = validate_symbols(table)
    intervals: dict[str, list[tuple[date, date | None, int]]] = defaultdict(list)
    parsed: list[tuple[str, date, date | None]] = []
    for row_number, row in enumerate(table.rows, start=2):
        for column in ("valid_from", "valid_to", "effective_date"):
            issue = _date_issue(table.name, str(row_number), column, row.get(column, ""))
            if issue:
                issues.append(issue)
        if row.get("announcement_at"):
            try:
                parse_timestamp(row["announcement_at"])
            except ValueError as exc:
                issues.append(Issue("ERROR", "INVALID_TIMESTAMP", table.name, str(row_number), str(exc)))
        try:
            parse_timestamp(row.get("retrieved_at_kst", ""))
        except ValueError as exc:
            issues.append(Issue("ERROR", "INVALID_TIMESTAMP", table.name, str(row_number), str(exc)))
        try:
            start = parse_date(row["valid_from"])
            end = parse_date(row["valid_to"]) if row.get("valid_to") else None
            if end is not None and end <= start:
                issues.append(Issue("ERROR", "INVALID_INTERVAL", table.name, str(row_number), "valid_to must be after valid_from."))
            symbol_id = row["symbol_id"]
            intervals[symbol_id].append((start, end, row_number))
            parsed.append((symbol_id, start, end))
        except (KeyError, ValueError):
            pass
    issues.extend(_overlap_issues(table.name, intervals))

    if calendar is not None:
        for cal_row in calendar.rows:
            if not is_true(cal_row.get("is_trading_day", "")):
                continue
            try:
                session = parse_date(cal_row["trade_date"])
            except (KeyError, ValueError):
                continue
            active = {symbol_id for symbol_id, start, end in parsed if start <= session and (end is None or session < end)}
            if len(active) != expected_size:
                issues.append(
                    Issue(
                        "ERROR",
                        "UNIVERSE_SIZE_MISMATCH",
                        table.name,
                        session.isoformat(),
                        f"Expected {expected_size} active symbols, found {len(active)}.",
                    )
                )
    return issues


def validate_calendar(table: CsvTable) -> list[Issue]:
    issues: list[Issue] = []
    seen: set[str] = set()
    missing_session_times = 0
    unknown_early_close = 0
    for row_number, row in enumerate(table.rows, start=2):
        key = row.get("trade_date", "")
        issue = _date_issue(table.name, str(row_number), "trade_date", key)
        if issue:
            issues.append(issue)
        if key in seen:
            issues.append(Issue("ERROR", "DUPLICATE_SESSION", table.name, key, "Duplicate calendar date."))
        seen.add(key)
        if row.get("is_trading_day") not in TRUE_VALUES | {"0", "false", "FALSE", "False", "N", "n"}:
            issues.append(Issue("ERROR", "INVALID_BOOLEAN", table.name, key, "is_trading_day is not boolean-like."))
        if is_true(row.get("is_trading_day", "")) and (
            not row.get("market_open_kst") or not row.get("market_close_kst")
        ):
            missing_session_times += 1
        if not row.get("is_early_close"):
            unknown_early_close += 1
    if missing_session_times:
        issues.append(
            Issue(
                "WARNING",
                "MISSING_SESSION_TIMES",
                table.name,
                "aggregate",
                f"{missing_session_times} trading sessions lack official open/close times.",
            )
        )
    if unknown_early_close:
        issues.append(
            Issue(
                "WARNING",
                "UNKNOWN_EARLY_CLOSE_FLAGS",
                table.name,
                "aggregate",
                f"{unknown_early_close} calendar rows lack an early-close flag.",
            )
        )
    return issues


def validate_ohlcv(table: CsvTable, key_columns: tuple[str, ...]) -> list[Issue]:
    issues = validate_symbols(table) if "symbol" in table.fieldnames else []
    seen: set[tuple[str, ...]] = set()
    for row_number, row in enumerate(table.rows, start=2):
        key = tuple(row.get(column, "") for column in key_columns)
        key_text = "|".join(key)
        if key in seen:
            issues.append(Issue("ERROR", "DUPLICATE_BAR", table.name, key_text, "Duplicate date/instrument bar."))
        seen.add(key)
        date_issue = _date_issue(table.name, key_text, "trade_date", row.get("trade_date", ""))
        if date_issue:
            issues.append(date_issue)
        numeric: dict[str, Decimal] = {}
        for column in (*PRICE_COLUMNS, "volume", "traded_value"):
            try:
                numeric[column] = parse_decimal(row.get(column, ""))
            except (InvalidOperation, AttributeError):
                issues.append(Issue("ERROR", "INVALID_NUMBER", table.name, key_text, f"{column} is not numeric."))
        if not all(column in numeric for column in PRICE_COLUMNS):
            continue
        market_status = row.get("market_status", "TRADING").upper()
        if market_status == "TRADING" and any(numeric[column] <= 0 for column in PRICE_COLUMNS):
            issues.append(Issue("ERROR", "NONPOSITIVE_TRADING_PRICE", table.name, key_text, "Trading OHLC prices must be positive."))
        low, high = numeric["low"], numeric["high"]
        if high < low:
            issues.append(Issue("ERROR", "HIGH_BELOW_LOW", table.name, key_text, "high is below low."))
        if not (low <= numeric["open"] <= high) or not (low <= numeric["close"] <= high):
            issues.append(Issue("ERROR", "OHLC_RANGE_ERROR", table.name, key_text, "open/close is outside [low, high]."))
        if numeric.get("volume", Decimal(0)) < 0 or numeric.get("traded_value", Decimal(0)) < 0:
            issues.append(Issue("ERROR", "NEGATIVE_ACTIVITY", table.name, key_text, "volume/traded_value is negative."))
    return issues


def validate_events(table: CsvTable) -> list[Issue]:
    issues = validate_symbols(table)
    for row_number, row in enumerate(table.rows, start=2):
        for column in ("effective_date",):
            issue = _date_issue(table.name, str(row_number), column, row.get(column, ""))
            if issue:
                issues.append(issue)
        if row.get("announcement_at"):
            try:
                parse_timestamp(row["announcement_at"])
            except ValueError as exc:
                issues.append(Issue("ERROR", "INVALID_TIMESTAMP", table.name, str(row_number), str(exc)))
        action = row.get("action_type", "").upper()
        if action in {"SPLIT", "REVERSE_SPLIT", "STOCK_DIVIDEND"}:
            try:
                numerator = parse_decimal(row.get("share_factor_numerator", ""))
                denominator = parse_decimal(row.get("share_factor_denominator", ""))
                if numerator <= 0 or denominator <= 0:
                    raise InvalidOperation
            except (InvalidOperation, ZeroDivisionError):
                issues.append(Issue("ERROR", "INVALID_SHARE_FACTOR", table.name, str(row_number), "Split factor must be positive."))
    return issues


def validate_suspensions(table: CsvTable) -> list[Issue]:
    issues = validate_symbols(table)
    for row_number, row in enumerate(table.rows, start=2):
        for column in ("suspended_from", "suspended_to"):
            issue = _date_issue(table.name, str(row_number), column, row.get(column, ""))
            if issue:
                issues.append(issue)
        try:
            start = parse_date(row["suspended_from"])
            end = parse_date(row["suspended_to"]) if row.get("suspended_to") else None
            if end is not None and end < start:
                issues.append(Issue("ERROR", "INVALID_SUSPENSION_INTERVAL", table.name, str(row_number), "suspended_to precedes suspended_from."))
        except (KeyError, ValueError):
            pass
    return issues


def validate_lineage(tables: dict[str, CsvTable], manifest_rows: list[dict[str, str]]) -> list[Issue]:
    issues: list[Issue] = []
    manifest_pairs: set[tuple[str, str]] = set()
    manifest_tables: set[str] = set()
    for row_number, row in enumerate(manifest_rows, start=2):
        logical_table = row.get("logical_table", "")
        local_file = row.get("local_file", "")
        digest = row.get("sha256", "").lower()
        manifest_tables.add(logical_table)
        manifest_pairs.add((local_file, digest))
        if logical_table not in TABLE_SPECS:
            issues.append(Issue("ERROR", "UNKNOWN_MANIFEST_TABLE", "source_manifest", str(row_number), logical_table))
        if not SHA256_RE.fullmatch(digest):
            issues.append(Issue("ERROR", "INVALID_SOURCE_SHA256", "source_manifest", str(row_number), "sha256 must be 64 lowercase hex characters."))
        try:
            parse_timestamp(row.get("retrieved_at_kst", ""))
        except ValueError as exc:
            issues.append(Issue("ERROR", "INVALID_TIMESTAMP", "source_manifest", str(row_number), str(exc)))
        for column in ("coverage_start", "coverage_end"):
            issue = _date_issue("source_manifest", str(row_number), column, row.get(column, ""))
            if issue:
                issues.append(issue)

    for name, table in tables.items():
        if name not in manifest_tables:
            issues.append(Issue("BLOCKER", "UNMANIFESTED_TABLE", name, str(table.path), "No source manifest row for this logical table."))
        for row_number, row in enumerate(table.rows, start=2):
            source_file = row.get("source_file", "")
            digest = row.get("source_sha256", "").lower()
            if not source_file or not SHA256_RE.fullmatch(digest):
                issues.append(Issue("ERROR", "INVALID_ROW_LINEAGE", name, str(row_number), "source_file or source_sha256 is invalid."))
            elif (source_file, digest) not in manifest_pairs:
                issues.append(Issue("ERROR", "SOURCE_NOT_IN_MANIFEST", name, str(row_number), f"{source_file} / {digest}"))
    return issues


def validate_referential_integrity(tables: dict[str, CsvTable]) -> list[Issue]:
    if "symbol_master" not in tables:
        return []
    master: dict[str, list[tuple[date, date | None, str]]] = defaultdict(list)
    for row in tables["symbol_master"].rows:
        try:
            master[row["symbol_id"]].append(
                (
                    parse_date(row["valid_from"]),
                    parse_date(row["valid_to"]) if row.get("valid_to") else None,
                    row["symbol"],
                )
            )
        except (KeyError, ValueError):
            continue

    checks = {
        "universe_membership": "valid_from",
        "ohlcv_raw": "trade_date",
        "corporate_actions": "effective_date",
        "suspensions": "suspended_from",
    }
    issues: list[Issue] = []
    for table_name, date_column in checks.items():
        table = tables.get(table_name)
        if table is None:
            continue
        for row_number, row in enumerate(table.rows, start=2):
            try:
                when = parse_date(row[date_column])
                matches = [
                    symbol
                    for start, end, symbol in master.get(row["symbol_id"], [])
                    if start <= when and (end is None or when < end)
                ]
            except (KeyError, ValueError):
                continue
            if not matches:
                issues.append(Issue("ERROR", "UNKNOWN_SYMBOL_VERSION", table_name, str(row_number), "No symbol-master version is active."))
            elif row.get("symbol") not in matches:
                issues.append(Issue("ERROR", "SYMBOL_CODE_MISMATCH", table_name, str(row_number), f"Expected one of {matches}, got {row.get('symbol')!r}."))
    return issues


def validate_coverage(
    tables: dict[str, CsvTable], research_start: date, research_end: date
) -> list[Issue]:
    issues: list[Issue] = []
    required_ranges = {
        "trading_calendar": "trade_date",
        "ohlcv_raw": "trade_date",
        "index_ohlcv_raw": "trade_date",
        "universe_membership": "valid_from",
    }
    start_tolerance = date.fromordinal(research_start.toordinal() + 10)
    end_tolerance = date.fromordinal(research_end.toordinal() - 10)
    for table_name, column in required_ranges.items():
        table = tables.get(table_name)
        if table is None:
            continue
        values: list[date] = []
        for row in table.rows:
            try:
                values.append(parse_date(row[column]))
            except (KeyError, ValueError):
                continue
        if not values:
            continue
        if min(values) > start_tolerance:
            issues.append(Issue("BLOCKER", "INSUFFICIENT_START_COVERAGE", table_name, min(values).isoformat(), f"Research starts {research_start}."))
        if table_name != "universe_membership" and max(values) < end_tolerance:
            issues.append(Issue("BLOCKER", "INSUFFICIENT_END_COVERAGE", table_name, max(values).isoformat(), f"Research ends {research_end}."))
    return issues


def active_membership_ids(rows: Iterable[dict[str, str]], session: date) -> set[str]:
    active: set[str] = set()
    for row in rows:
        try:
            start = parse_date(row["valid_from"])
            end = parse_date(row["valid_to"]) if row.get("valid_to") else None
        except (KeyError, ValueError):
            continue
        if start <= session and (end is None or session < end):
            active.add(row["symbol_id"])
    return active


def validate_price_coverage(
    memberships: CsvTable, calendar: CsvTable, ohlcv: CsvTable, suspensions: CsvTable
) -> list[Issue]:
    issues: list[Issue] = []
    price_keys = {(row.get("trade_date", ""), row.get("symbol_id", "")) for row in ohlcv.rows}
    suspension_intervals: dict[str, list[tuple[date, date | None]]] = defaultdict(list)
    for row in suspensions.rows:
        try:
            suspension_intervals[row["symbol_id"]].append(
                (
                    parse_date(row["suspended_from"]),
                    parse_date(row["suspended_to"]) if row.get("suspended_to") else None,
                )
            )
        except (KeyError, ValueError):
            continue

    for cal_row in calendar.rows:
        if not is_true(cal_row.get("is_trading_day", "")):
            continue
        try:
            session = parse_date(cal_row["trade_date"])
        except (KeyError, ValueError):
            continue
        for symbol_id in active_membership_ids(memberships.rows, session):
            if (session.isoformat(), symbol_id) in price_keys:
                continue
            is_suspended = any(
                start <= session and (end is None or session <= end)
                for start, end in suspension_intervals.get(symbol_id, [])
            )
            severity = "WARNING" if is_suspended else "ERROR"
            code = "MISSING_PRICE_DURING_SUSPENSION" if is_suspended else "MISSING_ACTIVE_MEMBER_PRICE"
            issues.append(Issue(severity, code, ohlcv.name, f"{session}|{symbol_id}", "No OHLCV bar for active member."))
    return issues


def summarize_issues(issues: Iterable[Issue]) -> dict[str, int]:
    return dict(sorted(Counter(issue.severity for issue in issues).items()))
