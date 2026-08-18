import json
import tempfile
import unittest
from pathlib import Path

from kospi100_features.config import load_config


CONFIG = Path("configs/phase4_features.json")


class Phase4ConfigTests(unittest.TestCase):
    def test_frozen_phase4_contract_loads(self) -> None:
        config = load_config(CONFIG)
        self.assertEqual(config.experiment_id, "P4-FEATURES-20260818-001")
        self.assertEqual(len(config.features), 21)
        self.assertEqual(len(config.regime_features), 5)
        self.assertEqual(config.purge_sessions, 20)
        self.assertEqual(config.embargo_sessions, 20)
        self.assertEqual(config.minimum_cross_section, 30)
        self.assertEqual(config.hac_lag_sessions, 10)
        self.assertFalse(config.payload["evaluation"]["model_training"])
        self.assertFalse(config.payload["evaluation"]["portfolio_backtest"])

    def test_oos_and_development_test_options_fail_closed(self) -> None:
        payload = json.loads(CONFIG.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            payload["data_root"] = "data/sealed/final_oos_v24"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(PermissionError):
                load_config(path)

            payload["data_root"] = "data/processed/v24/development"
            payload["evaluation"]["development_test_access"] = True
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(PermissionError):
                load_config(path)

    def test_period_or_registered_threshold_change_is_rejected(self) -> None:
        payload = json.loads(CONFIG.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            payload["periods"]["validation"][1] = "2022-12-31"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(path)

            payload = json.loads(CONFIG.read_text(encoding="utf-8"))
            payload["evaluation"]["hac_lag_sessions"] = 9
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
