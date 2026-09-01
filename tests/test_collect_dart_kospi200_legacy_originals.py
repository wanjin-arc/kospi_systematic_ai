from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "collect_dart_kospi200_legacy_originals_v1.py"
SPEC = importlib.util.spec_from_file_location("legacy_dart_collector", MODULE_PATH)
assert SPEC and SPEC.loader
collector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = collector
SPEC.loader.exec_module(collector)


class LegacyDartCollectorTests(unittest.TestCase):
    def test_financial_report_selection_and_correction_audit(self) -> None:
        annual = {"rcept_no": "1", "report_nm": "[기재정정]사업보고서 (2013.12)"}
        half = {"rcept_no": "2", "report_nm": "반기보고서 (2014.06)"}
        quarter = {"rcept_no": "3", "report_nm": "분기보고서 (2014.03)"}
        non_financial = {"rcept_no": "4", "report_nm": "주요사항보고서"}
        self.assertTrue(collector.is_financial_report(annual))
        self.assertEqual(collector.report_kind(annual), "ANNUAL")
        self.assertEqual(collector.report_kind(half), "HALF")
        self.assertEqual(collector.report_kind(quarter), "QUARTERLY")
        self.assertFalse(collector.is_financial_report(non_financial))

    def test_only_historical_membership_tickers_are_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "membership.csv").write_text(
                "date,ticker,name\n2011-01-03,005930,삼성전자\n2015-01-02,000660,SK하이닉스\n",
                encoding="utf-8",
            )
            self.assertEqual(collector.load_membership_tickers(root, 2011, 2014), {"005930"})

    def test_nonzip_dart_document_is_not_accepted_as_original(self) -> None:
        self.assertTrue(collector.looks_like_zip(b"PK\\x03\\x04"))
        self.assertFalse(collector.looks_like_zip(b'{"status":"101"}'))

    def test_2015_or_later_is_rejected_before_api_key_prompt(self) -> None:
        with self.assertRaises(SystemExit):
            collector.main(["--end-year", "2015"])


if __name__ == "__main__":
    unittest.main()
