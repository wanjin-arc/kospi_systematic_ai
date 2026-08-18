from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from kospi100_data.normalize_user_exports import normalize_exports


class NormalizeUserExportsTests(unittest.TestCase):
    def test_normalizes_intervals_calendar_and_index_units(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            membership = root / "membership.csv"
            index = root / "index.csv"
            incoming = root / "data" / "incoming"
            manifest = root / "data" / "manifests" / "source_manifest.csv"
            profile = root / "data" / "quality" / "source_profile.json"
            with membership.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["date", "ticker", "name", "is_member"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"date": "2023-01-06", "ticker": "000001", "name": "Alpha", "is_member": "1"},
                        {"date": "2023-01-09", "ticker": "000001", "name": "Alpha New", "is_member": "1"},
                        {"date": "2023-01-10", "ticker": "000002", "name": "Beta", "is_member": "1"},
                    ]
                )
            with index.open("w", encoding="cp949", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "일자",
                        "종가",
                        "대비",
                        "등락률",
                        "시가",
                        "고가",
                        "저가",
                        "거래량(천주)",
                        "거래대금(백만원)",
                        "상장시가총액",
                    ],
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {
                            "일자": "2023-01-10",
                            "종가": "102",
                            "대비": "2",
                            "등락률": "2",
                            "시가": "100",
                            "고가": "103",
                            "저가": "99",
                            "거래량(천주)": "5",
                            "거래대금(백만원)": "7",
                            "상장시가총액": "1000",
                        },
                        {
                            "일자": "2023-01-06",
                            "종가": "100",
                            "대비": "0",
                            "등락률": "0",
                            "시가": "100",
                            "고가": "100",
                            "저가": "100",
                            "거래량(천주)": "4",
                            "거래대금(백만원)": "6",
                            "상장시가총액": "900일자",
                        },
                    ]
                )

            result = normalize_exports(
                membership,
                index,
                incoming,
                manifest,
                profile,
                received_at_kst="2026-08-16T15:10:00+09:00",
            )

            self.assertEqual(result["membership"]["source_rows"], 3)
            with (incoming / "universe_membership.csv").open(encoding="utf-8", newline="") as handle:
                membership_rows = list(csv.DictReader(handle))
            self.assertEqual(len(membership_rows), 3)
            self.assertEqual(membership_rows[0]["valid_to"], "2023-01-09")
            self.assertEqual(membership_rows[1]["effective_date"], "2023-01-06")
            self.assertEqual(membership_rows[2]["symbol_id"], "KRX_CODE:000002")

            with (incoming / "index_ohlcv_raw.csv").open(encoding="utf-8", newline="") as handle:
                index_rows = list(csv.DictReader(handle))
            self.assertEqual([row["trade_date"] for row in index_rows], ["2023-01-06", "2023-01-10"])
            self.assertEqual(index_rows[0]["volume"], "4000")
            self.assertEqual(index_rows[0]["traded_value"], "6000000")
            self.assertEqual(
                result["index"]["concatenated_header_markers_removed_from_unused_market_cap_field"], 1
            )

            with manifest.open(encoding="utf-8", newline="") as handle:
                manifest_rows = list(csv.DictReader(handle))
            self.assertEqual({row["logical_table"] for row in manifest_rows}, {
                "symbol_master",
                "universe_membership",
                "trading_calendar",
                "index_ohlcv_raw",
            })


if __name__ == "__main__":
    unittest.main()
