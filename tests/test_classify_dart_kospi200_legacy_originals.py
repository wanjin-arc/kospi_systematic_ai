from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "classify_dart_kospi200_legacy_originals_v1.py"
SPEC = importlib.util.spec_from_file_location("legacy_dart_classifier", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class LegacyDartClassifierTests(unittest.TestCase):
    def test_cp949_table_xml_is_classified_without_numeric_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sample.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("sample.xml", "<?xml version='1.0'?><DOCUMENT><TABLE><TD>자산총계</TD></TABLE></DOCUMENT>".encode("cp949"))
            result = module.classify_zip(path)
            self.assertEqual(result["detected_encoding"], "CP949")
            self.assertEqual(result["structure"], "LEGACY_TABLE_XML_REQUIRES_NUMERIC_ACCOUNT_REVIEW")

    def test_xbrl_is_not_silently_treated_as_legacy_table(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sample.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("sample.xml", "<xbrl xmlns='http://www.xbrl.org/2003/instance'></xbrl>")
            self.assertEqual(module.classify_zip(path)["structure"], "XBRL_OR_INLINE_XBRL_REQUIRES_SEPARATE_PARSER")

    def test_sealed_path_is_denied(self) -> None:
        with self.assertRaises(ValueError):
            module.guard(Path("data/sealed/final_oos_v24"))


if __name__ == "__main__":
    unittest.main()
