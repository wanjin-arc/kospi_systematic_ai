from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd

from kospi200_agent_d7.runner import apply_policy, build_frame


ROOT = Path(__file__).resolve().parents[1]


class AgentD7Tests(unittest.TestCase):
    def test_b_top30_is_a_hard_gate_and_probability_sets_size(self) -> None:
        b = pd.DataFrame({"date": ["2020-01-02"] * 3, "ticker": ["000001", "000002", "000003"], "agent_b5_percentile": [1.0, 0.9, 0.1], "report_top30": [True, True, False]})
        c = pd.DataFrame({"date": ["2020-01-02"] * 3, "ticker": ["000001", "000002", "000003"], "agent_c3_score": [0.2, 0.3, 0.8], "bottom_probability": [0.66, 0.56, 0.90], "predicted_volatility": [0.2, 0.1, 0.1]})
        frame = build_frame(b, c)
        policy = apply_policy(frame, 0.5, {"entry_probability_low": 0.55, "entry_probability_high": 0.65, "daily_candidate_limit": 10, "target_weight_low": 0.05, "target_weight_high": 0.11})
        self.assertEqual(set(policy["ticker"]), {"000001", "000002"})
        self.assertEqual(policy.loc[policy["ticker"].eq("000001"), "target_weight"].iloc[0], 0.11)

    def test_config_uses_probability_not_old_raw_score_threshold(self) -> None:
        config = json.loads((ROOT / "configs/v2_agent_d7_serial_b5_c6.json").read_text(encoding="utf-8"))
        self.assertEqual(config["agent_b_weight_grid"], [0.0, 0.5, 1.0])
        self.assertEqual(config["entry_probability_low"], 0.55)
        self.assertEqual(config["entry_probability_high"], 0.65)
        self.assertNotIn("entry_score_5pct", config)
        self.assertFalse(config["final_oos_access"])


if __name__ == "__main__":
    unittest.main()
