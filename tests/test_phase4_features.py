import unittest

import numpy as np
import pandas as pd

from kospi100_features.features import build_feature_matrix


def _empty_actions() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "security_id", "feature_handling", "feature_boundary_date", "canonical_event_id",
            "price_multiplier", "share_multiplier", "first_filing_date", "portfolio_terms_status",
        ]
    )


class Phase4FeatureTests(unittest.TestCase):
    def test_session_lookback_and_eligibility_are_fail_closed(self) -> None:
        dates = pd.bdate_range("2020-01-02", periods=30)
        index = pd.DataFrame({"date": dates, "open": 100.0, "close": np.arange(100.0, 130.0)})
        panel = pd.DataFrame(
            {
                "date": dates,
                "security_id": "A",
                "open": np.arange(10.0, 40.0),
                "high": np.arange(11.0, 41.0),
                "low": np.arange(9.0, 39.0),
                "close": np.arange(10.0, 40.0),
                "feature_volume": 1000.0,
                "feature_trading_value": 1_000_000.0,
                "rank_eligible": True,
                "tradable": True,
                "is_member": True,
                "eligible_new_entry": True,
            }
        )
        result = build_feature_matrix(panel, index, _empty_actions()).cross_sectional
        self.assertTrue(pd.isna(result.loc[19, "momentum_20"]))
        self.assertTrue(pd.notna(result.loc[20, "momentum_20"]))

        panel = panel.drop(index=dates.get_loc(dates[10])).reset_index(drop=True)
        broken = build_feature_matrix(panel, index, _empty_actions()).cross_sectional
        row = broken.loc[broken["date"].eq(dates[20])].iloc[0]
        self.assertTrue(pd.isna(row["momentum_20"]))

        missing_value = panel.copy()
        missing_value.loc[missing_value["date"].eq(dates[12]), "close"] = np.nan
        missing_result = build_feature_matrix(missing_value, index, _empty_actions()).cross_sectional
        missing_row = missing_result.loc[missing_result["date"].eq(dates[25])].iloc[0]
        self.assertTrue(pd.isna(missing_row["momentum_20"]))

        panel.loc[panel["date"].eq(dates[25]), "rank_eligible"] = False
        gated = build_feature_matrix(panel, index, _empty_actions()).cross_sectional
        self.assertFalse(bool(gated.loc[gated["date"].eq(dates[25]), "phase4_eligible"].iloc[0]))

    def test_mechanical_adjustment_and_reset_boundary(self) -> None:
        dates = pd.bdate_range("2020-01-02", periods=25)
        index = pd.DataFrame({"date": dates, "open": 100.0, "close": 100.0})
        panel = pd.DataFrame(
            {
                "date": dates,
                "security_id": "A",
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.0,
                "feature_volume": 1000.0,
                "feature_trading_value": 1_000_000.0,
                "rank_eligible": True,
                "tradable": True,
                "is_member": True,
                "eligible_new_entry": True,
            }
        )
        actions = pd.DataFrame(
            {
                "security_id": ["A", "A"],
                "feature_handling": ["PIT_MECHANICAL_ADJUSTMENT", "RESET_RIGHTS_ISSUE"],
                "feature_boundary_date": [dates[5], dates[15]],
                "canonical_event_id": ["M1", "R1"],
                "price_multiplier": [0.5, 1.0],
                "share_multiplier": [2.0, 1.0],
                "first_filing_date": [dates[5], dates[14]],
                "portfolio_terms_status": ["KNOWN", "KNOWN"],
            }
        )
        result = build_feature_matrix(panel, index, actions).cross_sectional
        self.assertEqual(result.loc[0, "adjusted_close"], 5.0)
        self.assertEqual(result.loc[0, "adjusted_volume"], 2000.0)
        self.assertNotEqual(result.loc[14, "feature_segment"], result.loc[15, "feature_segment"])
        self.assertTrue(pd.isna(result.loc[20, "momentum_20"]))


if __name__ == "__main__":
    unittest.main()
