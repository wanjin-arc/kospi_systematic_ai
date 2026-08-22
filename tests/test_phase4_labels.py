import math
import unittest

import numpy as np
import pandas as pd

from kospi100_features.labels import LABEL_COLUMN, attach_forward_label


class Phase4LabelTests(unittest.TestCase):
    def test_signal_close_uses_t_plus_1_and_t_plus_11_opens(self) -> None:
        dates = pd.bdate_range("2021-01-04", periods=13)
        index = pd.DataFrame({"date": dates, "open": np.arange(100.0, 113.0), "close": 100.0})
        full = pd.DataFrame(
            {
                "date": dates,
                "security_id": "A",
                "open": np.arange(10.0, 23.0),
                "tradable": True,
            }
        )
        feature = pd.DataFrame(
            {
                "date": [dates[0]],
                "security_id": ["A"],
                "feature_segment": [0],
                "phase4_eligible": [True],
            }
        )
        actions = pd.DataFrame(
            columns=[
                "security_id", "feature_handling", "feature_boundary_date", "canonical_event_id",
                "price_multiplier", "share_multiplier", "first_filing_date", "portfolio_terms_status",
            ]
        )
        labeled, audit = attach_forward_label(feature, full, index, actions)
        expected = math.log(21.0 / 11.0) - math.log(111.0 / 101.0)
        self.assertAlmostEqual(float(labeled.loc[0, LABEL_COLUMN]), expected)
        self.assertEqual(labeled.loc[0, "entry_date"], dates[1])
        self.assertEqual(labeled.loc[0, "exit_date"], dates[11])
        self.assertTrue(audit["entry_is_after_signal"])
        self.assertFalse(audit["same_day_execution"])

    def test_reset_crossing_and_untradable_exit_remove_label(self) -> None:
        dates = pd.bdate_range("2021-01-04", periods=13)
        index = pd.DataFrame({"date": dates, "open": 100.0, "close": 100.0})
        full = pd.DataFrame({"date": dates, "security_id": "A", "open": 10.0, "tradable": True})
        feature = pd.DataFrame(
            {"date": [dates[0]], "security_id": ["A"], "feature_segment": [0], "phase4_eligible": [True]}
        )
        actions = pd.DataFrame(
            {
                "security_id": ["A"],
                "feature_handling": ["RESET_RIGHTS_ISSUE"],
                "feature_boundary_date": [dates[5]],
                "canonical_event_id": ["R1"],
                "price_multiplier": [1.0],
                "share_multiplier": [1.0],
                "first_filing_date": [dates[1]],
                "portfolio_terms_status": ["KNOWN"],
            }
        )
        labeled, audit = attach_forward_label(feature, full, index, actions)
        self.assertTrue(pd.isna(labeled.loc[0, LABEL_COLUMN]))
        self.assertEqual(audit["reset_crossing_rows_excluded"], 1)


if __name__ == "__main__":
    unittest.main()
