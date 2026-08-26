from __future__ import annotations

import gzip
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load_audit_module():
    path = ROOT / "tools" / "audit_kospi200_v2_membership.py"
    spec = importlib.util.spec_from_file_location("kospi200_membership_audit_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Kospi200MembershipAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_audit_module()

    def test_audit_preserves_two_hundred_two_member_transition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "input"
            raw = root / "raw" / "membership_1028" / "2018" / "20180614.csv.gz"
            normalized = root / "normalized" / "membership_daily" / "2018" / "20180614.csv"
            raw.parent.mkdir(parents=True)
            normalized.parent.mkdir(parents=True)
            rows = ["ISU_SRT_CD,ISU_ABBRV"] + [f"{number:06d},N{number}" for number in range(202)]
            with gzip.open(raw, "wb") as handle:
                handle.write(("\n".join(rows) + "\n").encode("ascii"))
            normalized.write_text("date,ticker,name\n", encoding="utf-8")
            checkpoint = root / "checkpoints"
            checkpoint.mkdir()
            (checkpoint / "completed_sessions.txt").write_text("20180614\n", encoding="utf-8")
            relative = "raw/membership_1028/2018/20180614.csv.gz"
            manifest = {
                "schema_version": "kospi200-krx-raw-v2",
                "coverage": {"start": "2004-01-02", "end": "2023-12-31"},
                "protected_oos_accessed": False,
                "session_source": {"sessions": 1},
                "raw_files": [{"path": relative, "sha256": self.module.sha256_file(raw)}],
            }
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            result = self.module.audit(root, Path(directory) / "output")
        self.assertEqual(result["status"], "PASS_MEMBERSHIP_ONLY_DART_REQUIRED")
        self.assertEqual(result["official_member_count_distribution"], {"202": 1})

    def test_audit_rejects_sealed_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(PermissionError):
                self.module.audit(Path(directory) / "sealed" / "final_oos_v24", Path(directory) / "output")


if __name__ == "__main__":
    unittest.main()
