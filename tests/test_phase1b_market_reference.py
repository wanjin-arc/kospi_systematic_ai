import csv
import gzip
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


TOOL = Path(__file__).resolve().parents[1] / "tools" / "build_phase1b_market_reference.py"
SPEC = importlib.util.spec_from_file_location("phase1b_market_reference", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Phase1BMarketReferenceTests(unittest.TestCase):
    def _write_day(self, root, year, date):
        path = root / "raw" / "market_stk" / str(year) / f"{date}.csv.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="cp949", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["종목코드", "종목명", "종가", "x", "x", "시가", "고가", "저가", "거래량", "거래대금"])
            writer.writerow(["000001", "가", "110", "", "", "100", "112", "99", "10", "1000"])
            writer.writerow(["000002", "나", "95", "", "", "100", "101", "94", "20", "2000"])
        return path

    def test_only_permitted_years_are_opened_and_result_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "raw_root"
            root.mkdir()
            (root / "manifest.json").write_text("{}\n", encoding="utf-8")
            self._write_day(root, 2023, "20230102")
            blocked = self._write_day(root, 2024, "20240102")
            output_a = Path(temp) / "a"
            output_b = Path(temp) / "b"
            MODULE.main(["--raw-root", str(root), "--output-root", str(output_a)])
            MODULE.main(["--raw-root", str(root), "--output-root", str(output_b)])
            self.assertTrue(blocked.exists())
            manifest = json.loads((output_a / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["max_loaded_date"], "2023-01-02")
            self.assertFalse(manifest["post_2023_files_loaded"])
            self.assertEqual((output_a / "all_kospi_market_reference.csv").read_bytes(), (output_b / "all_kospi_market_reference.csv").read_bytes())
            self.assertEqual((output_a / "manifest.json").read_bytes(), (output_b / "manifest.json").read_bytes())

    def test_post_2023_configuration_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "raw_root"
            root.mkdir()
            (root / "manifest.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE.main(["--raw-root", str(root), "--output-root", str(Path(temp) / "out"), "--max-date", "2024-01-01"])
