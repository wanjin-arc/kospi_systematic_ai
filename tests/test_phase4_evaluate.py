import math
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from kospi100_features.config import load_config
from kospi100_features.evaluate import _daily_rank_ic, _forward_embargo_dates, _hac_tstat, evaluate_features
from kospi100_features.labels import LABEL_COLUMN


class Phase4EvaluationTests(unittest.TestCase):
    def test_spearman_minimum_cross_section_and_hac(self) -> None:
        frame = pd.DataFrame(
            {
                "date": [pd.Timestamp("2020-01-02")] * 30,
                "feature": np.arange(30.0),
                LABEL_COLUMN: np.arange(30.0),
            }
        )
        ic = _daily_rank_ic(frame, "feature", 30)
        self.assertAlmostEqual(float(ic.iloc[0]), 1.0)
        self.assertTrue(_daily_rank_ic(frame.iloc[:-1], "feature", 30).empty)
        values = pd.Series(np.linspace(0.01, 0.02, 40))
        self.assertIsNotNone(_hac_tstat(values, 10))

    def test_purge_embargo_coverage_stability_and_redundancy(self) -> None:
        config = load_config(Path("configs/phase4_features.json"))
        train_dates = pd.bdate_range("2018-09-03", periods=60)
        validation_dates = pd.bdate_range("2019-01-02", periods=45).append(
            pd.bdate_range("2020-01-02", periods=45)
        )
        dates = train_dates.append(validation_dates)
        index = pd.DataFrame({"date": dates, "open": 100.0, "close": 100.0})
        rows = []
        feature_ids = [item.feature_id for item in config.features]
        for day_index, day in enumerate(dates):
            for security in range(35):
                row = {
                    "date": day,
                    "security_id": f"S{security:03d}",
                    "phase4_eligible": True,
                    LABEL_COLUMN: float(security) + math.sin((day_index + 1) * (security + 1)) * 0.75,
                }
                for offset, feature in enumerate(feature_ids):
                    row[feature] = float(security) + offset * 1e-9
                rows.append(row)
        result = evaluate_features(pd.DataFrame(rows), index, config)
        self.assertEqual(result.audit["purge_sessions"], 20)
        self.assertEqual(result.audit["embargo_sessions"], 20)
        self.assertEqual(result.audit["embargoed_dates"], 0)
        self.assertFalse(result.audit["embargo_later_training_exists"])
        self.assertTrue((result.metrics["coverage"] == 1.0).all())
        self.assertIn("채택_Phase5후보", set(result.decisions["decision"]))
        self.assertIn("보류_중복", set(result.decisions["decision"]))
        self.assertFalse(result.audit["development_test_accessed"])

        embargo = _forward_embargo_dates(index, train_dates[-1], 20, later_training_exists=True)
        self.assertEqual(len(embargo), 20)


if __name__ == "__main__":
    unittest.main()
