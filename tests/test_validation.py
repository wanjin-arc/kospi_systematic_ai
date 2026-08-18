from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from kospi100_data.pipeline import _clean_ohlcv
from kospi100_data.validation import CsvTable, active_membership_ids, validate_calendar, validate_ohlcv


class ValidationTests(unittest.TestCase):
    def make_ohlcv(self, rows: list[dict[str, str]]) -> CsvTable:
        columns = [
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
        ]
        return CsvTable("ohlcv_raw", Path("fixture.csv"), columns, rows, "fixture")

    def test_rejects_invalid_ohlc_and_duplicate(self) -> None:
        row = {
            "trade_date": "2023-01-02",
            "symbol_id": "KR000001",
            "symbol": "000001",
            "open": "110",
            "high": "100",
            "low": "105",
            "close": "95",
            "volume": "-1",
            "traded_value": "1000",
            "market_status": "TRADING",
            "source_file": "synthetic",
            "source_sha256": "x",
        }
        issues = validate_ohlcv(self.make_ohlcv([row, dict(row)]), ("trade_date", "symbol_id"))
        codes = {issue.code for issue in issues}
        self.assertIn("DUPLICATE_BAR", codes)
        self.assertIn("HIGH_BELOW_LOW", codes)
        self.assertIn("OHLC_RANGE_ERROR", codes)
        self.assertIn("NEGATIVE_ACTIVITY", codes)

    def test_membership_is_point_in_time(self) -> None:
        memberships = [
            {"symbol_id": "A", "valid_from": "2023-01-01", "valid_to": "2023-06-01"},
            {"symbol_id": "B", "valid_from": "2023-06-01", "valid_to": ""},
        ]
        self.assertEqual(active_membership_ids(memberships, date(2023, 5, 31)), {"A"})
        self.assertEqual(active_membership_ids(memberships, date(2023, 6, 1)), {"B"})

    def test_calendar_reports_missing_session_metadata_once(self) -> None:
        rows = [
            {
                "trade_date": session,
                "is_trading_day": "1",
                "market_open_kst": "",
                "market_close_kst": "",
                "is_early_close": "",
            }
            for session in ("2023-01-02", "2023-01-03")
        ]
        table = CsvTable("trading_calendar", Path("calendar.csv"), list(rows[0]), rows, "fixture")
        issues = validate_calendar(table)
        self.assertEqual([issue.code for issue in issues], ["MISSING_SESSION_TIMES", "UNKNOWN_EARLY_CLOSE_FLAGS"])
        self.assertIn("2 trading sessions", issues[0].message)

    def test_split_adjustment_uses_only_effective_actions(self) -> None:
        memberships = [
            {"symbol_id": "A", "valid_from": "2023-01-01", "valid_to": ""},
        ]
        rows = [
            {
                "trade_date": "2023-01-02",
                "symbol_id": "A",
                "symbol": "000001",
                "open": "100",
                "high": "100",
                "low": "100",
                "close": "100",
                "volume": "10",
                "traded_value": "1000",
                "market_status": "TRADING",
                "source_file": "synthetic",
                "source_sha256": "x",
            },
            {
                "trade_date": "2023-01-03",
                "symbol_id": "A",
                "symbol": "000001",
                "open": "50",
                "high": "50",
                "low": "50",
                "close": "50",
                "volume": "20",
                "traded_value": "1000",
                "market_status": "TRADING",
                "source_file": "synthetic",
                "source_sha256": "x",
            },
        ]
        actions = [
            {
                "symbol_id": "A",
                "action_type": "SPLIT",
                "effective_date": "2023-01-03",
                "share_factor_numerator": "2",
                "share_factor_denominator": "1",
            }
        ]
        cleaned = _clean_ohlcv(rows, memberships, actions)
        self.assertEqual(cleaned[0]["adjustment_factor_asof"], "1")
        self.assertEqual(cleaned[1]["adjustment_factor_asof"], "2")
        self.assertEqual(cleaned[0]["analysis_close"], "100")
        self.assertEqual(cleaned[1]["analysis_close"], "100")
        self.assertEqual(cleaned[1]["analysis_volume"], "10")


if __name__ == "__main__":
    unittest.main()
