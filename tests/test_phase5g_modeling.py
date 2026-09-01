from __future__ import annotations

import math
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from kospi100_multihorizon.config import load_config
from kospi100_multihorizon.modeling import (
    PreparedMultiHorizonResearch,
    attach_multihorizon_targets,
    evaluate_model,
    target_name,
)
from kospi100_ranking.config import Fold, Period


class Phase5GModelingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(Path("configs/phase5g_multihorizon_consensus.json"))

    def test_t_plus_1_to_6_11_21_targets_and_costs(self) -> None:
        dates = pd.bdate_range("2018-01-02", periods=23)
        index = pd.DataFrame({"date": dates, "open": np.arange(100.0, 123.0), "close": 100.0})
        full = pd.DataFrame({
            "date": dates, "security_id": "A", "open": np.arange(10.0, 33.0), "tradable": True,
        })
        feature = pd.DataFrame({
            "date": [dates[0]], "security_id": ["A"], "feature_segment": [0],
            "phase4_eligible": [True],
        })
        actions = pd.DataFrame(columns=[
            "security_id", "feature_handling", "feature_boundary_date", "canonical_event_id",
            "price_multiplier", "share_multiplier", "first_filing_date", "portfolio_terms_status",
        ])
        result, audit = attach_multihorizon_targets(feature, full, index, actions, self.config)
        self.assertEqual(audit["exit_offsets_sessions"], [6, 11, 21])
        self.assertEqual(result.loc[0, "entry_date"], dates[1])
        for horizon, position in ((5, 6), (10, 11), (20, 21)):
            gross = math.log((10.0 + position) / 11.0) - math.log((100.0 + position) / 101.0)
            self.assertLess(float(result.loc[0, target_name(horizon)]), gross)
            self.assertEqual(result.loc[0, f"exit_date_{horizon}"], dates[position])

    def test_reset_crossing_removes_all_horizon_completion(self) -> None:
        dates = pd.bdate_range("2018-01-02", periods=23)
        index = pd.DataFrame({"date": dates, "open": 100.0, "close": 100.0})
        full = pd.DataFrame({"date": dates, "security_id": "A", "open": 10.0, "tradable": True})
        feature = pd.DataFrame({
            "date": [dates[0]], "security_id": ["A"], "feature_segment": [0],
            "phase4_eligible": [True],
        })
        actions = pd.DataFrame({
            "security_id": ["A"], "feature_handling": ["RESET_RIGHTS_ISSUE"],
            "feature_boundary_date": [dates[5]], "canonical_event_id": ["R1"],
            "price_multiplier": [1.0], "share_multiplier": [1.0],
            "first_filing_date": [dates[1]], "portfolio_terms_status": ["KNOWN"],
        })
        result, audit = attach_multihorizon_targets(feature, full, index, actions, self.config)
        self.assertTrue(result[[target_name(value) for value in self.config.horizons]].isna().all().all())
        self.assertEqual(audit["complete_all_horizons_rows"], 0)

    def test_validation_targets_do_not_change_train_fitted_predictions(self) -> None:
        sessions = pd.bdate_range("2020-01-01", "2020-02-28")
        fold = Fold(
            "ITEST", Period("train", date(2020, 1, 1), date(2020, 1, 31)),
            Period("validation", date(2020, 2, 1), date(2020, 2, 28)),
        )
        base = replace(self.config.base, folds=(fold,), purge_sessions=1, embargo_sessions=1)
        config = replace(self.config, base=base, n_estimators=5, min_samples_leaf=2, max_depth=3)
        rows = []
        for day, session in enumerate(sessions):
            for security in range(35):
                rank = (security + 1) / 35
                row = {
                    "date": session, "security_id": f"S{security:02d}",
                    "membership_spell_id": f"S{security:02d}:1", "close": 100.0,
                }
                for horizon in config.horizons:
                    row[target_name(horizon)] = (rank - 0.5) * horizon / 100.0
                for name in config.base.stock_features:
                    row[f"rank__{name}"] = rank
                for number, name in enumerate(config.base.regime_features):
                    row[name] = day / 100.0 + number / 10.0
                rows.append(row)
        frame = pd.DataFrame(rows)
        research = PreparedMultiHorizonResearch(frame, {})
        index = pd.DataFrame({"date": sessions})
        first = evaluate_model(research, index, config)
        changed = frame.copy()
        validation = changed["date"] >= pd.Timestamp("2020-02-01")
        changed.loc[validation, [target_name(value) for value in config.horizons]] *= -100
        second = evaluate_model(PreparedMultiHorizonResearch(changed, {}), index, config)
        columns = ["date", "security_id", *[f"predicted_net_excess_{value}" for value in config.horizons]]
        pd.testing.assert_frame_equal(first.predictions[columns], second.predictions[columns])
        self.assertFalse(first.fold_audit["model_fit_used_validation"].any())


if __name__ == "__main__":
    unittest.main()
