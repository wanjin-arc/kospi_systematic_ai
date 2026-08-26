import unittest
from datetime import date

import pandas as pd

import collect_krx_v25_technical as base
from tools.collect_krx_kospi200_sector_v1 import guard_path, parse_sector, sector_params


class Kospi200SectorCollectorTests(unittest.TestCase):
    def test_params_are_historical_pit_query(self):
        self.assertEqual(sector_params(date(2018, 1, 2)), {"mktId": "STK", "trdDd": "20180102", "money": "1"})

    def test_parse_sector_normalizes_ticker_and_preserves_code(self):
        raw = "종목코드,종목명,업종코드,업종\n005930,삼성전자,전자부품,전자부품\n000660,SK하이닉스,전자부품,전자부품\n".encode("cp949")
        result = parse_sector(raw, date(2018, 1, 2))
        self.assertEqual(result["ticker"].tolist(), ["000660", "005930"])
        self.assertEqual(result["sector_code"].tolist(), ["전자부품", "전자부품"])
        self.assertEqual(result["date"].unique().tolist(), ["2018-01-02"])

    def test_missing_sector_columns_fail_closed(self):
        raw = "종목코드,종목명\n005930,삼성전자\n".encode("cp949")
        with self.assertRaises(base.KRXError):
            parse_sector(raw, date(2018, 1, 2))

    def test_sector_name_only_response_uses_explicit_fallback_code(self):
        raw = "종목코드,종목명,시장구분,업종명\n005930,삼성전자,KOSPI,정보기술\n".encode("cp949")
        result = parse_sector(raw, date(2018, 1, 2))
        self.assertEqual(result.loc[0, "sector"], "정보기술")
        self.assertEqual(result.loc[0, "sector_code"], "정보기술")
        self.assertEqual(result.loc[0, "sector_code_source"], "derived_from_sector_name")

    def test_sealed_path_is_rejected_before_io(self):
        with self.assertRaises(base.KRXError):
            guard_path(__import__("pathlib").Path("data/sealed/final_oos_v24"))


if __name__ == "__main__":
    unittest.main()
