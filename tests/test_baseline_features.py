from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from kospi100_baseline.features import build_features, mechanically_adjusted_close


class BaselineFeatureTests(unittest.TestCase):
    def test_future_split_factor_cannot_change_scale_invariant_signal(self) -> None:
        dates = pd.bdate_range("2020-01-01", periods=220)
        panel = pd.DataFrame(
            {
                "date": dates,
                "security_id": "A",
                "close": np.linspace(100.0, 150.0, len(dates)),
            }
        )
        boundary = dates[-1] + pd.offsets.BDay(5)
        actions = pd.DataFrame(
            {
                "canonical_event_id": ["FUTURE_SPLIT"],
                "security_id": ["A"],
                "feature_handling": ["PIT_MECHANICAL_ADJUSTMENT"],
                "feature_boundary_date": [boundary],
                "price_multiplier": [0.2],
            }
        )
        effective_asof = mechanically_adjusted_close(panel, actions, action_cutoff=dates[-1])
        fully_scaled = mechanically_adjusted_close(panel, actions)
        self.assertAlmostEqual(float(effective_asof.iloc[-1] / effective_asof.iloc[-127] - 1), float(fully_scaled.iloc[-1] / fully_scaled.iloc[-127] - 1))
        self.assertEqual(effective_asof.iloc[-1] > effective_asof.iloc[-200:].mean(), fully_scaled.iloc[-1] > fully_scaled.iloc[-200:].mean())

    def test_reset_starts_new_lookback_and_pending_terms_block_entries(self) -> None:
        dates = pd.bdate_range("2019-01-01", periods=450)
        panel = pd.DataFrame(
            {
                "date": dates,
                "security_id": "A",
                "close": np.linspace(100.0, 200.0, len(dates)),
                "rank_eligible": True,
                "tradable": True,
                "is_member": True,
            }
        )
        index = pd.DataFrame({"date": dates, "close": np.linspace(1000.0, 1100.0, len(dates))})
        boundary = dates[260]
        filing = dates[250]
        actions = pd.DataFrame(
            {
                "canonical_event_id": ["RESET"],
                "security_id": ["A"],
                "feature_handling": ["RESET_PRICE_CONTINUITY"],
                "feature_boundary_date": [boundary],
                "first_filing_date": [filing],
                "portfolio_terms_status": ["PENDING_PORTFOLIO_TERMS"],
                "price_multiplier": [np.nan],
            }
        )
        result = build_features(panel, index, actions).frame
        boundary_row = result.loc[result["date"].eq(boundary)].iloc[0]
        last_row = result.iloc[-1]
        self.assertEqual(boundary_row["feature_segment"], 1)
        self.assertTrue(pd.isna(boundary_row["sma200"]))
        self.assertTrue(last_row["ca_entry_blocked"])
        self.assertFalse(last_row["baseline_candidate"])


if __name__ == "__main__":
    unittest.main()
