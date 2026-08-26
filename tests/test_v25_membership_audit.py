from __future__ import annotations

import csv
import gzip
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load_tool():
    path = ROOT / "tools" / "audit_v25_membership_corporate_actions.py"
    spec = importlib.util.spec_from_file_location("membership_audit_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class V25MembershipAuditTests(unittest.TestCase):
    def test_official_99_membership_is_a_valid_partial_snapshot(self) -> None:
        tool = load_tool()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            membership = root / "membership.csv"
            with membership.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["date", "ticker", "is_member", "source", "official_count"])
                for number in range(1, 100):
                    writer.writerow(["2017-05-11", f"{number:06d}", "True", "KRX_11006", "99"])
            market = root / "krx" / "raw" / "market_stk" / "2017"
            market.mkdir(parents=True)
            with gzip.open(market / "20170511.csv.gz", "wt", encoding="cp949", newline="") as handle:
                handle.write("ticker,name\n" + "".join(f"{number:06d},One\n" for number in range(1, 100)))
            dart = root / "dart"; dart.mkdir()
            (dart / "corporate_action_candidates.csv").write_text("ticker,corp_code,rcept_no,rcept_dt,report_nm,document_status\n", encoding="utf-8")
            tool.main(["--membership", str(membership), "--krx-root", str(root / "krx"), "--dart-root", str(dart), "--output-root", str(root / "out")])
            with (root / "out" / "membership_date_audit.csv").open(encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["coverage_status"], "OFFICIAL_PARTIAL_99")
            self.assertEqual(row["membership_count_ok"], "True")

    def test_iso_membership_date_matches_compact_krx_filename(self) -> None:
        tool = load_tool()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            membership = root / "membership.csv"
            with membership.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["date", "ticker", "is_member"])
                writer.writerow(["2011-01-03", "000001", "True"])
            market = root / "krx" / "raw" / "market_stk" / "2011"
            market.mkdir(parents=True)
            with gzip.open(market / "20110103.csv.gz", "wt", encoding="cp949", newline="") as handle:
                handle.write("ticker,name\n000001,One\n000002,Two\n")
            dart = root / "dart"
            dart.mkdir()
            (dart / "corporate_action_candidates.csv").write_text(
                "ticker,corp_code,rcept_no,rcept_dt,report_nm,document_status\n", encoding="utf-8"
            )
            result = tool.main(["--membership", str(membership), "--krx-root", str(root / "krx"), "--dart-root", str(dart), "--output-root", str(root / "out")])
            self.assertEqual(result, 0)
            manifest = json.loads((root / "out" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["membership_ticker_rows_missing_from_krx"], 0)
            self.assertEqual(manifest["krx_dates_without_membership"], 0)


if __name__ == "__main__":
    unittest.main()
