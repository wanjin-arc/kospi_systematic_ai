from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from kospi200_phase5r.config import EXPERIMENT_ID, guard_path, load_config
from kospi200_phase5r.data import (
    FUNDAMENTAL_FEATURES,
    discover_year_partition_files,
    repercentile_fundamental_panel,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "v2_phase5r_integrity_soft_fusion.json"


class Phase5RConfigTests(unittest.TestCase):
    def test_frozen_config_loads_and_separates_development_from_external_execution(self) -> None:
        config = load_config(CONFIG)
        self.assertEqual(config.experiment_id, EXPERIMENT_ID)
        self.assertEqual(config.data_end.isoformat(), "2023-12-28")
        self.assertEqual(config.evaluation_start.isoformat(), "2021-01-04")
        self.assertEqual(config.excluded_tickers, frozenset({"005930", "000660"}))
        self.assertTrue(config.payload["development_backtest_approved"])
        self.assertFalse(config.payload["external_portfolio_execution_approved"])

    def test_protected_oos_path_is_fail_closed_case_insensitively(self) -> None:
        for path in (
            Path("data/sealed/final_oos_v24/panel.csv"),
            Path("DATA/SEALED/FINAL_OOS_V24/panel.csv"),
        ):
            with self.assertRaises(PermissionError):
                guard_path(path)

    def test_changed_approval_or_exclusions_are_rejected(self) -> None:
        payload = json.loads(CONFIG.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            payload["development_backtest_approved"] = False
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(PermissionError):
                load_config(path)
            payload["development_backtest_approved"] = True
            payload["excluded_securities"] = payload["excluded_securities"][:1]
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(path)

    def test_existing_percentile_or_changed_feature_contract_is_rejected(self) -> None:
        payload = json.loads(CONFIG.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            payload["agent_b"]["feature_suffix"] = "__percentile"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(path)

    def test_partition_discovery_does_not_return_post_boundary_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for year in (2023, 2024):
                (root / str(year)).mkdir()
            for name in ("20231228.csv", "20231229.csv"):
                (root / "2023" / name).write_text("x\n", encoding="utf-8")
            (root / "2024" / "20240102.csv").write_text("x\n", encoding="utf-8")
            paths = discover_year_partition_files(root, date(2023, 1, 1), date(2023, 12, 28), "*.csv")
            self.assertEqual([path.name for path in paths], ["20231228.csv"])
            with self.assertRaises(PermissionError):
                discover_year_partition_files(root, date(2023, 1, 1), date(2024, 1, 2), "*.csv")

    def test_fundamental_percentiles_are_recomputed_after_exclusions(self) -> None:
        rows = []
        for ticker, value in (("111111", 1.0), ("222222", 2.0), ("005930", 100.0)):
            row = {"date": "2020-01-02", "ticker": ticker, "roe__percentile": 0.123}
            row.update({factor: value for factor in FUNDAMENTAL_FEATURES})
            rows.append(row)
        result = repercentile_fundamental_panel(pd.DataFrame(rows))
        self.assertEqual(result["ticker"].tolist(), ["111111", "222222"])
        self.assertEqual(result["roe__phase4e_percentile"].tolist(), [0.5, 1.0])
        self.assertNotIn("roe__percentile", result.columns)


if __name__ == "__main__":
    unittest.main()
