from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd

from kospi200_agent_b5.runner import add_temporal_features, temporal_feature_columns


ROOT = Path(__file__).resolve().parents[1]


class AgentB5Tests(unittest.TestCase):
    def test_temporal_change_uses_only_prior_rows_of_same_ticker(self) -> None:
        column = "roe__percentile"
        frame = pd.DataFrame({"date": ["2020-01-01", "2020-01-02", "2020-01-03"], "ticker": ["000001"] * 3, column: [0.2, 0.3, 0.9]})
        for name in temporal_feature_columns():
            if name not in frame:
                frame[name] = 0.0
        result = add_temporal_features(frame)
        self.assertTrue(pd.isna(result.loc[result.index[0], f"{column}__delta_63"]))
        self.assertTrue(pd.isna(result.loc[result.index[0], f"{column}__delta_252"]))

    def test_missing_optional_robust_z_is_not_synthesized(self) -> None:
        columns = temporal_feature_columns({"dilution_252__percentile"})
        self.assertNotIn("dilution_252__robust_z", columns)

    def test_config_freezes_fundamental_only_xgb_top30_contract(self) -> None:
        config = json.loads((ROOT / "configs/v2_agent_b5_temporal_xgbranker.json").read_text(encoding="utf-8"))
        self.assertEqual(config["model"]["objective"], "rank:ndcg")
        self.assertEqual(config["report_top_size"], 30)
        self.assertEqual(config["market_cap_universe_size"], 200)
        self.assertEqual(config["purge_sessions"], 63)
        self.assertFalse(config["portfolio_backtest"])
        self.assertFalse(config["final_oos_access"])


if __name__ == "__main__":
    unittest.main()
