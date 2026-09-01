import copy
import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from kospi200_agent_b3.runner import _fit_ranker, _make_model, _validate_config


CONFIG = json.loads(Path("configs/v2_phase6_agent_b_xgbranker.json").read_text(encoding="utf-8"))


class AgentB3Tests(unittest.TestCase):
    def test_xgbranker_contract(self):
        _validate_config(CONFIG)
        self.assertEqual(CONFIG["model"]["objective"], "rank:ndcg")
        self.assertFalse(CONFIG["model"]["ndcg_exp_gain"])
        self.assertEqual(CONFIG["report_top_size"], 30)

    def test_rejects_legacy_or_portfolio_or_oos(self):
        for key, value in (("legacy_fundamental_panel", True), ("portfolio_backtest", True), ("final_oos_access", True)):
            config = copy.deepcopy(CONFIG)
            config[key] = value
            with self.assertRaises(ValueError):
                _validate_config(config)

    def test_ranker_uses_date_query_groups_and_is_deterministic(self):
        rows = []
        for day in ("2020-01-31", "2020-02-29"):
            for ticker, target in (("000001", 0.2), ("000002", 0.1), ("000003", -0.1)):
                rows.append({"date": day, "ticker": ticker, "target_quality_63": target, **{f: target for f in [
                    "roe__percentile", "roa__percentile", "operating_margin__percentile", "net_margin__percentile",
                    "cfo_to_assets__percentile", "earnings_yield__percentile", "book_to_market__percentile", "sales_to_market_cap__percentile",
                    "cfo_yield__percentile", "free_cash_flow_yield__percentile", "debt_to_equity__percentile", "liabilities_to_assets__percentile",
                    "current_ratio__percentile", "cash_to_assets__percentile", "equity_ratio__percentile", "revenue_growth_yoy__percentile",
                    "operating_income_growth_yoy__percentile", "net_income_growth_yoy__percentile", "assets_growth_yoy__percentile",
                    "equity_growth_yoy__percentile", "dilution_252__percentile"]}})
        frame = pd.DataFrame(rows)
        first = _fit_ranker(_make_model(CONFIG, 7), frame).predict(frame[[c for c in frame.columns if c.endswith("__percentile")]])
        second = _fit_ranker(_make_model(CONFIG, 7), frame).predict(frame[[c for c in frame.columns if c.endswith("__percentile")]])
        np.testing.assert_array_equal(first, second)


if __name__ == "__main__":
    unittest.main()
