from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd

from kospi200_agent_d3.runner import METHODS, combine_scores, create_orders


class AgentD3Tests(unittest.TestCase):
    def setUp(self):
        self.c = pd.DataFrame({"date": ["2020-01-02"] * 3, "ticker": ["000001", "000002", "000003"],
                               "agent_c3_score": [0.10, 0.08, 0.04], "bottom_probability": [0.7, 0.6, 0.5],
                               "predicted_volatility": [0.2, 0.1, 0.3]})
        self.b = pd.DataFrame({"date": ["2020-01-02"] * 2, "ticker": ["000001", "000002"], "agent_b2_percentile": [0.1, 1.0]})

    def test_b2_calibration_does_not_remove_c3_stock(self):
        result = combine_scores(self.b, self.c, "C3_B2_RISK_CALIBRATION")
        self.assertEqual(set(result["ticker"]), set(self.c["ticker"]))
        self.assertEqual(result.iloc[0]["ticker"], "000002")

    def test_thresholds_control_five_and_eleven_percent_weight(self):
        scored = combine_scores(self.b, self.c, "C3_ONLY")
        market = pd.DataFrame({"date": ["2020-01-02"] * 3 + ["2020-01-03"] * 3,
                               "ticker": ["000001", "000002", "000003"] * 2,
                               "open": [100] * 3 + [101] * 3, "close": [100] * 3 + [101] * 3, "volume": [100] * 6})
        config = {"entry_score_5pct": 0.05, "entry_score_11pct": 0.075, "target_weight_low": 0.05,
                  "target_weight_high": 0.11, "daily_candidate_limit": 10, "gap_veto_rate": 0.05,
                  "stop_loss_rate": 0.05, "take_profit_rate": 0.10, "maximum_holding_sessions": 10}
        orders, _ = create_orders(scored, market, ["2020-01-02", "2020-01-03"], config, "C3_ONLY")
        self.assertEqual(len(orders), 2)
        self.assertEqual({str(order.target_weight) for order in orders}, {"0.11"})
        self.assertEqual(orders[0].execute_date.isoformat(), "2020-01-03")

    def test_config_freezes_original_lstm_cnn_trading_rules(self):
        config = json.loads(Path("configs/v2_phase4c_agent_d3_lstm_cnn.json").read_text(encoding="utf-8"))
        self.assertEqual(tuple(config["methods"]), METHODS)
        self.assertEqual(config["entry_score_5pct"], 0.05)
        self.assertEqual(config["entry_score_11pct"], 0.075)
        self.assertEqual(config["target_weight_low"], 0.05)
        self.assertEqual(config["target_weight_high"], 0.11)
        self.assertEqual(config["take_profit_rate"], 2 * config["stop_loss_rate"])
        self.assertEqual(config["same_bar_policy"], "STOP_FIRST")
        self.assertFalse(config["final_oos_access"])


if __name__ == "__main__":
    unittest.main()
