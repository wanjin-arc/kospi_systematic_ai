from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from kospi100_multihorizon.cli import build_parser
from kospi100_multihorizon.config import EXPERIMENT_ID, load_config
from kospi100_multihorizon.runner import confirm_development_test


CONFIG = Path("configs/phase5g_multihorizon_consensus.json")


class Phase5GConfigTests(unittest.TestCase):
    def test_preregistered_contract_is_fixed(self) -> None:
        config = load_config(CONFIG)
        self.assertEqual(config.experiment_id, EXPERIMENT_ID)
        self.assertEqual(config.horizons, (5, 10, 20))
        self.assertEqual(len(config.base.stock_features), 21)
        self.assertEqual(len(config.base.regime_features), 5)
        self.assertEqual(len(config.base.interactions), 6)
        self.assertEqual(config.minimum_positive_horizons, 2)
        self.assertEqual(config.entry_median_net_excess, 0.002)
        self.assertEqual(config.base.maximum_permitted_date.isoformat(), "2018-12-31")
        self.assertEqual(config.base.purge_sessions, 20)
        self.assertEqual(config.base.embargo_sessions, 20)

    def test_forbidden_partition_and_dates_fail_closed(self) -> None:
        payload = json.loads(CONFIG.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.json"
            for field, value in (
                ("data_root", "data/processed/v24/development"),
                ("maximum_permitted_date", "2021-12-31"),
                ("development_test_access", True),
            ):
                changed = dict(payload)
                changed[field] = value
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaises(PermissionError):
                    load_config(path)

    def test_model_target_and_policy_changes_are_rejected(self) -> None:
        payload = json.loads(CONFIG.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.json"
            for section, field, value in (
                ("model", "max_depth", 7),
                ("target", "horizons", [5, 20]),
                ("consensus_policy", "entry_minimum_median_net_excess", 0.001),
            ):
                changed = json.loads(json.dumps(payload))
                changed[section][field] = value
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_config(path)

    def test_development_test_is_denied_and_cli_is_registered(self) -> None:
        with self.assertRaises(PermissionError):
            confirm_development_test(CONFIG)
        args = build_parser().parse_args(["run", "--config", str(CONFIG), "--output", "out"])
        self.assertEqual(args.command, "run")
        package = Path("src/kospi100_multihorizon")
        combined = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
        self.assertNotIn("final_oos_v24", combined.lower())
        self.assertNotIn("2022-01-01", combined)


if __name__ == "__main__":
    unittest.main()
