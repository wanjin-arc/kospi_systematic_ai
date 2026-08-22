from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from kospi100_absolute_alpha.config import load_config
from kospi100_absolute_alpha.policy import apply_no_trade_policy, generate_no_trade_orders
from kospi100_backtest.types import Side


class Phase5EPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(Path("configs/phase5e_absolute_alpha.json"))

    def _predictions(self, sessions: tuple[date, ...]) -> pd.DataFrame:
        rows = []
        for session in sessions:
            for number in range(12):
                rows.append({
                    "date": pd.Timestamp(session),
                    "security_id": f"S{number:02d}",
                    "membership_spell_id": f"S{number:02d}:01",
                    "close": 100.0,
                    "fold": "F2021",
                    "predicted_net_excess": 0.02 - number * 0.001,
                    "positive_probability": 0.70,
                })
        return pd.DataFrame(rows)

    def test_dual_absolute_gate_and_maximum_ten_candidates(self) -> None:
        sessions = (date(2021, 1, 4),)
        result = apply_no_trade_policy(self._predictions(sessions), self.config)
        self.assertEqual(int(result["entry_eligible"].sum()), 10)
        rejected = result.loc[result["security_id"].eq("S00")].copy()
        rejected["positive_probability"] = 0.59
        changed = pd.concat([result.loc[~result["security_id"].eq("S00")], rejected], ignore_index=True)
        changed = apply_no_trade_policy(changed.drop(columns=[
            "absolute_rank", "passes_return_gate", "passes_probability_gate", "entry_eligible", "exit_signal", "model"
        ]), self.config)
        self.assertFalse(changed.loc[changed["security_id"].eq("S00"), "entry_eligible"].iloc[0])

    def test_zero_eligible_means_no_buy_and_cash_is_allowed(self) -> None:
        sessions = (date(2021, 1, 4), date(2021, 1, 5))
        raw = self._predictions(sessions[:1])
        raw["predicted_net_excess"] = 0.001
        policy = apply_no_trade_policy(raw, self.config)
        orders, audit = generate_no_trade_orders(policy, sessions, self.config)
        self.assertEqual([order for order in orders if order.side is Side.BUY], [])
        self.assertEqual(audit["no_trade_signal_days"], 1)
        self.assertEqual(audit["minimum_required_holdings"], 0)
        self.assertFalse(audit["average_cash_is_hard_gate"])

    def test_model_exit_and_all_orders_use_next_session(self) -> None:
        sessions = (date(2021, 1, 4), date(2021, 1, 5), date(2021, 1, 6))
        raw = self._predictions(sessions[:2])
        raw.loc[raw["date"].eq(pd.Timestamp(sessions[1])), "predicted_net_excess"] = -0.01
        raw.loc[raw["date"].eq(pd.Timestamp(sessions[1])), "positive_probability"] = 0.40
        policy = apply_no_trade_policy(raw, self.config)
        orders, _ = generate_no_trade_orders(policy, sessions, self.config)
        buys = [order for order in orders if order.side is Side.BUY]
        sells = [order for order in orders if order.side is Side.SELL]
        self.assertEqual(len(buys), 10)
        self.assertEqual(len(sells), 10)
        self.assertTrue(all(order.signal_date < order.execute_date for order in orders))


if __name__ == "__main__":
    unittest.main()
