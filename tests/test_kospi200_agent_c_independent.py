from __future__ import annotations

import json
import unittest

import pandas as pd

from kospi200_agent_c_independent.runner import trade_outcomes


def market_for_path(lows, highs):
    sessions = [f"s{i:02d}" for i in range(12)]
    return pd.DataFrame({"date": sessions, "ticker": ["000001"] * 12, "open": [100.0] * 12,
                         "high": [100.0] + highs + [100.0] * (11 - len(highs)),
                         "low": [100.0] + lows + [100.0] * (11 - len(lows)), "close": [100.0] * 12}), sessions


class IndependentAgentCTests(unittest.TestCase):
    def test_same_bar_stop_and_target_is_conservative_loss(self):
        market, sessions = market_for_path([94.0], [111.0])
        result = trade_outcomes(market, sessions, 10, 0.05, 0.10, 0.004)
        self.assertEqual(result.iloc[0]["target_success_2to1"], 0.0)

    def test_target_before_stop_is_success(self):
        market, sessions = market_for_path([99.0, 94.0], [111.0, 100.0])
        result = trade_outcomes(market, sessions, 10, 0.05, 0.10, 0.004)
        self.assertEqual(result.iloc[0]["target_success_2to1"], 1.0)

    def test_config_forbids_agent_b_and_portfolio(self):
        from pathlib import Path
        config = json.loads(Path("configs/v2_phase3b_independent_agent_c.json").read_text(encoding="utf-8"))
        self.assertFalse(config["agent_b_access"]); self.assertFalse(config["portfolio_backtest"])
        self.assertEqual(config["take_profit_rate"], 2 * config["stop_loss_rate"])


if __name__ == "__main__": unittest.main()
