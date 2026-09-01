from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Kospi200KrxCollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load("kospi200_krx_collector_test", "tools/collect_krx_kospi200_v2.py")

    def test_index_code_and_development_boundary(self) -> None:
        self.assertEqual(self.module.KOSPI200_CODE, "1028")
        self.assertEqual(self.module.membership_params(date(2020, 1, 2)), {"trdDd": "20200102", "indIdx": "1", "indIdx2": "028"})
        self.assertEqual(self.module.MAX_DEVELOPMENT_DATE, date(2023, 12, 31))

    def test_membership_preserves_official_vacancy_without_imputation(self) -> None:
        raw = "종목코드,종목명\n005930,삼성전자\n000660,SK하이닉스\n".encode("cp949")
        result = self.module.parse_membership(raw, date(2020, 1, 2))
        self.assertEqual(result["ticker"].tolist(), ["000660", "005930"])

    def test_membership_allows_official_201_constituent_transition(self) -> None:
        rows = ["ISU_SRT_CD,ISU_ABBRV"] + [f"{i:06d},N{i}" for i in range(201)]
        raw = ("\n".join(rows) + "\n").encode("ascii")
        result = self.module.parse_membership(raw, date(2017, 7, 10))
        self.assertEqual(len(result), 201)

    def test_membership_allows_two_hundred_two_transition(self) -> None:
        rows = ["ISU_SRT_CD,ISU_ABBRV"] + [f"{i:06d},N{i}" for i in range(202)]
        result = self.module.parse_membership(("\n".join(rows) + "\n").encode("ascii"), date(2018, 6, 14))
        self.assertEqual(len(result), 202)

    def test_post_2023_argument_is_rejected_before_cookie_prompt(self) -> None:
        with self.assertRaises(SystemExit):
            self.module.main(["--start", "2024-01-01", "--end", "2024-01-02"])

    def test_sessions_come_from_existing_file_names_without_reading_bars(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "2020" / "20200102.csv.gz"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"not a csv")
            sessions = self.module.sessions_from_existing_ohlcv(root, date(2020, 1, 1), date(2020, 1, 31))
        self.assertEqual(sessions, [date(2020, 1, 2)])


class Kospi200DartCollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load("kospi200_dart_collector_test", "tools/collect_dart_kospi200_fundamentals_v2.py")

    def test_standard_api_boundary_and_report_codes(self) -> None:
        self.assertEqual(self.module.MIN_STANDARD_YEAR, 2015)
        self.assertEqual(set(self.module.REPORT_CODES), {"11011", "11012", "11013", "11014"})

    def test_disclosure_receipt_dates_are_required(self) -> None:
        payload = {"status": "000", "list": [{"rcept_no": "20200101000001", "rcept_dt": "20200101"}]}
        self.assertEqual(self.module.disclosure_dates(payload), {"20200101000001": "20200101"})

    def test_pre_2015_is_rejected_before_key_prompt(self) -> None:
        with self.assertRaises(SystemExit):
            self.module.main(["--start-year", "2014", "--end-year", "2015"])


class FundamentalNormalizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load("kospi200_dart_normalizer_test", "tools/normalize_dart_kospi200_fundamentals_v2.py")

    def test_unresolved_availability_is_not_model_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "financial_statements" / "001" / "2020" / "11011.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"status": "000", "_audit": {"ticker": "005930", "availability_status": "UNRESOLVED_NOT_MODEL_ELIGIBLE"}, "list": [{"account_id": "ifrs-full_Assets", "thstrm_amount": "1,000"}]}), encoding="utf-8")
            rows, audit = self.module.normalize_file(path, root)
        self.assertEqual(rows[0]["model_eligible"], "false")
        self.assertFalse(audit["eligible"])


if __name__ == "__main__":
    unittest.main()
