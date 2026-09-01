from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ReceiptOverrideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = load("receipt_override_builder_test", "tools/build_dart_kospi200_receipt_overrides_v2.py")
        cls.normalizer = load("receipt_override_normalizer_test", "tools/normalize_dart_kospi200_fundamentals_v2.py")
        cls.auditor = load("receipt_override_auditor_test", "tools/audit_kospi200_fundamentals_v2.py")

    def make_raw(self, root: Path) -> Path:
        statement = root / "financial_statements" / "00101628" / "2015" / "11011.json"
        statement.parent.mkdir(parents=True)
        statement.write_text(json.dumps({
            "status": "000",
            "_audit": {"ticker": "005930", "corp_code": "00101628", "availability_status": "UNRESOLVED_NOT_MODEL_ELIGIBLE"},
            "list": [{"rcept_no": "20160330001223", "bsns_year": "2015", "account_id": "ifrs-full_Assets", "account_detail": "연결재무제표 [member]", "thstrm_amount": "1"}],
        }), encoding="utf-8")
        listing = root / "disclosures" / "00101628" / "2016.json"
        listing.parent.mkdir(parents=True)
        listing.write_text(json.dumps({"status": "000", "list": [{"rcept_no": "20160330001223", "rcept_dt": "20160330"}]}), encoding="utf-8")
        return statement

    def test_next_calendar_year_receipt_is_resolved_without_mutating_raw(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "raw"
            statement = self.make_raw(root)
            output = Path(directory) / "override"
            report = self.builder.build(root, output)
            overrides = self.normalizer.load_receipt_overrides(output / "receipt_overrides.csv", root)
            rows, audit = self.normalizer.normalize_file(statement, root, overrides, [date(2016, 3, 30), date(2016, 3, 31)])
        self.assertFalse(report["raw_modified"])
        self.assertEqual(audit["receipt_date"], "20160330")
        self.assertEqual(rows[0]["available_from"], "2016-03-31")
        self.assertEqual(rows[0]["availability_status"], "RESOLVED_NEXT_KRX_SESSION_CFS_EVIDENCED")
        self.assertEqual(rows[0]["statement_scope"], "CFS_EVIDENCED")
        self.assertEqual(rows[0]["model_eligible"], "true")

    def test_same_day_never_becomes_available(self) -> None:
        self.assertEqual(self.normalizer.next_session(date(2016, 3, 30), [date(2016, 3, 30), date(2016, 3, 31)]), "2016-03-31")

    def test_hash_mismatch_is_rejected_before_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "raw"
            statement = self.make_raw(root)
            output = Path(directory) / "override"
            self.builder.build(root, output)
            statement.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash"):
                self.normalizer.load_receipt_overrides(output / "receipt_overrides.csv", root)

    def test_no_future_session_is_not_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "raw"
            statement = self.make_raw(root)
            output = Path(directory) / "override"
            self.builder.build(root, output)
            overrides = self.normalizer.load_receipt_overrides(output / "receipt_overrides.csv", root)
            rows, _ = self.normalizer.normalize_file(statement, root, overrides, [date(2016, 3, 30)])
        self.assertEqual(rows[0]["model_eligible"], "false")
        self.assertEqual(rows[0]["availability_status"], "RESOLVED_OUTSIDE_DEVELOPMENT_SESSIONS_NOT_MODEL_ELIGIBLE")

    def test_audit_accepts_only_next_krx_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sessions = root / "membership"
            snapshot = sessions / "2016" / "20160331.csv"
            snapshot.parent.mkdir(parents=True)
            snapshot.write_text("date,ticker\n2016-03-31,005930\n", encoding="utf-8")
            overrides = root / "overrides.csv"
            overrides.write_text("source_file,source_sha256,receipt_date,availability_status\na.json,x,20160330,RESOLVED\n", encoding="utf-8")
            facts = root / "facts.csv"
            facts.write_text(
                "source_file,receipt_date,available_from,availability_status,statement_scope,model_eligible\n"
                "a.json,20160330,2016-03-31,RESOLVED_NEXT_KRX_SESSION_CFS_EVIDENCED,CFS_EVIDENCED,true\n",
                encoding="utf-8",
            )
            result = self.auditor.audit(facts, overrides, sessions)
        self.assertEqual(result["status"], "PASS_PIT_FACTS_MODEL_NOT_STARTED")


if __name__ == "__main__":
    unittest.main()
