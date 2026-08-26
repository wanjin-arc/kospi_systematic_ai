from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from kospi200_agent_c4.runner import TemporalAlphaModel, score_predictions


class AgentC4Tests(unittest.TestCase):
    def test_temporal_model_has_regression_and_probability_heads(self):
        model = TemporalAlphaModel(input_size=6, hidden_size=8, channels=8)
        excess, logit = model(torch.zeros((4, 40, 6), dtype=torch.float32))
        self.assertEqual(tuple(excess.shape), (4,))
        self.assertEqual(tuple(logit.shape), (4,))

    def test_score_is_cross_sectional_and_scale_independent(self):
        meta = pd.DataFrame({"date": ["2020-01-02"] * 3, "ticker": ["1", "2", "3"]})
        scored = score_predictions(meta, np.array([0.01, 0.03, -0.01]), np.array([0.6, 0.7, 0.2]), 0.25)
        self.assertEqual(scored.sort_values("agent_c4_rank").iloc[0]["ticker"], "2")
        self.assertTrue(np.isfinite(scored["agent_c4_score"]).all())

    def test_config_freezes_boundaries_and_no_portfolio_access(self):
        config = json.loads(Path("configs/v2_phase3e_agent_c4_temporal_alpha.json").read_text(encoding="utf-8"))
        self.assertEqual(config["market_start"], "2004-01-02")
        self.assertEqual(config["train_end"], "2018-12-28")
        self.assertEqual(config["score_start"], "2019-01-02")
        self.assertEqual(config["purge_sessions"], 10)
        self.assertEqual(config["embargo_sessions"], 10)
        self.assertFalse(config["agent_b_access"])
        self.assertFalse(config["portfolio_backtest"])
        self.assertFalse(config["final_oos_access"])


if __name__ == "__main__":
    unittest.main()
