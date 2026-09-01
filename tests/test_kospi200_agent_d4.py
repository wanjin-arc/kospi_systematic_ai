from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd

from kospi200_agent_d4.runner import METHODS, combine_scores, create_orders


class AgentD4Tests(unittest.TestCase):
    def setUp(self):
        self.c = pd.DataFrame({
            "date": ["2020-01-02"] * 3, "ticker": ["000001", "000002", "000003"],
            "agent_c4_score": [1.0, 0.8, 0.2], "predicted_net_excess_10": [0.02, 0.01, -0.01],
            "positive_excess_probability": [0.7, 0.6, 0.2],
        })
        self.b = pd.DataFrame({
            "date": ["2020-01-02"] * 2, "ticker": ["000001", "000002"],
            "agent_b2_percentile": [0.1, 1.0],
        })

    def test_b2_calibration_changes_rank_without_removing_c4_rows(self):
        result = combine_scores(self.b, self.c, "C4_B2_RISK_CALIBRATION_SPARSE")
        self.assertEqual(set(result["ticker"]), set(self.c["ticker"]))
        self.assertEqual(result.iloc[0]["ticker"], "000002")

    def test_orders_use_economic_zero_gate_and_no_intraday_barriers(self):
        scored = combine_scores(self.b, self.c, "C4_SPARSE")
        market = pd.DataFrame({
            "date": ["2020-01-02"] * 3 + ["2020-01-03"] * 3,
            "ticker": ["000001", "000002", "000003"] * 2,
            "open": [100] * 3 + [101] * 3, "close": [100] * 3 + [101] * 3, "volume": [100] * 6,
        })
        config = {"minimum_predicted_net_excess": 0.0, "rebalance_interval_sessions": 5,
                  "daily_candidate_limit": 5, "gap_veto_rate": 0.05, "target_weight": 0.1,
                  "maximum_holding_sessions": 10}
        orders, _, signal_days = create_orders(scored, market, ["2020-01-02", "2020-01-03"], config, "C4_SPARSE")
        self.assertEqual(len(orders), 2)
        self.assertEqual(signal_days, 1)
        self.assertTrue(all(order.stop_price is None and order.target_price is None for order in orders))
        self.assertTrue(all(str(order.target_weight) == "0.1" for order in orders))

    def test_config_removes_raw_score_threshold_and_daily_reentry(self):
        config = json.loads(Path("configs/v2_phase4d_agent_d4_sparse_temporal_alpha.json").read_text(encoding="utf-8"))
        self.assertEqual(tuple(config["methods"]), METHODS)
        self.assertEqual(config["minimum_predicted_net_excess"], 0.0)
        self.assertEqual(config["rebalance_interval_sessions"], 5)
        self.assertNotIn("entry_score_5pct", config)
        self.assertNotIn("entry_score_11pct", config)
        self.assertFalse(config["final_oos_access"])


if __name__ == "__main__":
    unittest.main()
