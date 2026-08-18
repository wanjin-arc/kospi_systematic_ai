from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from kospi100_backtest.config import engine_from_files
from kospi100_backtest.costs import ExecutionCostModel, default_kospi_cost_schedule
from kospi100_backtest.types import Side


class CostScheduleTests(unittest.TestCase):
    def test_verified_kospi_total_sell_rates_at_every_boundary(self) -> None:
        schedule = default_kospi_cost_schedule()
        expected = {
            date(2011, 1, 1): Decimal("0.0030"),
            date(2019, 6, 2): Decimal("0.0030"),
            date(2019, 6, 3): Decimal("0.0025"),
            date(2021, 1, 1): Decimal("0.0023"),
            date(2023, 1, 1): Decimal("0.0020"),
            date(2024, 1, 1): Decimal("0.0018"),
            date(2025, 1, 1): Decimal("0.0015"),
            date(2025, 12, 31): Decimal("0.0015"),
        }
        for session, total in expected.items():
            with self.subTest(session=session):
                self.assertEqual(sum(schedule.rates_on(session), Decimal("0")), total)

    def test_unknown_date_fails_closed(self) -> None:
        with self.assertRaises(KeyError):
            default_kospi_cost_schedule().rates_on(date(2026, 1, 1))

    def test_costs_round_down_to_one_won_and_slippage_is_adverse(self) -> None:
        model = ExecutionCostModel(default_kospi_cost_schedule())
        self.assertEqual(model.commission(Decimal("9999")), Decimal("1"))
        self.assertEqual(model.fill_price(Side.BUY, Decimal("10000")), Decimal("10010.000"))
        self.assertEqual(model.fill_price(Side.SELL, Decimal("10000")), Decimal("9990.000"))
        transaction, rural = model.sell_taxes(date(2023, 1, 2), Decimal("1000000"))
        self.assertEqual((transaction, rural), (Decimal("500"), Decimal("1500")))

    def test_frozen_config_files_load_the_verified_schedule(self) -> None:
        root = Path(__file__).resolve().parents[1]
        engine = engine_from_files(root / "configs/phase2_engine.json", root / "configs/kospi_sell_cost_schedule.csv")
        self.assertEqual(engine.config.initial_cash, Decimal("5000000"))
        self.assertEqual(sum(engine.cost_model.schedule.rates_on(date(2023, 1, 2)), Decimal("0")), Decimal("0.0020"))


if __name__ == "__main__":
    unittest.main()
