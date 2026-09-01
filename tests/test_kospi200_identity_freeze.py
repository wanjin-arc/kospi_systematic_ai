from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load_module():
    path = ROOT / "tools" / "freeze_kospi200_identity_v2.py"
    spec = importlib.util.spec_from_file_location("kospi200_identity_freeze_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Kospi200IdentityFreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def fixture(self, root: Path, *, membership_name: str = "삼성전자") -> tuple[Path, Path, Path]:
        membership = root / "membership" / "2020"
        membership.mkdir(parents=True)
        (membership / "20200102.csv").write_text(f"date,ticker,name\n2020-01-02,005930,{membership_name}\n", encoding="utf-8")
        dart = root / "dart"
        dart.mkdir()
        xml = "<result><list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name><stock_code>005930</stock_code></list></result>"
        with zipfile.ZipFile(dart / "corp_codes.xml.zip", "w") as archive:
            archive.writestr("CORPCODE.xml", xml)
        (dart / "collection_audit.csv").write_text("ticker,corp_code\n005930,00126380\n", encoding="utf-8")
        contract = root / "contract.json"
        contract.write_text(json.dumps({"manual_aliases": {}}), encoding="utf-8")
        return membership.parent, dart, contract

    def test_exact_name_and_unique_corp_are_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            membership, dart, contract = self.fixture(root, membership_name="(주) 삼성전자")
            result = self.module.freeze(membership, dart, contract, root / "out")
            with (root / "out" / "identity_spells.csv").open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(result["confirmed_tickers"], 1)
        self.assertEqual(rows[0]["identity_status"], "CONFIRMED_EXACT_NAME_AND_UNIQUE_CORP")

    def test_name_mismatch_is_not_silently_aliased(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            membership, dart, contract = self.fixture(root, membership_name="다른회사")
            result = self.module.freeze(membership, dart, contract, root / "out")
        self.assertEqual(result["confirmed_tickers"], 0)
        self.assertEqual(result["fully_unresolved_tickers"], 1)

    def test_manual_alias_and_sealed_path_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            membership, dart, contract = self.fixture(root)
            contract.write_text(json.dumps({"manual_aliases": {"005930": "삼성전자"}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.module.freeze(membership, dart, contract, root / "out")
            with self.assertRaises(ValueError):
                self.module.guard_path(Path("data/sealed/final_oos_v24"))


if __name__ == "__main__":
    unittest.main()
