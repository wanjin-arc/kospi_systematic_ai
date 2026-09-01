from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools" / "collect_krx_v25_technical.py"
SPEC = importlib.util.spec_from_file_location("krx_v25_collector", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
COLLECTOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = COLLECTOR
SPEC.loader.exec_module(COLLECTOR)


class KrxV25CollectorTests(unittest.TestCase):
    def test_cookie_is_normalized_but_not_replaced(self) -> None:
        self.assertEqual(COLLECTOR.clean_cookie("Cookie: JSESSIONID=abc; foo=bar"), "JSESSIONID=abc; foo=bar")
        with self.assertRaises(COLLECTOR.KRXError):
            COLLECTOR.clean_cookie("foo=bar")

    def test_historical_membership_queries_are_not_blocked_by_pykrx_boundary(self) -> None:
        self.assertEqual(COLLECTOR.EXPANSION_END, date(2010, 12, 31))
        args = COLLECTOR.parse_args(["--start", "2000-01-04", "--end", "2000-01-04"])
        self.assertEqual(args.start, date(2000, 1, 4))
        self.assertIsNone(args.legacy_membership)

    def test_empty_or_non_100_membership_is_not_a_successful_snapshot(self) -> None:
        self.assertEqual(len(COLLECTOR.legacy_snapshot(COLLECTOR.pd.DataFrame(columns=["date", "ticker", "name"]), date(2000, 1, 4))), 0)

    def test_market_csv_normalization_keeps_price_and_identity_fields(self) -> None:
        raw = "종목코드,종목명,시장구분,시가,고가,저가,종가,거래량,거래대금,시가총액,상장주식수\n005930,삼성전자,KOSPI,100,110,95,105,10,1000,10000,100\n".encode("cp949")
        result = COLLECTOR.canonical_columns(COLLECTOR.parse_csv(raw))
        self.assertEqual(result.loc[0, "ticker"], "005930")
        self.assertEqual(result.loc[0, "trading_value"], 1000)
        self.assertEqual(result.loc[0, "listed_shares"], 100)

    def test_existing_boolean_membership_export_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "membership.csv"
            path.write_text("date,ticker,name,is_member\n2010-01-04,005930,삼성전자,True\n", encoding="utf-8")
            result = COLLECTOR.load_legacy_membership(path)
        self.assertEqual(result[["date", "ticker"]].to_dict("records"), [{"date": result.iloc[0]["date"], "ticker": "005930"}])

    def test_fundamental_krx_endpoint_is_not_part_of_collector_contract(self) -> None:
        self.assertNotIn("MDCSTAT03501", MODULE_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
