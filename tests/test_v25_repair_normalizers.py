from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load_tool(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class V25RepairNormalizerTests(unittest.TestCase):
    def test_official_99_response_is_preserved_and_not_imputed(self) -> None:
        tool = load_tool("normalize_v25_membership.py", "membership_normalizer_test")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "membership.csv"
            source.write_text(
                "date,security_id,ticker,name,membership_spell_id,is_member,eligible_new_entry,tradable\n"
                "2011-03-30,KRX_COMMON:000001,000001,A,000001:01,True,True,True\n"
                "2011-03-31,KRX_COMMON:000001,000001,A,000001:01,True,True,True\n",
                encoding="utf-8",
            )
            repair = root / "repairs"
            repair.mkdir()
            (repair / "membership_repairs.csv").write_text(
                "date,ticker,name,source,official_count\n2011-03-30,000002,B,KRX_11006,99\n",
                encoding="utf-8",
            )
            out = root / "out"
            self.assertEqual(tool.main(["--membership-source", str(source), "--repair-root", str(repair), "--output-root", str(out)]), 0)
            with (out / "membership_daily_v25_candidate.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            repaired = next(row for row in rows if row["date"] == "2011-03-30")
            self.assertEqual(repaired["ticker"], "000002")
            self.assertEqual(repaired["official_count"], "99")
            self.assertEqual(repaired["tradable"], "")
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["imputation_performed"])

    def test_gap_dates_selects_only_99_member_rows(self) -> None:
        tool = load_tool("collect_krx_v25_membership_repairs.py", "membership_repair_test")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "gaps.csv"
            path.write_text("date,count\n2017-05-11,99\n2017-06-09,100\n", encoding="utf-8")
            self.assertEqual([value.isoformat() for value in tool.gap_dates(path)], ["2017-05-11"])

    def test_corporate_action_normalizer_never_promotes_without_terms(self) -> None:
        tool = load_tool("normalize_v25_corporate_actions.py", "corporate_normalizer_test")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "triage.csv"
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["ticker", "corp_code", "rcept_no", "rcept_dt", "event_type_candidate", "document_status", "member_on_filing_date"])
                writer.writeheader()
                writer.writerow({"ticker": "000001", "corp_code": "00123456", "rcept_no": "20200101000001", "rcept_dt": "20200101", "event_type_candidate": "BONUS_ISSUE", "document_status": "DOCUMENT_ARCHIVED", "member_on_filing_date": "True"})
            self.assertEqual(tool.main(["--triage-csv", str(source), "--output-root", str(root / "out")]), 0)
            manifest = json.loads((root / "out" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["promoted_mechanical_adjustments"], 0)
            with (root / "out" / "corporate_actions_v25_unresolved.csv").open(encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["normalization_status"], "UNRESOLVED_MISSING_EFFECTIVE_DATE_RATIO_PIT_IDENTITY")


if __name__ == "__main__":
    unittest.main()
