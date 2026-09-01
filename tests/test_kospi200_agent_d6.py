from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd

from kospi200_agent_d6.runner import META_FEATURES, METHODS, apply_method, build_meta_frame


ROOT = Path(__file__).resolve().parents[1]


class AgentD6Tests(unittest.TestCase):
    def test_config_replaces_raw_threshold_grid_with_walk_forward_rank(self) -> None:
        config = json.loads((ROOT / "configs/v2_agent_d6_walk_forward_meta_rank.json").read_text(encoding="utf-8"))
        self.assertEqual(tuple(config["methods"]), METHODS)
        self.assertNotIn("entry_score_5pct", config)
        self.assertNotIn("entry_score_11pct", config)
        self.assertNotIn("agent_b_weight_grid", config)
        self.assertEqual(config["evaluation_years"], [2020, 2021, 2022, 2023])
        self.assertEqual(config["purge_sessions"], 10)
        self.assertEqual(config["embargo_sessions"], 10)
        self.assertFalse(config["final_oos_access"])

    def test_meta_frame_uses_b2_c3_relationships_and_top30_flag(self) -> None:
        b = pd.DataFrame({"date": ["2020-01-02"], "ticker": [5930], "agent_b2_percentile": [0.8], "report_top30": [True]})
        c = pd.DataFrame({"date": ["2020-01-02"], "ticker": [5930], "agent_c3_score": [0.4], "bottom_probability": [0.7], "predicted_volatility": [0.2]})
        target = pd.DataFrame({"date": ["2020-01-02"], "ticker": [5930], "target_net_excess_10": [0.03]})
        row = build_meta_frame(b, c, target).iloc[0]
        self.assertTrue(set(META_FEATURES).issubset(row.index))
        self.assertTrue(row["report_top30"])
        self.assertAlmostEqual(row["b_bottom_product"], 0.56)

    def test_serial_method_excludes_non_top30_and_uses_rank_not_absolute_threshold(self) -> None:
        frame = pd.DataFrame({
            "date": ["2020-01-02"] * 4,
            "ticker": ["000001", "000002", "000003", "000004"],
            "report_top30": [True, True, False, True],
            "meta_expected_net_excess": [-0.03, -0.01, 0.50, -0.02],
            "agent_c3_score": [0.1, 0.2, 0.9, 0.3],
        })
        result = apply_method(frame, "B2_TOP30_META_RANK", 2)
        self.assertEqual(set(result["ticker"]), {"000001", "000002", "000004"})
        self.assertEqual(set(result.loc[result["entry_eligible"], "ticker"]), {"000002", "000004"})


if __name__ == "__main__":
    unittest.main()
