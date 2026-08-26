from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn

from kospi200_agent_c3.runner import (
    CNNBottomModel, LSTMVolatilityModel, build_sequences, choose_weight,
    sequence_feature_frame, train_cutoff_before_calibration, train_pair,
)


class AgentC3Tests(unittest.TestCase):
    def test_models_are_actual_lstm_and_cnn(self):
        lstm = LSTMVolatilityModel(6, 4)
        cnn = CNNBottomModel(6, 4)
        self.assertIsInstance(lstm.lstm, nn.LSTM)
        self.assertTrue(any(isinstance(layer, nn.Conv1d) for layer in cnn.modules()))

    def test_future_bar_cannot_change_earlier_sequence_features(self):
        rows = []
        for i in range(25):
            rows.append({"date": f"2020-01-{i + 1:02d}", "ticker": "000001", "open": 100 + i,
                         "high": 101 + i, "low": 99 + i, "close": 100.5 + i, "volume": 1000 + i,
                         "listed_shares": 1000000})
        market = pd.DataFrame(rows)
        before = sequence_feature_frame(market).iloc[:-1].reset_index(drop=True)
        market.loc[24, ["open", "high", "low", "close", "volume"]] = [1000, 1001, 999, 1000, 999999]
        after = sequence_feature_frame(market).iloc[:-1].reset_index(drop=True)
        pd.testing.assert_frame_equal(before, after)

    def test_membership_gap_and_reset_block_sequence(self):
        sessions = [f"2020-01-{i + 1:02d}" for i in range(6)]
        membership = pd.DataFrame({"date": sessions[:2] + sessions[3:], "ticker": ["000001"] * 5})
        features = membership.copy()
        for name in ("open_gap_log", "high_from_open_log", "low_from_open_log", "close_from_open_log", "close_return_log", "volume_z20"):
            features[name] = 0.0
        features["mechanical_reset"] = False
        targets = membership.copy()
        targets["target_success_2to1"] = 1.0
        targets["target_volatility_10"] = 0.2
        targets["target_net_excess_10"] = 0.1
        values, _ = build_sequences(features, membership, targets, sessions, sessions[0], sessions[-1], 3, 1)
        self.assertEqual(len(values), 1)
        features.loc[features.index[-2], "mechanical_reset"] = True
        values, _ = build_sequences(features, membership, targets, sessions, sessions[0], sessions[-1], 3, 1)
        self.assertEqual(len(values), 0)

    def test_tiny_training_is_deterministic(self):
        rng = np.random.default_rng(7)
        x = rng.normal(size=(32, 12, 6)).astype(np.float32)
        vol = np.abs(rng.normal(0.2, 0.05, size=32))
        success = (rng.random(32) > 0.6).astype(float)
        config = {"batch_size": 16, "lstm_hidden_size": 4, "cnn_channels": 4, "learning_rate": 0.001, "weight_decay": 0.0, "epochs": 2}
        first = train_pair(x, vol, success, config, 123)
        second = train_pair(x, vol, success, config, 123)
        for left, right in zip(first[0].state_dict().values(), second[0].state_dict().values(), strict=True):
            self.assertTrue(torch.equal(left, right))
        for left, right in zip(first[1].state_dict().values(), second[1].state_dict().values(), strict=True):
            self.assertTrue(torch.equal(left, right))

    def test_weight_grid_uses_excess_rank_ic(self):
        meta = pd.DataFrame({"date": ["2020-01-02"] * 4, "ticker": list("ABCD"),
                             "target_success_2to1": [1, 1, 0, 0], "target_volatility_10": [0.1, 0.2, 0.3, 0.4],
                             "target_net_excess_10": [0.4, 0.3, -0.2, -0.3]})
        result = choose_weight(meta, np.array([0.6, 0.55, 0.5, 0.45]), np.array([0.1, 0.2, 0.3, 0.4]), [0.0, 0.5])
        self.assertEqual(float(result.iloc[0]["risk_weight"]), 0.0)

    def test_purge_and_embargo_are_exchange_session_based(self):
        sessions = [f"S{i:02d}" for i in range(30)]
        self.assertEqual(train_cutoff_before_calibration(sessions, "S25", 3, 2), "S19")

    def test_config_freezes_real_torch_and_boundaries(self):
        config = json.loads(Path("configs/v2_phase3d_agent_c3_lstm_cnn.json").read_text(encoding="utf-8"))
        self.assertEqual(config["torch_version"], "2.13.0")
        self.assertEqual(config["lookback_sessions"], 40)
        self.assertEqual(config["risk_weight_grid"], [0.0, 0.25, 0.5, 0.75])
        self.assertEqual(config["take_profit_rate"], 2 * config["stop_loss_rate"])
        self.assertFalse(config["agent_b_access"])
        self.assertFalse(config["portfolio_backtest"])
        self.assertFalse(config["final_oos_access"])


if __name__ == "__main__":
    unittest.main()
