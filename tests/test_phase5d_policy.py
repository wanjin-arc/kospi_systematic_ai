from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from kospi100_backtest.types import Side
from kospi100_selective_ranking.config import load_config
from kospi100_selective_ranking.policy import apply_selective_scores, generate_selective_orders


class Phase5DPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(Path("configs/phase5d_selective_ranking.json"))

    def _raw(self, sessions: tuple[date, ...]) -> pd.DataFrame:
        rows = []
        for offset, session in enumerate(sessions):
            for number in range(12):
                rows.append(
                    {
                        "date": pd.Timestamp(session),
                        "security_id": f"S{number:02d}",
                        "membership_spell_id": f"S{number:02d}:01",
                        "raw_prediction": 0.40 + number * 0.01 + offset * 0.001,
                        "fold": "F2021",
                        "close": 100.0,
                        "index_trend_200": 0.1,
                        "breadth_above_sma200": 0.6,
                    }
                )
        return pd.DataFrame(rows)

    def test_future_prediction_cannot_change_earlier_scores(self) -> None:
        sessions = tuple(pd.bdate_range("2021-01-04", periods=4).date)
        raw = self._raw(sessions)
        changed = raw.copy()
        changed.loc[
            changed["date"].eq(pd.Timestamp(sessions[-1])) & changed["security_id"].eq("S11"),
            "raw_prediction",
        ] = 100.0
        first = apply_selective_scores(raw, sessions, self.config)
        second = apply_selective_scores(changed, sessions, self.config)
        earlier = first["date"] < pd.Timestamp(sessions[-1])
        columns = ["date", "security_id", "smoothed_raw_prediction", "score_z", "score"]
        self.assertEqual(first.loc[earlier, columns].to_csv(index=False), second.loc[earlier, columns].to_csv(index=False))

    def test_market_regimes_allow_ten_five_or_zero_capacity(self) -> None:
        sessions = (date(2021, 1, 4), date(2021, 1, 5), date(2021, 1, 6))
        raw = self._raw(sessions)
        raw.loc[raw["date"].eq(pd.Timestamp(sessions[1])), "breadth_above_sma200"] = 0.4
        raw.loc[raw["date"].eq(pd.Timestamp(sessions[2])), ["index_trend_200", "breadth_above_sma200"]] = [-0.1, 0.4]
        result = apply_selective_scores(raw, sessions, self.config)
        capacities = result.groupby("date")["regime_capacity"].first().tolist()
        regimes = result.groupby("date")["market_regime"].first().tolist()
        self.assertEqual(regimes, ["risk_on", "neutral", "risk_off"])
        self.assertEqual(capacities, [10, 5, 0])
        self.assertFalse(result.loc[result["market_regime"].eq("risk_off"), "entry_eligible"].any())

    def test_no_score_means_no_required_position_and_orders_use_next_session(self) -> None:
        sessions = (date(2021, 1, 4), date(2021, 1, 5), date(2021, 1, 6), date(2021, 1, 7))
        rows = []
        for index, session in enumerate(sessions[:3]):
            regime = ("risk_on", "neutral", "risk_off")[index]
            capacity = (10, 5, 0)[index]
            for rank in range(1, 13):
                rows.append(
                    {
                        "date": pd.Timestamp(session),
                        "security_id": f"S{rank:02d}",
                        "membership_spell_id": f"S{rank:02d}:01",
                        "score": 1.0 - rank / 100.0,
                        "score_z": 1.5 if index == 0 and rank <= 2 else -0.5,
                        "daily_rank": rank,
                        "market_regime": regime,
                        "regime_capacity": capacity,
                        "entry_eligible": index == 0 and rank <= 2,
                        "fold": "F2021",
                        "close": 100.0,
                        "candidate": self.config.policy_candidate,
                    }
                )
        orders, audit = generate_selective_orders(pd.DataFrame(rows), sessions, self.config)
        buys = [order for order in orders if order.side is Side.BUY]
        risk_off_buys = [order for order in buys if order.signal_date == sessions[2]]
        risk_off_exits = [order for order in orders if order.side is Side.SELL and order.signal_date == sessions[2]]
        self.assertEqual(len(buys), 2)
        self.assertEqual(risk_off_buys, [])
        self.assertEqual(len(risk_off_exits), 2)
        self.assertEqual(audit["minimum_required_holdings"], 0)
        self.assertFalse(audit["average_cash_is_hard_gate"])
        self.assertTrue(all(order.signal_date < order.execute_date for order in orders))


if __name__ == "__main__":
    unittest.main()
