import json
import unittest
from pathlib import Path

import pandas as pd

from kospi200_agent_c2.runner import ALL_FEATURES, attach_excess_target, index_features


class AgentC2Tests(unittest.TestCase):
    def test_config_freezes_long_history_official_index_and_no_agent_b(self):
        config = json.loads(Path("configs/v2_phase3c_agent_c_excess.json").read_text(encoding="utf-8"))
        self.assertEqual(config["market_start"], "2004-01-02")
        self.assertEqual(config["target_horizon_sessions"], 10)
        self.assertFalse(config["agent_b_access"])
        self.assertEqual(config["purge_sessions"], 10)
        self.assertEqual(config["embargo_sessions"], 10)
        self.assertEqual(len(ALL_FEATURES), 17)

    def test_target_uses_t_plus_1_t_plus_11_and_official_index(self):
        sessions = [f"2020-01-{day:02d}" for day in range(1, 13)]
        market = pd.DataFrame({"date": sessions, "ticker": "000001", "open": [100.0] * 11 + [120.0]})
        index = pd.DataFrame({"date": sessions, "open": [100.0] * 11 + [110.0]})
        frame = pd.DataFrame({"date": [sessions[0]], "ticker": ["000001"]})
        result = attach_excess_target(frame, market, index, sessions, 10, 0.004)
        self.assertAlmostEqual(result.loc[0, "target_net_excess_10"], 0.096)

    def test_index_features_are_causal(self):
        dates = pd.date_range("2020-01-01", periods=80, freq="D")
        base = pd.DataFrame({"date": dates.date.astype(str), "close": range(100, 180)})
        first = index_features(base)
        changed = base.copy(); changed.loc[79, "close"] = 10000
        second = index_features(changed)
        pd.testing.assert_frame_equal(first.iloc[:79], second.iloc[:79])

