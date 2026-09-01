from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load_module(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class V25CorporateActionToolTests(unittest.TestCase):
    def test_repair_plan_only_includes_invalid_legacy_responses(self) -> None:
        repair = load_module("repair_dart_kospi_structured_v25.py", "repair_tool_test")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bad = root / "source" / "structured" / "company_split" / "00123456"
            good = root / "source" / "structured" / "split_merger" / "00123456"
            bad.mkdir(parents=True); good.mkdir(parents=True)
            (bad / "2020.json").write_text('{"status":"101"}', encoding="utf-8")
            (good / "2020.json").write_text('{"status":"013"}', encoding="utf-8")
            plan = repair.pending_repairs(root / "source", root / "repair")
            self.assertEqual(len(plan), 1)
            self.assertEqual(plan[0]["endpoint"], "cmpDvDecsn.json")

    def test_repair_plan_uses_only_matching_action_candidates(self) -> None:
        repair = load_module("repair_dart_kospi_structured_v25.py", "repair_candidate_tool_test")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source" / "structured" / "company_split" / "00123456"
            source.mkdir(parents=True)
            (source / "2020.json").write_text('{"status":"101"}', encoding="utf-8")
            candidate_csv = root / "source" / "corporate_action_candidates.csv"
            with candidate_csv.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["corp_code", "rcept_dt", "report_nm"])
                writer.writeheader()
                writer.writerow({"corp_code": "00123456", "rcept_dt": "20200101", "report_nm": "유상증자결정"})
            self.assertEqual(repair.pending_repairs(root / "source", root / "repair", candidate_csv=candidate_csv), [])

    def test_audit_never_emits_an_automatic_adjustment(self) -> None:
        audit = load_module("audit_v25_kospi_corporate_actions.py", "audit_tool_test")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "dart").mkdir()
            with (root / "dart" / "corporate_action_candidates.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["ticker", "corp_code", "rcept_no", "rcept_dt", "report_nm", "document_status"])
                writer.writeheader()
                writer.writerow({"ticker": "000001", "corp_code": "00123456", "rcept_no": "20200101000001", "rcept_dt": "20200101", "report_nm": "무상증자결정", "document_status": "DOCUMENT_ARCHIVED"})
            result = audit.main(["--dart-root", str(root / "dart"), "--output-root", str(root / "out")])
            self.assertEqual(result, 0)
            manifest = json.loads((root / "out" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["automatic_adjustments_emitted"], 0)
            with (root / "out" / "corporate_action_resolution.csv").open(encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["resolution_status"], "UNRESOLVED_BLOCK_IF_IN_UNIVERSE")


if __name__ == "__main__":
    unittest.main()
