from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from kospi200_agent_c.runner import FEATURES, attach_target, compute_technical_features, guard_path


class AgentCContractTests(unittest.TestCase):
    def test_exactly_fourteen_ohlcv_features(self):
        self.assertEqual(len(FEATURES), 14)
        self.assertNotIn("agent_b_score", FEATURES)

    def test_forbidden_oos_path(self):
        from pathlib import Path
        with self.assertRaises(ValueError): guard_path(Path("data/sealed/final_oos_v24"))

    def test_target_uses_t_plus_1_and_t_plus_11_open_minus_cost(self):
        sessions = [f"s{i:02d}" for i in range(12)]
        market = pd.DataFrame({"date": sessions, "ticker": ["000001"] * 12, "open": np.arange(100.0, 112.0)})
        panel = pd.DataFrame({"date": ["s00"], "ticker": ["000001"]})
        result = attach_target(panel, market, sessions, 10, 0.004)
        self.assertAlmostEqual(result.loc[0, "target_net_return_10"], 111 / 101 - 1 - 0.004)

    def test_split_resets_technical_history(self):
        rows = 65
        market = pd.DataFrame({"date": [f"s{i:03d}" for i in range(rows)], "ticker": ["000001"] * rows,
                               "open": [100.0] * rows, "high": [101.0] * rows, "low": [99.0] * rows,
                               "close": [100.0] * 64 + [20.0], "volume": [1000.0] * rows,
                               "listed_shares": [100.0] * 64 + [500.0]})
        result = compute_technical_features(market)
        self.assertTrue(bool(result.iloc[-1]["mechanical_reset"]))
        self.assertTrue(result.iloc[-1][list(FEATURES)].isna().all())


if __name__ == "__main__": unittest.main()
