from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from kospi100_absolute_alpha.config import load_config
from kospi100_absolute_alpha.modeling import (
    NET_TARGET,
    POSITIVE_TARGET,
    attach_cost_adjusted_target,
    evaluate_models,
)
from kospi100_features.labels import LABEL_COLUMN
from kospi100_ranking.config import Fold, Period


class Phase5EModelingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(Path("configs/phase5e_absolute_alpha.json"))

    def test_cost_adjusted_target_uses_exit_tax_and_strict_positive_label(self) -> None:
        labeled = pd.DataFrame({
            "date": pd.to_datetime(["2021-01-04", "2021-01-04", "2010-01-04"]),
            LABEL_COLUMN: [0.02, 0.0, 0.10],
            "exit_date": pd.to_datetime(["2021-01-15", "2021-01-15", "2010-01-19"]),
        })
        result, audit = attach_cost_adjusted_target(labeled, self.config)
        tax = 0.0008 + 0.0015
        net_factor = ((1 - 0.001) * (1 - 0.0002 - tax)) / ((1 + 0.001) * (1 + 0.0002))
        expected_cost = -np.log(net_factor)
        self.assertAlmostEqual(result.loc[0, "estimated_roundtrip_log_cost"], expected_cost)
        self.assertAlmostEqual(result.loc[0, NET_TARGET], 0.02 - expected_cost)
        self.assertEqual(result.loc[0, POSITIVE_TARGET], 1)
        self.assertEqual(result.loc[1, POSITIVE_TARGET], 0)
        self.assertTrue(pd.isna(result.loc[2, NET_TARGET]))
        self.assertEqual(audit["outside_research_period_rows_excluded"], 1)
        self.assertEqual(audit["cross_sectional_target_transform"], "none")
        self.assertEqual(audit["entry_offset_sessions"], 1)
        self.assertEqual(audit["exit_offset_sessions"], 11)

    def _small_config(self):
        fold = Fold(
            "FTEST",
            Period("train", date(2020, 1, 1), date(2020, 1, 14)),
            Period("validation", date(2020, 1, 15), date(2020, 1, 24)),
        )
        base = replace(self.config.base, folds=(fold,), purge_sessions=1, embargo_sessions=1)
        return replace(self.config, base=base)

    def _frame(self, sessions: pd.DatetimeIndex, config) -> pd.DataFrame:
        rows = []
        for day, session in enumerate(sessions):
            for security in range(40):
                rank = (security + 1) / 40
                target = (rank - 0.5) * 0.04 + (day % 3 - 1) * 0.001
                row = {
                    "date": session,
                    "security_id": f"S{security:02d}",
                    "membership_spell_id": f"S{security:02d}:01",
                    "close": 100.0,
                    LABEL_COLUMN: target + 0.004,
                    NET_TARGET: target,
                    POSITIVE_TARGET: int(target > 0.0),
                }
                for name in config.base.stock_features:
                    row[f"rank__{name}"] = rank
                for index, name in enumerate(config.base.regime_features):
                    row[name] = day * 0.01 + index * 0.02
                rows.append(row)
        return pd.DataFrame(rows)

    def test_validation_targets_do_not_affect_train_fitted_predictions(self) -> None:
        config = self._small_config()
        sessions = pd.bdate_range("2020-01-01", "2020-01-24")
        index = pd.DataFrame({"date": sessions})
        frame = self._frame(sessions, config)
        first = evaluate_models(frame, index, config)
        changed = frame.copy()
        changed.loc[changed["date"] >= pd.Timestamp("2020-01-15"), NET_TARGET] *= -10
        changed.loc[changed["date"] >= pd.Timestamp("2020-01-15"), POSITIVE_TARGET] = 1 - changed.loc[
            changed["date"] >= pd.Timestamp("2020-01-15"), POSITIVE_TARGET
        ]
        second = evaluate_models(changed, index, config)
        columns = ["date", "security_id", "predicted_net_excess", "positive_probability"]
        pd.testing.assert_frame_equal(first.predictions[columns], second.predictions[columns])
        self.assertFalse(first.fold_audit["preprocessing_fit_used_validation"].any())
        self.assertFalse(first.fold_audit["regression_fit_used_validation"].any())
        self.assertFalse(first.fold_audit["classification_fit_used_validation"].any())
        self.assertFalse(first.fold_audit["target_cross_sectional_rank_used"].any())


if __name__ == "__main__":
    unittest.main()
