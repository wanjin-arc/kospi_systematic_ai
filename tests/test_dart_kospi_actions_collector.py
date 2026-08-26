from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def load_collector():
    path = Path(__file__).parents[1] / "tools" / "collect_dart_kospi_actions_v25.py"
    spec = importlib.util.spec_from_file_location("dart_kospi_actions_collector_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DartKospiActionsCollectorTests(unittest.TestCase):
    def test_unavailable_original_document_is_an_audit_record_not_a_run_failure(self) -> None:
        collector = load_collector()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(collector, "request_bytes", return_value=b'{"status":"014","message":"not available"}'):
                document, status, error = collector.save_document("x" * 40, "20140828000779", root)
            self.assertEqual(document, "")
            self.assertEqual(status, "DOCUMENT_UNAVAILABLE")
            self.assertEqual(error, "document_errors/20140828000779.json")
            payload = json.loads((root / error).read_text(encoding="utf-8"))
            self.assertEqual(payload["receipt_no"], "20140828000779")

    def test_action_keyword_filter_includes_split(self) -> None:
        collector = load_collector()
        self.assertTrue(collector.is_action_candidate({"report_nm": "회사분할 결정", "rm": ""}))
        self.assertFalse(collector.is_action_candidate({"report_nm": "사업보고서", "rm": ""}))


    def test_structured_endpoints_use_current_open_dart_paths(self) -> None:
        collector = load_collector()
        self.assertEqual(collector.STRUCTURED_ENDPOINTS["company_split"], "cmpDvDecsn.json")
        self.assertEqual(collector.STRUCTURED_ENDPOINTS["split_merger"], "cmpDvMgDecsn.json")
        self.assertEqual(collector.STRUCTURED_ENDPOINTS["share_exchange_transfer"], "stkExtrDecsn.json")


if __name__ == "__main__":
    unittest.main()
