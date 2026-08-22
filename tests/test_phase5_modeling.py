from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from kospi100_ranking.config import load_config
from kospi100_ranking.modeling import evaluate_candidates, fold_dates
from kospi100_ranking.portfolio import _score, generate_orders


class Phase5ModelingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(Path("configs/phase5_ranking.json"))
        cls.index = pd.DataFrame({"date": pd.bdate_range("2011-01-03", "2021-12-31")})

    def test_purge_and_embargo_are_exchange_session_based(self) -> None:
        fold = self.config.folds[0]
        train, validation = fold_dates(self.index, fold, 20, 20)
        raw_train = self.index.loc[self.index["date"].dt.year <= 2018, "date"].tolist()
        raw_validation = self.index.loc[self.index["date"].dt.year == 2019, "date"].tolist()
        self.assertNotIn(raw_train[-1], train)
        self.assertIn(raw_train[-21], train)
        self.assertNotIn(raw_validation[19], validation)
        self.assertIn(raw_validation[20], validation)
        self.assertNotIn(raw_validation[-1], validation)
        self.assertIn(raw_validation[-21], validation)

    def _frame(self) -> pd.DataFrame:
        dates: list[pd.Timestamp] = []
        for year in range(2011, 2022):
            year_dates = self.index.loc[self.index["date"].dt.year.eq(year), "date"]
            dates.extend([year_dates.iloc[60], year_dates.iloc[120]])
        rows = []
        for dt in dates:
            for number in range(30):
                rank = (number + 1) / 30
                rows.append(
                    {
                        "date": dt,
                        "security_id": f"S{number:03d}",
                        "membership_spell_id": f"S{number:03d}:01",
                        "close": 100 + number,
                        "feature_rank": rank,
                        "target_rank": rank if dt.year % 2 else 1.0 - rank,
                        "forward_excess_log_return_10": rank / 100,
                    }
                )
        return pd.DataFrame(rows)

    def test_all_eight_candidates_are_fit_train_only_and_deterministic(self) -> None:
        frame = self._frame()
        first = evaluate_candidates(frame, self.index, self.config)
        second = evaluate_candidates(frame, self.index, self.config)
        self.assertEqual(first.predictions.to_csv(index=False), second.predictions.to_csv(index=False))
        self.assertEqual(set(first.predictions["candidate"]), set(self.config.candidate_order))
        self.assertEqual(len(first.rank_metrics), 24)
        self.assertTrue(first.rank_metrics["top_bottom_decile_target_spread"].notna().all())
        self.assertTrue((first.fold_audit["fit_used_validation"] == False).all())  # noqa: E712
        for row in first.fold_audit.itertuples(index=False):
            self.assertLess(row.train_max_date, row.validation_min_date)

    def test_signal_order_uses_next_session_and_fixed_portfolio_contract(self) -> None:
        sessions = (date(2020, 1, 2), date(2020, 1, 3), date(2020, 1, 6))
        predictions = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-02"] * 12),
                "security_id": [f"S{n:02d}" for n in range(12)],
                "score": np.arange(12),
                "close": [100] * 12,
                "candidate": ["raw_rank"] * 12,
            }
        )
        orders = generate_orders(predictions, sessions, self.config)
        self.assertEqual(len(orders), 10)
        self.assertTrue(all(order.signal_date == sessions[0] and order.execute_date == sessions[1] for order in orders))
        self.assertTrue(all(order.max_holding_sessions == 20 for order in orders))
        self.assertTrue(all(order.target_weight == self.config.target_weight for order in orders))
        self.assertEqual(orders[0].security_id, "S11")

    def test_selection_score_prefers_sharpe_then_registered_ties(self) -> None:
        raw = pd.Series(
            {"candidate": "raw_rank", "sharpe_zero_rf": 0.1, "net_excess_return": 0.2, "max_drawdown": -0.2, "turnover_on_average_equity": 2.0}
        )
        tree = raw.copy()
        tree["candidate"] = "tree_d1_l002"
        self.assertGreater(_score(raw, self.config.candidate_order), _score(tree, self.config.candidate_order))
        tree["sharpe_zero_rf"] = 0.11
        self.assertGreater(_score(tree, self.config.candidate_order), _score(raw, self.config.candidate_order))


if __name__ == "__main__":
    unittest.main()
