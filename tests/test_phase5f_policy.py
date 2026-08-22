from __future__ import annotations

import unittest
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from kospi100_temporal_risk.config import load_config
from kospi100_temporal_risk.policy import apply_temporal_policy, generate_temporal_orders


CONFIG = load_config(Path("configs/phase5f_temporal_risk.json"))


def _predictions(anomaly: bool = False) -> pd.DataFrame:
    rows = []
    for index in range(12):
        rows.append({
            "date": pd.Timestamp("2020-01-02"),
            "security_id": f"S{index:02d}",
            "membership_spell_id": f"S{index:02d}:1",
            "close": 100.0,
            "fold": "F2020",
            "predicted_mean_net_excess": 0.02 - index * 0.001,
            "predicted_median_net_excess": 0.01,
            "market_anomaly": anomaly,
        })
    return pd.DataFrame(rows)


class Phase5FPolicyTests(unittest.TestCase):
    def test_dual_regression_gate_ranks_and_caps_at_ten(self) -> None:
        policy = apply_temporal_policy(_predictions(), CONFIG)
        self.assertEqual(int(policy["entry_eligible"].sum()), 10)
        selected = policy.loc[policy["entry_eligible"]].sort_values("absolute_rank")
        self.assertEqual(selected.iloc[0]["security_id"], "S00")
        self.assertEqual(selected.iloc[-1]["security_id"], "S09")

    def test_median_and_anomaly_veto_allow_zero_holdings(self) -> None:
        frame = _predictions()
        frame["predicted_median_net_excess"] = 0.0
        policy = apply_temporal_policy(frame, CONFIG)
        self.assertFalse(policy["entry_eligible"].any())
        anomaly = apply_temporal_policy(_predictions(anomaly=True), CONFIG)
        self.assertFalse(anomaly["entry_eligible"].any())
        self.assertTrue(anomaly["exit_signal"].all())

    def test_orders_execute_only_on_next_session_and_audit_veto(self) -> None:
        sessions = tuple(date(2020, 1, 2) + timedelta(days=index) for index in range(3))
        policy = apply_temporal_policy(_predictions(), CONFIG)
        orders, audit = generate_temporal_orders(policy, sessions, CONFIG)
        buys = [order for order in orders if order.side.value == "BUY"]
        self.assertEqual(len(buys), 10)
        self.assertTrue(all(order.signal_date == sessions[0] for order in buys))
        self.assertTrue(all(order.execute_date == sessions[1] for order in buys))
        self.assertEqual(audit["anomaly_veto_signal_days"], 0)

        veto = apply_temporal_policy(_predictions(anomaly=True), CONFIG)
        _, veto_audit = generate_temporal_orders(veto, sessions, CONFIG)
        self.assertEqual(veto_audit["entry_orders"], 0)
        self.assertEqual(veto_audit["anomaly_veto_signal_days"], 1)

    def test_future_prediction_does_not_change_past_orders(self) -> None:
        sessions = tuple(date(2020, 1, 2) + timedelta(days=index) for index in range(4))
        original = _predictions()
        later = _predictions()
        later["date"] = pd.Timestamp("2020-01-03")
        combined = pd.concat([original, later], ignore_index=True)
        first, _ = generate_temporal_orders(apply_temporal_policy(original, CONFIG), sessions, CONFIG)
        second, _ = generate_temporal_orders(apply_temporal_policy(combined, CONFIG), sessions, CONFIG)
        past_second = tuple(order for order in second if order.signal_date == sessions[0])
        self.assertEqual(first, past_second)


if __name__ == "__main__":
    unittest.main()
