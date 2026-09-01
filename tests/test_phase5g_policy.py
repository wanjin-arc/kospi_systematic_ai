from __future__ import annotations

import unittest
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from kospi100_multihorizon.config import load_config
from kospi100_multihorizon.policy import apply_consensus_policy, generate_orders


CONFIG = load_config(Path("configs/phase5g_multihorizon_consensus.json"))


def _predictions() -> pd.DataFrame:
    rows = []
    for index in range(12):
        rows.append({
            "date": pd.Timestamp("2020-01-02"), "security_id": f"S{index:02d}",
            "membership_spell_id": f"S{index:02d}:1", "close": 100.0, "fold": "ITEST",
            "predicted_net_excess_5": 0.020 - index * 0.001,
            "predicted_net_excess_10": 0.015 - index * 0.001,
            "predicted_net_excess_20": 0.010 - index * 0.001,
        })
    return pd.DataFrame(rows)


class Phase5GPolicyTests(unittest.TestCase):
    def test_consensus_ranks_daily_and_allows_zero_to_ten(self) -> None:
        policy = apply_consensus_policy(_predictions(), CONFIG)
        self.assertEqual(int(policy["entry_eligible"].sum()), 10)
        selected = policy.loc[policy["entry_eligible"]].sort_values("consensus_rank")
        self.assertEqual(selected.iloc[0]["security_id"], "S00")
        self.assertEqual(selected.iloc[-1]["security_id"], "S09")
        negative = _predictions()
        negative[["predicted_net_excess_5", "predicted_net_excess_10", "predicted_net_excess_20"]] = -0.01
        self.assertFalse(apply_consensus_policy(negative, CONFIG)["entry_eligible"].any())

    def test_two_positive_horizons_and_magnitude_are_both_required(self) -> None:
        frame = _predictions().iloc[[0]].copy()
        frame.loc[:, ["predicted_net_excess_5", "predicted_net_excess_10", "predicted_net_excess_20"]] = [0.004, 0.003, -0.001]
        self.assertTrue(bool(apply_consensus_policy(frame, CONFIG).iloc[0]["entry_eligible"]))
        frame.loc[:, ["predicted_net_excess_5", "predicted_net_excess_10", "predicted_net_excess_20"]] = [0.001, 0.0005, -0.001]
        self.assertFalse(bool(apply_consensus_policy(frame, CONFIG).iloc[0]["entry_eligible"]))

    def test_orders_execute_next_session_and_future_scores_do_not_change_past(self) -> None:
        sessions = tuple(date(2020, 1, 2) + timedelta(days=value) for value in range(4))
        original = apply_consensus_policy(_predictions(), CONFIG)
        first, audit = generate_orders(original, sessions, CONFIG)
        self.assertEqual(audit["entry_orders"], 10)
        self.assertTrue(all(order.execute_date == sessions[1] for order in first))
        later = _predictions()
        later["date"] = pd.Timestamp("2020-01-03")
        combined = apply_consensus_policy(pd.concat([_predictions(), later], ignore_index=True), CONFIG)
        second, _ = generate_orders(combined, sessions, CONFIG)
        past = tuple(order for order in second if order.signal_date == sessions[0])
        self.assertEqual(first, past)


if __name__ == "__main__":
    unittest.main()
