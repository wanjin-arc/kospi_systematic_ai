from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from kospi100_backtest.types import Side
from kospi100_rank_persistence.config import load_config
from kospi100_rank_persistence.policy import apply_causal_persistence, generate_persistent_orders


class Phase5CPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(Path("configs/phase5c_persistent_ranking.json"))

    def test_future_score_cannot_change_earlier_persistent_scores(self) -> None:
        sessions = tuple(pd.bdate_range("2018-01-02", periods=4).date)
        rows = []
        for offset, session in enumerate(sessions):
            for security, score in (("A", 0.2 + offset * 0.1), ("B", 0.8 - offset * 0.1)):
                rows.append(
                    {
                        "date": pd.Timestamp(session),
                        "security_id": security,
                        "membership_spell_id": f"{security}:01",
                        "score": score,
                        "fold": "I2018",
                        "close": 100.0,
                    }
                )
        original = pd.DataFrame(rows)
        changed = original.copy()
        changed.loc[
            changed["date"].eq(pd.Timestamp(sessions[-1])) & changed["security_id"].eq("A"), "score"
        ] = 100.0
        first = apply_causal_persistence(original, sessions, self.config)
        second = apply_causal_persistence(changed, sessions, self.config)
        earlier = first["date"] < pd.Timestamp(sessions[-1])
        self.assertEqual(
            first.loc[earlier, ["date", "security_id", "smoothed_score", "score"]].to_csv(index=False),
            second.loc[earlier, ["date", "security_id", "smoothed_score", "score"]].to_csv(index=False),
        )

    def test_ema_resets_on_exchange_session_gap_and_spell(self) -> None:
        sessions = tuple(pd.bdate_range("2018-01-02", periods=5).date)
        frame = pd.DataFrame(
            [
                {"date": pd.Timestamp(sessions[0]), "security_id": "A", "membership_spell_id": "A:01", "score": 0.9, "fold": "I2018", "close": 100},
                {"date": pd.Timestamp(sessions[1]), "security_id": "A", "membership_spell_id": "A:01", "score": 0.6, "fold": "I2018", "close": 100},
                {"date": pd.Timestamp(sessions[3]), "security_id": "A", "membership_spell_id": "A:01", "score": 0.2, "fold": "I2018", "close": 100},
                {"date": pd.Timestamp(sessions[4]), "security_id": "A", "membership_spell_id": "A:02", "score": 0.4, "fold": "I2018", "close": 100},
            ]
        )
        result = apply_causal_persistence(frame, sessions, self.config).sort_values("date")
        self.assertAlmostEqual(float(result.iloc[2]["smoothed_score"]), 0.2)
        self.assertAlmostEqual(float(result.iloc[3]["smoothed_score"]), 0.4)

    def test_top20_fallback_and_rank_loss_orders_execute_next_session(self) -> None:
        sessions = (date(2018, 1, 2), date(2018, 1, 3), date(2018, 1, 4))
        rows = []
        for day_index, session in enumerate(sessions[:2]):
            securities = [f"S{number:02d}" for number in range(25)]
            if day_index == 1:
                securities = securities[1:] + securities[:1]
            for rank, security in enumerate(securities, start=1):
                rows.append(
                    {
                        "date": pd.Timestamp(session),
                        "security_id": security,
                        "membership_spell_id": f"{security}:01",
                        "score": 1.0 - rank / 100.0,
                        "daily_rank": rank,
                        "fold": "I2018",
                        "close": 100.0,
                        "candidate": self.config.policy_candidate,
                    }
                )
        orders, audit = generate_persistent_orders(pd.DataFrame(rows), sessions, self.config)
        buys = [order for order in orders if order.side is Side.BUY]
        exits = [order for order in orders if order.side is Side.SELL]
        self.assertEqual(len(buys), 40)
        self.assertEqual(audit["desired_entry_orders"], 20)
        self.assertEqual(audit["fallback_entry_orders"], 20)
        self.assertEqual(len(exits), 1)
        self.assertEqual(exits[0].security_id, "S00")
        self.assertEqual(exits[0].signal_date, sessions[1])
        self.assertEqual(exits[0].execute_date, sessions[2])
        self.assertTrue(all(order.signal_date < order.execute_date for order in orders))
        self.assertTrue(all((order.max_holding_sessions == 20) for order in buys))


if __name__ == "__main__":
    unittest.main()
