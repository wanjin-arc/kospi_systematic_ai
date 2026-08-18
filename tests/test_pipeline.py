from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from kospi100_data.access import FinalOOSAccessError, PointInTimeDataset
from kospi100_data.pipeline import Phase1Pipeline
from kospi100_data.schema import TABLE_SPECS


class PipelineTests(unittest.TestCase):
    def write_csv(self, root: Path, table_name: str, rows: list[dict[str, str]]) -> None:
        spec = TABLE_SPECS[table_name]
        path = root / spec.filename
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=spec.required_columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def source_fields(self) -> dict[str, str]:
        return {"source_file": "synthetic-test-only", "source_sha256": "a" * 64}

    def create_complete_fixture(self, root: Path) -> None:
        manifest_dir = root.parent / "manifests"
        manifest_dir.mkdir()
        manifest_columns = [
            "logical_table",
            "local_file",
            "source_organization",
            "source_product",
            "source_url",
            "retrieved_at_kst",
            "coverage_start",
            "coverage_end",
            "row_count",
            "sha256",
            "licence_or_terms_reference",
            "notes",
        ]
        with (manifest_dir / "source_manifest.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=manifest_columns, lineterminator="\n")
            writer.writeheader()
            for table_name in TABLE_SPECS:
                writer.writerow(
                    {
                        "logical_table": table_name,
                        "local_file": "synthetic-test-only",
                        "source_organization": "synthetic",
                        "source_product": "unit-test",
                        "source_url": "none",
                        "retrieved_at_kst": "2026-08-16T12:00:00+09:00",
                        "coverage_start": "2023-01-01",
                        "coverage_end": "2024-01-02",
                        "row_count": "0",
                        "sha256": "a" * 64,
                        "licence_or_terms_reference": "none",
                        "notes": "synthetic test only",
                    }
                )
        self.write_csv(
            root,
            "symbol_master",
            [
                {
                    "symbol_id": symbol_id,
                    "symbol": symbol,
                    "isin": f"ISIN{symbol_id}",
                    "company_name": symbol_id,
                    "valid_from": "2023-01-01",
                    "valid_to": "",
                    "listing_date": "2020-01-01",
                    "delisting_date": "",
                    **self.source_fields(),
                }
                for symbol_id, symbol in (("A", "000001"), ("B", "000002"))
            ],
        )
        self.write_csv(
            root,
            "universe_membership",
            [
                {
                    "index_name": "KOSPI 100",
                    "index_code": "TEST",
                    "symbol_id": symbol_id,
                    "symbol": symbol,
                    "company_name": symbol_id,
                    "valid_from": "2023-01-01",
                    "valid_to": "",
                    "announcement_at": "2022-12-01T12:00:00+09:00",
                    "effective_date": "2023-01-01",
                    "retrieved_at_kst": "2026-08-16T12:00:00+09:00",
                    **self.source_fields(),
                }
                for symbol_id, symbol in (("A", "000001"), ("B", "000002"))
            ],
        )
        self.write_csv(
            root,
            "trading_calendar",
            [
                {
                    "trade_date": session,
                    "is_trading_day": "1",
                    "market_open_kst": "09:00:00",
                    "market_close_kst": "15:30:00",
                    "is_early_close": "0",
                    **self.source_fields(),
                }
                for session in ("2023-12-29", "2024-01-02")
            ],
        )
        bars: list[dict[str, str]] = []
        for session in ("2023-12-29", "2024-01-02"):
            for symbol_id, symbol, price in (("A", "000001", "100"), ("B", "000002", "200")):
                bars.append(
                    {
                        "trade_date": session,
                        "symbol_id": symbol_id,
                        "symbol": symbol,
                        "open": price,
                        "high": price,
                        "low": price,
                        "close": price,
                        "volume": "10",
                        "traded_value": "1000",
                        "market_status": "TRADING",
                        **self.source_fields(),
                    }
                )
        self.write_csv(root, "ohlcv_raw", bars)
        self.write_csv(
            root,
            "index_ohlcv_raw",
            [
                {
                    "trade_date": session,
                    "index_code": "TEST",
                    "index_name": "KOSPI 100",
                    "open": "1000",
                    "high": "1000",
                    "low": "1000",
                    "close": "1000",
                    "volume": "20",
                    "traded_value": "2000",
                    **self.source_fields(),
                }
                for session in ("2023-12-29", "2024-01-02")
            ],
        )
        self.write_csv(root, "corporate_actions", [])
        self.write_csv(root, "suspensions", [])

    def test_missing_inputs_block_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = Phase1Pipeline(root / "incoming", root / "data", root / "report.json").build()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(any(issue.code == "MISSING_INPUT_FILE" for issue in result.issues))
            self.assertFalse((root / "data" / "processed").exists())

    def test_valid_fixture_builds_and_seals_oos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            incoming = root / "incoming"
            incoming.mkdir()
            self.create_complete_fixture(incoming)
            result = Phase1Pipeline(
                incoming,
                root / "data",
                root / "report.json",
                expected_universe_size=2,
                research_start=date(2023, 12, 29),
                research_end=date(2024, 1, 2),
            ).build()
            self.assertEqual(result.status, "VALID", [issue.to_dict() for issue in result.issues])
            development = root / "data" / "processed" / "development"
            sealed = root / "data" / "sealed" / "final_oos"
            self.assertTrue((development / "ohlcv_clean.csv.gz").exists())
            self.assertTrue((sealed / "ohlcv_clean.csv.gz").exists())
            dataset = PointInTimeDataset(development)
            self.assertEqual(dataset.universe_on(date(2023, 12, 29)), {"A", "B"})
            self.assertEqual(len(dataset.history_through("A", date(2023, 12, 29))), 1)
            with self.assertRaises(FinalOOSAccessError):
                dataset.history_through("A", date(2024, 1, 2))


if __name__ == "__main__":
    unittest.main()
