from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE = Path("tools/build_kospi200_legacy_canonical_fundamentals_v1.py")
SPEC = importlib.util.spec_from_file_location("legacy_canonical", MODULE)
assert SPEC and SPEC.loader
legacy_canonical = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(legacy_canonical)


class LegacyCanonicalTests(unittest.TestCase):
    def _row(self, **updates: str) -> dict[str, str]:
        row = {
            "ticker": "005930", "corp_code": "00126380", "rcept_no": "20110516000001", "rcept_dt": "20110516",
            "available_from": "2011-05-17", "document_path": "documents/2011/x.zip", "source_sha256": "a" * 64,
            "report_period_end": "2011-03-31", "canonical_candidate": "assets", "source_label": "자산총계",
            "reported_unit": "백만원", "amount_krw_candidate": "100000000", "statement_scope": "CFS_EVIDENCED",
            "identity_model_eligible": "true", "latest_logical_filing": "true",
            "selection_status": "UNAMBIGUOUS_CURRENT_FILING_CANDIDATE_NOT_MODEL_ELIGIBLE",
        }
        row.update(updates)
        return row

    def test_only_strict_pit_rows_are_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            selected = root / "selected.csv"
            fields = list(self._row())
            with selected.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
                writer.writerow(self._row())
                writer.writerow(self._row(rcept_no="20110516000002", canonical_candidate="equity", identity_model_eligible="false"))
                writer.writerow(self._row(rcept_no="20110516000003", canonical_candidate="liabilities", reported_unit="", amount_krw_candidate=""))
                writer.writerow(self._row(rcept_no="20110214000004", report_period_end="2010-12-31"))
            contract = root / "contract.json"
            contract.write_text(json.dumps({"source_period":{"min_report_period_end":"2011-03-31","max_report_period_end":"2014-12-31"}, "accounts":["assets","equity","liabilities"], "required_statement_scope":"CFS_EVIDENCED"}), encoding="utf-8")
            result = legacy_canonical.build(selected, contract, root / "out")
            self.assertTrue(result["status"].startswith("PASS"))
            self.assertEqual(result["output_rows"], 1)
            self.assertEqual(result["rejected_rows"]["unresolved_identity"], 1)
            self.assertEqual(result["rejected_rows"]["unknown_unit"], 1)
            self.assertEqual(result["rejected_rows"]["outside_ifrs_legacy_period"], 1)

    def test_oos_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(ValueError):
                legacy_canonical.build(root / "sealed" / "final_oos_v24" / "input.csv", root / "x.json", root / "out")


if __name__ == "__main__":
    unittest.main()
