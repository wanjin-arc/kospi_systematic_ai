from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "phase1-v1"


@dataclass(frozen=True)
class TableSpec:
    filename: str
    required_columns: tuple[str, ...]
    allow_empty: bool = False


TABLE_SPECS: dict[str, TableSpec] = {
    "symbol_master": TableSpec(
        "symbol_master.csv",
        (
            "symbol_id",
            "symbol",
            "isin",
            "company_name",
            "valid_from",
            "valid_to",
            "listing_date",
            "delisting_date",
            "source_file",
            "source_sha256",
        ),
    ),
    "universe_membership": TableSpec(
        "universe_membership.csv",
        (
            "index_name",
            "index_code",
            "symbol_id",
            "symbol",
            "company_name",
            "valid_from",
            "valid_to",
            "announcement_at",
            "effective_date",
            "source_file",
            "source_sha256",
            "retrieved_at_kst",
        ),
    ),
    "trading_calendar": TableSpec(
        "trading_calendar.csv",
        (
            "trade_date",
            "is_trading_day",
            "market_open_kst",
            "market_close_kst",
            "is_early_close",
            "source_file",
            "source_sha256",
        ),
    ),
    "ohlcv_raw": TableSpec(
        "ohlcv_raw.csv",
        (
            "trade_date",
            "symbol_id",
            "symbol",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "traded_value",
            "market_status",
            "source_file",
            "source_sha256",
        ),
    ),
    "index_ohlcv_raw": TableSpec(
        "index_ohlcv_raw.csv",
        (
            "trade_date",
            "index_code",
            "index_name",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "traded_value",
            "source_file",
            "source_sha256",
        ),
    ),
    "corporate_actions": TableSpec(
        "corporate_actions.csv",
        (
            "symbol_id",
            "symbol",
            "action_type",
            "announcement_at",
            "effective_date",
            "share_factor_numerator",
            "share_factor_denominator",
            "cash_amount",
            "currency",
            "source_file",
            "source_sha256",
        ),
        allow_empty=True,
    ),
    "suspensions": TableSpec(
        "suspensions.csv",
        (
            "symbol_id",
            "symbol",
            "suspended_from",
            "suspended_to",
            "reason",
            "source_file",
            "source_sha256",
        ),
        allow_empty=True,
    ),
}

PRICE_COLUMNS = ("open", "high", "low", "close")
SPLIT_ACTION_TYPES = {"SPLIT", "REVERSE_SPLIT", "STOCK_DIVIDEND"}

SOURCE_MANIFEST_COLUMNS = (
    "logical_table",
    "local_file",
    "source_organization",
    "source_product",
    "source_url",
    "retrieved_at_kst",
    "coverage_start",
    "coverage_end",
    "row_count",
    "sha256",
    "licence_or_terms_reference",
    "notes",
)
