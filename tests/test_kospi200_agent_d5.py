from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd

from kospi200_agent_d5.runner import META_FEATURES, apply_policy, relationship_features


ROOT = Path(__file__).resolve().parents[1]


class AgentD5Tests(unittest.TestCase):
    def test_config_freezes_pre_2021_selection_and_consumed_diagnostic(self) -> None:
        config = json.loads((ROOT / "configs/v2_phase5_agent_d5_relationship_probability.json").read_text(encoding="utf-8"))
        self.assertLess(config["final_fit_end"], "2021-01-01")
        self.assertGreaterEqual(config["diagnostic_start"], "2021-01-01")
        self.assertLessEqual(config["diagnostic_end"], "2023-12-31")
        self.assertEqual(config["evidence_status"], "CONSUMED_DEVELOPMENT_DIAGNOSTIC_ONLY")
        self.assertFalse(config["final_oos_access"])
        self.assertEqual(config["purge_sessions"], 10)
        self.assertEqual(config["embargo_sessions"], 10)

    def test_relationship_features_include_cross_agent_interactions(self) -> None:
        b = pd.DataFrame({"date": ["2020-01-02"], "ticker": [5930], "agent_b2_percentile": [0.8]})
        c = pd.DataFrame({"date": ["2020-01-02"], "ticker": [5930], "agent_c3_score": [0.4], "bottom_probability": [0.7], "predicted_volatility": [0.2]})
        targets = pd.DataFrame({"date": ["2020-01-02"], "ticker": [5930], "target_success_2to1": [1.0], "target_terminal_net_return_10": [0.1], "target_net_excess_10": [0.08]})
        result = relationship_features(b, c, targets).iloc[0]
        self.assertTrue(set(META_FEATURES).issubset(result.index))
        self.assertAlmostEqual(result["b_probability_product"], 0.56)
        self.assertAlmostEqual(result["agent_agreement"], 0.8)

    def test_probability_and_percentile_both_gate_entries(self) -> None:
        frame = pd.DataFrame({
            "date": ["2020-01-02"] * 2, "ticker": ["000001", "000002"],
            "meta_success_probability": [0.61, 0.49], "agent_b2_percentile": [1.0, 0.9], "c3_percentile": [1.0, 0.8],
        })
        result = apply_policy(frame, 0.5, 0.55, 0.9)
        self.assertEqual(result["entry_eligible"].tolist(), [True, False])


if __name__ == "__main__":
    unittest.main()
