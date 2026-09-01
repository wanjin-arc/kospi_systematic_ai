from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load_module():
    path = ROOT / "tools" / "build_kospi200_canonical_fundamentals_v2.py"
    spec = importlib.util.spec_from_file_location("kospi200_canonical_fundamentals_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CanonicalFundamentalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_submember_detail_is_rejected(self) -> None:
        self.assertTrue(self.module.top_level_detail("연결재무제표 [member]"))
        self.assertFalse(self.module.top_level_detail("자본 [member]|비지배지분 [member]"))

    def test_only_identity_and_pit_eligible_standard_ids_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity = root / "identity.csv"
            identity.write_text("ticker,model_eligible\n005930,true\n000660,false\n", encoding="utf-8")
            taxonomy = root / "taxonomy.json"
            taxonomy.write_text(json.dumps({
                "manual_account_name_fallbacks": {},
                "accounts": {"assets": {"statement_div": ["BS"], "account_ids": ["ifrs-full_Assets"]}},
            }), encoding="utf-8")
            facts = root / "facts.csv"
            columns = ["ticker", "corp_code", "receipt_date", "available_from", "statement_scope", "model_eligible", "business_year", "report_code", "statement_div", "account_id", "account_name", "account_detail", "current_amount", "source_file"]
            rows = [
                ["005930", "1", "20200330", "2020-03-31", "CFS_EVIDENCED", "true", "2019", "11011", "BS", "ifrs-full_Assets", "자산총계", "-", "100", "a.json"],
                ["000660", "2", "20200330", "2020-03-31", "CFS_EVIDENCED", "true", "2019", "11011", "BS", "ifrs-full_Assets", "자산총계", "-", "200", "b.json"],
            ]
            with facts.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, lineterminator="\n"); writer.writerow(columns); writer.writerows(rows)
            result = self.module.build(facts, identity, taxonomy, root / "out")
            with (root / "out" / "canonical_financial_accounts.csv").open(encoding="utf-8") as handle:
                output = list(csv.DictReader(handle))
        self.assertEqual(result["status"], "PASS_CANONICAL_ACCOUNTS_MODEL_NOT_STARTED")
        self.assertEqual([row["ticker"] for row in output], ["005930"])

    def test_name_fallback_and_oos_path_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            taxonomy = root / "taxonomy.json"
            taxonomy.write_text(json.dumps({"manual_account_name_fallbacks": {"assets": ["자산"]}, "accounts": {}}), encoding="utf-8")
            identity = root / "identity.csv"; identity.write_text("ticker,model_eligible\n005930,true\n", encoding="utf-8")
            facts = root / "facts.csv"; facts.write_text("ticker\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                self.module.build(facts, identity, taxonomy, root / "out")
            with self.assertRaises(ValueError):
                self.module.guard_path(Path("data/sealed/final_oos_v24"))


if __name__ == "__main__":
    unittest.main()
