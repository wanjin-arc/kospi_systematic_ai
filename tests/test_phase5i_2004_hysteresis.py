from __future__ import annotations

import json
import hashlib
import unittest
from pathlib import Path

import pandas as pd

from kospi100_phase5i.config import load_config
from kospi100_phase5i.policy import add_policy_flags
from kospi100_phase5i.runner import freeze_values
from kospi100_ranking.data import load_selection_bundle


CONFIG = Path("configs/phase5i_2004_hysteresis_rebalance.json")


class Phase5IConfigAndBoundaryTests(unittest.TestCase):
    def test_config_is_2004_2018_and_protected_inputs_denied(self) -> None:
        config = load_config(CONFIG)
        self.assertEqual(config.base.periods["research"].start.isoformat(), "2004-01-02")
        self.assertEqual(config.base.maximum_permitted_date.isoformat(), "2018-12-31")
        self.assertEqual(len(config.base.folds), 8)
        self.assertFalse(config.payload["development_test_access"])

    def test_bundle_physically_loads_2004_and_not_after_2018(self) -> None:
        config = load_config(CONFIG)
        bundle = load_selection_bundle(config.base)
        self.assertEqual(bundle.feature_panel["date"].min().date().isoformat(), "2004-01-02")
        self.assertLessEqual(bundle.feature_panel["date"].max().date().isoformat(), "2018-12-31")
        self.assertTrue((bundle.feature_panel["date"] < "2011-01-01").any())
        self.assertEqual(bundle.audit["development_test_rows_loaded"], 0)
        self.assertFalse(bundle.audit["final_oos_accessed"])

    def test_registry_hashes_are_freezable_before_run(self) -> None:
        values = freeze_values(load_config(CONFIG))
        self.assertEqual(values["data_version"], "8d561c1412b825b10d8ceb0fce11554813cb17f47ee9f209ba39bcf9c7c88ebe")
        self.assertEqual(set(values), {"code_hash", "config_hash", "data_version", "model_hash"})

    def test_three_session_persistence_and_five_session_rebalance(self) -> None:
        config = load_config(CONFIG)
        dates = pd.date_range("2011-01-03", periods=7, freq="B")
        frame = pd.DataFrame(
            {
                "fold": ["I2011"] * 7,
                "security_id": ["S"] * 7,
                "membership_spell_id": ["M"] * 7,
                "continuity_segment": [1] * 7,
                "date": dates,
                "daily_rank": [5, 5, 5, 5, 25, 25, 25],
                "score": [0.9] * 7,
                "close": [100] * 7,
            }
        )
        result = add_policy_flags(frame, config)
        self.assertFalse(bool(result.iloc[1]["entry_persistent"]))
        self.assertTrue(bool(result.iloc[2]["entry_persistent"]))
        self.assertTrue(bool(result.iloc[6]["exit_persistent"]))
        self.assertEqual(result.loc[result["rebalance_date"], "date"].tolist(), [dates[0], dates[5]])

    def test_completed_artifacts_fail_closed_and_hash_verified(self) -> None:
        root = Path("artifacts/phase5i_2004_hysteresis_rebalance")
        decision = json.loads((root / "engineering_decision.json").read_text(encoding="utf-8"))
        audit = json.loads((root / "data_audit.json").read_text(encoding="utf-8"))
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(decision["status"], "ADAPTIVE_DIAGNOSTIC_FAIL")
        self.assertEqual(decision["nonnegative_annual_excess_folds"], 2)
        self.assertEqual(audit["pre_2011_training_rows"], 173390)
        self.assertEqual(audit["2019_plus_rows_loaded"], 0)
        self.assertEqual(audit["development_test_rows_loaded"], 0)
        self.assertFalse(audit["final_oos_accessed"])
        for name, expected in manifest.items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
