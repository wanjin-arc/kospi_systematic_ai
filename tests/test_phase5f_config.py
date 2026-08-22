from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from kospi100_temporal_risk.cli import build_parser
from kospi100_temporal_risk.config import EXPERIMENT_ID, load_config
from kospi100_temporal_risk.runner import confirm_development_test


CONFIG = Path("configs/phase5f_temporal_risk.json")


class Phase5FConfigTests(unittest.TestCase):
    def test_preregistered_contract_is_fixed(self) -> None:
        config = load_config(CONFIG)
        self.assertEqual(config.experiment_id, EXPERIMENT_ID)
        self.assertEqual(len(config.stock_features), 8)
        self.assertEqual(len(config.regime_features), 5)
        self.assertEqual(config.temporal_sessions, 20)
        self.assertEqual(config.base.purge_sessions, 20)
        self.assertEqual(config.base.embargo_sessions, 20)
        self.assertEqual(config.entry_net_excess, 0.003)
        self.assertEqual(config.entry_median_net_excess, 0.0)
        self.assertEqual(config.anomaly_quantile, 0.05)
        self.assertEqual(config.maximum_entry_candidates, 10)
        self.assertEqual(config.base.maximum_permitted_date.isoformat(), "2021-12-31")

    def test_forbidden_partition_and_date_fail_closed(self) -> None:
        payload = json.loads(CONFIG.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.json"
            for field, value in (
                ("data_root", "data/processed/v24/development"),
                ("maximum_permitted_date", "2023-12-31"),
                ("development_test_access", True),
            ):
                changed = dict(payload)
                changed[field] = value
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaises(PermissionError):
                    load_config(path)

    def test_model_and_threshold_changes_are_rejected(self) -> None:
        payload = json.loads(CONFIG.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.json"
            changed = json.loads(json.dumps(payload))
            changed["models"]["max_depth"] = 3
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(path)
            changed = json.loads(json.dumps(payload))
            changed["anomaly_veto"]["threshold_quantile"] = 0.10
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(path)

    def test_development_test_is_unconditionally_denied(self) -> None:
        with self.assertRaises(PermissionError):
            confirm_development_test(CONFIG)

    def test_cli_contract_and_package_source_boundary(self) -> None:
        args = build_parser().parse_args(["run", "--config", str(CONFIG), "--output", "out"])
        self.assertEqual(args.command, "run")
        package = Path("src/kospi100_temporal_risk")
        combined = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
        self.assertNotIn("final_oos_v24", combined.lower())
        self.assertNotIn("2022-01-01", combined)


if __name__ == "__main__":
    unittest.main()
