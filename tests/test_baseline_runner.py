from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from kospi100_baseline.runner import generate_signal_orders


class BaselineRunnerTests(unittest.TestCase):
    def test_rank_tie_order_t_plus_one_cap_weight_and_holding_are_frozen(self) -> None:
        signal = date(2023, 1, 2)
        execution = date(2023, 1, 3)
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime([signal, signal, signal]),
                "security_id": ["B", "A", "C"],
                "close": [100.0, 200.0, 300.0],
                "excess_return126": [0.2, 0.2, 0.1],
                "baseline_candidate": [True, True, True],
            }
        )
        orders = generate_signal_orders(
            frame,
            (signal, execution),
            holding_sessions=10,
            maximum_holdings=5,
        )
        self.assertEqual([order.security_id for order in orders], ["A", "B", "C"])
        self.assertTrue(all(order.signal_date == signal and order.execute_date == execution for order in orders))
        self.assertEqual(str(orders[0].target_weight), "0.10")
        self.assertEqual(str(orders[0].limit_price), "210.000")
        self.assertEqual(orders[0].max_holding_sessions, 10)


if __name__ == "__main__":
    unittest.main()
