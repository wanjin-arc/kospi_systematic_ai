from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from kospi200_agent_b.runner import attach_forward_rank, compute_dilution, eligible_daily_panel, guard_path


class AgentBContractTests(unittest.TestCase):
    def test_forbidden_oos_path(self):
        with self.assertRaises(ValueError):
            guard_path(__import__("pathlib").Path("data/sealed/final_oos_v24"))

    def test_target_is_t_plus_1_to_t_plus_64_open(self):
        sessions = [f"2020-01-{day:02d}" for day in range(1, 67)]
        market = pd.DataFrame({"date": sessions, "ticker": ["000001"] * 66,
                               "open": np.arange(100.0, 166.0), "close": 1.0, "listed_shares": 1.0})
        panel = pd.DataFrame({"date": [sessions[0]], "ticker": ["000001"]})
        result = attach_forward_rank(panel, market, sessions, 63)
        self.assertAlmostEqual(result.loc[0, "forward_return_63"], 164.0 / 101.0 - 1.0)

    def test_mechanical_split_is_not_dilution(self):
        market = pd.DataFrame({"date": [f"2020-01-{i:02d}" for i in range(1, 22)],
                               "ticker": ["000001"] * 21,
                               "open": [100.0] * 21,
                               "close": [100.0] * 20 + [20.0],
                               "listed_shares": [100.0] * 20 + [500.0]})
        result = compute_dilution(market, lookback=20)
        self.assertTrue(bool(result.iloc[-1]["mechanical_share_reset"]))
        self.assertAlmostEqual(float(result.iloc[-1]["dilution_252"]), 0.0)

    def test_market_cap_200_then_top_model_scope(self):
        panel = pd.DataFrame({"date": ["2020-01-01"] * 202, "ticker": [f"{i:06d}" for i in range(202)],
                              "market_cap": range(202, 0, -1), "rank_eligible": True})
        dilution = pd.DataFrame({"date": panel.date, "ticker": panel.ticker, "open": 1,
                                 "listed_shares": 1, "dilution_252": 0.0, "mechanical_share_reset": False})
        result = eligible_daily_panel(panel, dilution, 200)
        self.assertEqual(len(result), 200)
        self.assertEqual(int(result["market_cap_rank"].max()), 200)

    def test_purge_and_embargo_are_both_registered(self):
        import json
        from pathlib import Path
        config = json.loads(Path("configs/v2_phase2_agent_b.json").read_text(encoding="utf-8"))
        self.assertEqual(config["purge_sessions"], 63)
        self.assertEqual(config["embargo_sessions"], 63)

    def test_feature_contract_contains_dilution(self):
        from kospi200_agent_b.runner import feature_columns
        self.assertEqual(len(feature_columns()), 21)
        self.assertIn("dilution_252__percentile", feature_columns())

    def test_v2_consumed_period_is_not_called_unaccessed_development_test(self):
        source = __import__("inspect").getsource(__import__("kospi200_agent_b.runner", fromlist=["run"]).run)
        self.assertIn("v2_consumed_development_2022_2023_loaded", source)
        self.assertNotIn('"development_test_accessed"', source)


if __name__ == "__main__":
    unittest.main()
