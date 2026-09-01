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
MODULE_PATH = ROOT / "tools" / "extract_dart_kospi200_legacy_financials_v1.py"
SPEC = importlib.util.spec_from_file_location("legacy_dart_financials", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class LegacyDartFinancialExtractionTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path, Path]:
        raw = root / "raw"
        documents = raw / "documents" / "2014" / "00126380"
        documents.mkdir(parents=True)
        xml = """<?xml version='1.0'?><DOCUMENT>
        <P>(단위 : 백만원)</P><TABLE><TR><TH>과목</TH><TH>당기</TH><TH>전기</TH></TR>
        <TR><TD>자산 총계</TD><TD>1,000</TD><TD>900</TD></TR>
        <TR><TD>부채총계</TD><TD>400</TD><TD>350</TD></TR>
        <TR><TD>자본총계</TD><TD>600</TD><TD>550</TD></TR>
        <TR><TD>영업이익</TD><TD>(10)</TD><TD>8</TD></TR></TABLE></DOCUMENT>"""
        attachment = """<?xml version='1.0'?><DOCUMENT><P>(단위 : 백만원)</P>
        <TABLE><TR><TH>과목</TH><TH>당기</TH></TR><TR><TD>유동자산</TD><TD>700</TD></TR></TABLE></DOCUMENT>"""
        for receipt in ("20140301000001", "20140305000001"):
            with zipfile.ZipFile(documents / f"{receipt}.zip", "w") as archive:
                archive.writestr(f"{receipt}.xml", xml.encode("cp949"))
                archive.writestr(f"{receipt}_attachment.xml", attachment.encode("cp949"))
        rows = [
            ["005930", "00126380", "2014", "20140301000001", "20140301", "사업보고서 (2013.12)", "ANNUAL", "false", "DOWNLOADED_DOCUMENT", "documents/2014/00126380/20140301000001.zip", "", "FORBIDDEN"],
            ["005930", "00126380", "2014", "20140305000001", "20140305", "[기재정정]사업보고서 (2013.12)", "ANNUAL", "true", "DOWNLOADED_DOCUMENT", "documents/2014/00126380/20140305000001.zip", "", "FORBIDDEN"],
        ]
        with (raw / "document_audit.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["ticker", "corp_code", "year", "rcept_no", "rcept_dt", "report_nm", "report_kind", "is_correction", "document_status", "document_path", "error_path", "factor_usage"])
            writer.writerows(rows)
        (raw / "manifest.json").write_text(json.dumps({"coverage": {"start_year": 2011, "end_year": 2014}}), encoding="utf-8")
        membership = root / "membership"
        membership.mkdir()
        (membership / "20140303.csv").write_text("date,ticker,name\n2014-03-03,005930,삼성전자\n", encoding="utf-8")
        (membership / "20140306.csv").write_text("date,ticker,name\n2014-03-06,005930,삼성전자\n", encoding="utf-8")
        identity = root / "identity.csv"
        identity.write_text(
            "ticker,corp_code,first_date,last_date,identity_status,model_eligible\n"
            "005930,00126380,2004-01-02,2023-12-28,CONFIRMED_EXACT_NAME_AND_UNIQUE_CORP,true\n",
            encoding="utf-8",
        )
        return raw, membership, identity

    def test_strict_labels_units_pit_and_correction_are_audited(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw, membership, identity = self.fixture(root)
            result = module.run(raw, membership, identity, root / "out")
            with (root / "out" / "legacy_financial_selected.csv").open(encoding="utf-8") as handle:
                selected = list(csv.DictReader(handle))
            with (root / "out" / "legacy_document_numeric_audit.csv").open(encoding="utf-8") as handle:
                documents = list(csv.DictReader(handle))
        self.assertEqual(result["status"], "PASS_CANDIDATE_EXTRACTION_MODEL_INPUT_FORBIDDEN")
        self.assertEqual(result["model_eligible_rows"], 0)
        self.assertEqual({row["canonical_candidate"] for row in selected}, {"assets", "liabilities", "equity", "operating_income", "current_assets"})
        self.assertEqual({row["rcept_no"] for row in selected}, {"20140305000001"})
        self.assertEqual({row["available_from"] for row in selected}, {"2014-03-06"})
        self.assertEqual({row["amount_krw_candidate"] for row in selected if row["canonical_candidate"] == "assets"}, {"1000000000"})
        self.assertTrue(all(row["model_eligible"] == "false" for row in selected))
        self.assertTrue(all(row["xml_payload_count"] == "2" for row in documents))

    def test_same_fixture_is_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw, membership, identity = self.fixture(root)
            first = module.run(raw, membership, identity, root / "out1")
            second = module.run(raw, membership, identity, root / "out2")
        self.assertEqual(first["outputs"], second["outputs"])

    def test_partial_word_and_percent_are_not_numeric_account_values(self) -> None:
        self.assertEqual(module.compact("1. 자 산 총 계"), "자산총계")
        self.assertIsNone(module.number("5%"))
        self.assertIsNone(module.number("2014.03.05"))
        self.assertEqual(module.number("(1,000)"), -1000)

    def test_sealed_path_is_denied(self) -> None:
        with self.assertRaises(ValueError):
            module.guard_path(Path("data/sealed/final_oos_v24"))


if __name__ == "__main__":
    unittest.main()
