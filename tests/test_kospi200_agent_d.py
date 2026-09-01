from __future__ import annotations

import json
import unittest

import pandas as pd

from kospi200_agent_d.runner import combine_scores, create_orders


class AgentDTests(unittest.TestCase):
    def test_missing_agent_b_never_removes_agent_c_stock(self):
        c = pd.DataFrame({"date": ["2020-01-01"] * 2, "ticker": ["A", "B"], "agent_c_score": [0.1, 0.2]})
        b = pd.DataFrame({"date": ["2020-01-01"], "ticker": ["A"], "agent_b_score": [1.0]})
        result = combine_scores(b, c, 0.5)
        self.assertEqual(set(result["ticker"]), {"A", "B"})

    def test_config_freezes_original_score_weights_and_two_to_one(self):
        from pathlib import Path
        config = json.loads(Path("configs/v2_phase4_agent_d.json").read_text(encoding="utf-8"))
        self.assertEqual(config["entry_score_5pct"], 0.05); self.assertEqual(config["entry_score_11pct"], 0.075)
        self.assertEqual(config["take_profit_rate"], 2 * config["stop_loss_rate"])
        self.assertEqual(config["same_bar_policy"], "STOP_FIRST")

    def test_gap_veto_is_applied_at_execution_open(self):
        config = {"entry_score_5pct": 0.05, "entry_score_11pct": 0.075, "maximum_positions": 10, "gap_veto_rate": 0.05,
                  "target_weight_high": 0.11, "target_weight_low": 0.05, "stop_loss_rate": 0.05, "take_profit_rate": 0.10, "maximum_holding_sessions": 10}
        scored = pd.DataFrame({"date": ["2020-01-01"], "ticker": ["A"], "agent_c_score": [0.1], "combined_score": [1.0]})
        market = pd.DataFrame({"date": ["2020-01-01", "2020-01-02"], "ticker": ["A", "A"], "open": [100, 106], "close": [100, 106], "volume": [1, 1]})
        orders, vetoes = create_orders(scored, market, ["2020-01-01", "2020-01-02"], config)
        self.assertEqual(len(orders), 0); self.assertEqual(vetoes, 1)


if __name__ == "__main__": unittest.main()
