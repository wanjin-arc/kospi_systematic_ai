from __future__ import annotations

import tempfile
import unittest
import random
from datetime import date
from decimal import Decimal
from pathlib import Path

from kospi100_backtest.costs import CostBand, CostSchedule, ExecutionCostModel
from kospi100_backtest.demo import synthetic_scenario
from kospi100_backtest.engine import (
    BacktestEngine,
    BacktestInputError,
    EngineConfig,
    UnresolvedCorporateActionError,
)
from kospi100_backtest.io import write_result
from kospi100_backtest.types import Bar, CorporateAction, CorporateActionType, Order, OrderStatus, Side


def D(value: str) -> Decimal:
    return Decimal(value)


def zero_cost_engine(initial_cash: str = "5000000") -> BacktestEngine:
    schedule = CostSchedule((CostBand(date(2020, 1, 1), date(2025, 12, 31), D("0"), D("0")),))
    costs = ExecutionCostModel(schedule, commission_rate=D("0"), buy_slippage_rate=D("0"), sell_slippage_rate=D("0"))
    return BacktestEngine(EngineConfig(initial_cash=D(initial_cash)), costs)


def zero_cost_engine_with_config(*, initial_cash: str = "5000000", max_positions: int | None = None) -> BacktestEngine:
    schedule = CostSchedule((CostBand(date(2020, 1, 1), date(2025, 12, 31), D("0"), D("0")),))
    costs = ExecutionCostModel(schedule, commission_rate=D("0"), buy_slippage_rate=D("0"), sell_slippage_rate=D("0"))
    return BacktestEngine(EngineConfig(initial_cash=D(initial_cash), max_positions=max_positions), costs)


class BacktestEngineTests(unittest.TestCase):
    def test_target_weight_uses_prior_close_equity_and_whole_shares(self) -> None:
        sessions = (date(2023, 1, 2), date(2023, 1, 3), date(2023, 1, 4))
        bars = (
            Bar(sessions[1], "A", D("100"), D("200"), D("100"), D("200")),
            Bar(sessions[1], "B", D("300"), D("300"), D("300"), D("300")),
            Bar(sessions[2], "A", D("200"), D("200"), D("200"), D("200")),
            Bar(sessions[2], "B", D("300"), D("300"), D("300"), D("300")),
        )
        orders = (
            Order("BUY-A", sessions[0], sessions[1], "A", Side.BUY, target_weight=D("0.4")),
            Order("BUY-B", sessions[1], sessions[2], "B", Side.BUY, target_weight=D("0.5")),
        )
        result = zero_cost_engine_with_config(initial_cash="1000").run(sessions, bars, orders)
        # A is worth 800 at the second close, so prior-close equity is 1,400.
        # B receives a 700 budget and therefore buys two whole shares.
        self.assertEqual(result.final_positions, {"A": 4, "B": 2})

    def test_max_positions_rejects_excess_entry(self) -> None:
        sessions = (date(2023, 1, 2), date(2023, 1, 3))
        bars = (
            Bar(sessions[1], "A", D("100"), D("100"), D("100"), D("100")),
            Bar(sessions[1], "B", D("100"), D("100"), D("100"), D("100")),
        )
        orders = (
            Order("BUY-A", sessions[0], sessions[1], "A", Side.BUY, quantity=1, priority=1),
            Order("BUY-B", sessions[0], sessions[1], "B", Side.BUY, quantity=1, priority=2),
        )
        result = zero_cost_engine_with_config(max_positions=1).run(sessions, bars, orders)
        statuses = {event.order_id: event.status for event in result.order_events}
        self.assertEqual(result.final_positions, {"A": 1})
        self.assertEqual(statuses["BUY-B"], OrderStatus.REJECTED_MAX_POSITIONS)

    def test_max_holding_period_exits_at_open_after_exact_interval(self) -> None:
        sessions = (
            date(2023, 1, 2),
            date(2023, 1, 3),
            date(2023, 1, 4),
            date(2023, 1, 5),
            date(2023, 1, 6),
        )
        bars = tuple(
            Bar(session, "A", D(str(100 + index)), D(str(100 + index)), D(str(100 + index)), D(str(100 + index)))
            for index, session in enumerate(sessions[1:], start=1)
        )
        order = Order(
            "BUY",
            sessions[0],
            sessions[1],
            "A",
            Side.BUY,
            quantity=1,
            max_holding_sessions=2,
        )
        result = zero_cost_engine().run(sessions, bars, (order,))
        exit_fill = next(fill for fill in result.fills if fill.side is Side.SELL)
        self.assertEqual(exit_fill.session, sessions[3])
        self.assertEqual(exit_fill.reason, "TIME_EXIT")
        self.assertEqual(result.final_positions, {})

    def test_reference_scenario_covers_gap_halt_partial_stop_split_and_reconciles(self) -> None:
        sessions, bars, orders, actions, benchmark = synthetic_scenario()
        result = BacktestEngine().run(sessions, bars, orders, corporate_actions=actions, benchmark_close=benchmark)
        statuses = {event.order_id: event.status for event in result.order_events}
        self.assertEqual(statuses["BUY-B-GAP"], OrderStatus.UNFILLED_GAP_LIMIT)
        self.assertEqual(statuses["BUY-C-HALT"], OrderStatus.UNFILLED_NOT_TRADABLE)
        self.assertEqual(statuses["BUY-E-PARTIAL"], OrderStatus.PARTIALLY_FILLED)
        risk_fill = next(fill for fill in result.fills if fill.order_id.startswith("RISK:"))
        self.assertEqual(risk_fill.reference_price, D("9500"))
        self.assertEqual(risk_fill.reason, "STOP_FIRST_SAME_BAR")
        d_sell = next(fill for fill in result.fills if fill.order_id == "SELL-D")
        self.assertEqual(d_sell.quantity, 8)
        self.assertTrue(result.reconciliation.passed)
        self.assertEqual(result.final_positions, {})

    def test_opening_gap_through_stop_fills_at_adverse_open(self) -> None:
        sessions = (date(2023, 1, 2), date(2023, 1, 3))
        bars = (
            Bar(sessions[0], "A", D("100"), D("101"), D("99"), D("100")),
            Bar(sessions[1], "A", D("90"), D("92"), D("88"), D("91")),
        )
        order = Order("BUY", date(2023, 1, 2), date(2023, 1, 3), "A", Side.BUY, quantity=1, stop_price=D("95"))
        # Entry and stop happen on the same second session: open is already
        # below the predeclared stop, so the conservative exit uses open 90.
        result = zero_cost_engine().run(sessions, bars, (order,))
        sell = next(fill for fill in result.fills if fill.side is Side.SELL)
        self.assertEqual((sell.reference_price, sell.reason), (D("90"), "STOP_GAP"))

    def test_cash_priority_and_integer_quantity_are_deterministic(self) -> None:
        sessions = (date(2023, 1, 2), date(2023, 1, 3))
        bars = (
            Bar(sessions[1], "A", D("10000"), D("10000"), D("10000"), D("10000")),
            Bar(sessions[1], "B", D("10000"), D("10000"), D("10000"), D("10000")),
        )
        orders = (
            Order("BUY-B", sessions[0], sessions[1], "B", Side.BUY, quantity=1, priority=2),
            Order("BUY-A", sessions[0], sessions[1], "A", Side.BUY, quantity=1, priority=1),
        )
        result = zero_cost_engine("10000").run(sessions, bars, orders)
        self.assertEqual(result.final_positions, {"A": 1})
        self.assertEqual(next(event for event in result.order_events if event.order_id == "BUY-B").status, OrderStatus.REJECTED_INSUFFICIENT_CASH)

    def test_stale_mark_is_explicit_during_suspension(self) -> None:
        sessions = (date(2023, 1, 2), date(2023, 1, 3), date(2023, 1, 4))
        bars = (
            Bar(sessions[1], "A", D("100"), D("100"), D("100"), D("100")),
            Bar(sessions[2], "A", None, None, None, None, tradable=False),
        )
        order = Order("BUY", sessions[0], sessions[1], "A", Side.BUY, quantity=1)
        result = zero_cost_engine().run(sessions, bars, (order,))
        self.assertEqual(result.equity_curve[-1].stale_position_count, 1)
        self.assertEqual(result.position_snapshots[-1].mark_status, "STALE_LAST_VALID_CLOSE")

    def test_excess_sell_is_rejected_instead_of_creating_short(self) -> None:
        sessions = (date(2023, 1, 2), date(2023, 1, 3), date(2023, 1, 4))
        bars = (
            Bar(sessions[1], "A", D("100"), D("100"), D("100"), D("100")),
            Bar(sessions[2], "A", D("100"), D("100"), D("100"), D("100")),
        )
        orders = (
            Order("BUY", sessions[0], sessions[1], "A", Side.BUY, quantity=1),
            Order("SELL", sessions[1], sessions[2], "A", Side.SELL, quantity=2),
        )
        result = zero_cost_engine().run(sessions, bars, orders)
        self.assertEqual(result.final_positions, {"A": 1})
        self.assertEqual(result.order_events[-1].status, OrderStatus.REJECTED_EXCESS_SELL)

    def test_fractional_reverse_split_requires_and_uses_cash_in_lieu(self) -> None:
        sessions = (date(2023, 1, 2), date(2023, 1, 3), date(2023, 1, 4))
        bars = (
            Bar(sessions[1], "A", D("100"), D("100"), D("100"), D("100")),
            Bar(sessions[2], "A", D("200"), D("200"), D("200"), D("200")),
        )
        order = Order("BUY", sessions[0], sessions[1], "A", Side.BUY, quantity=3)
        action = CorporateAction("RS", sessions[2], "A", CorporateActionType.SPLIT, share_multiplier=D("0.5"), cash_in_lieu_price=D("200"))
        result = zero_cost_engine().run(sessions, bars, (order,), corporate_actions=(action,))
        self.assertEqual(result.final_positions, {"A": 1})
        ca_cash = [entry.amount for entry in result.cash_ledger if entry.category == "CORPORATE_ACTION_CASH"]
        self.assertEqual(ca_cash, [D("100.0")])
        self.assertTrue(result.reconciliation.passed)

    def test_successor_action_transforms_identity_and_quantity_before_exit(self) -> None:
        sessions = (date(2023, 1, 2), date(2023, 1, 3), date(2023, 1, 4), date(2023, 1, 5))
        bars = (
            Bar(sessions[1], "OLD", D("100"), D("100"), D("100"), D("100")),
            Bar(sessions[2], "NEW", D("67"), D("67"), D("67"), D("67")),
            Bar(sessions[3], "NEW", D("70"), D("70"), D("70"), D("70")),
        )
        orders = (
            Order("BUY-OLD", sessions[0], sessions[1], "OLD", Side.BUY, quantity=2),
            Order("SELL-NEW", sessions[2], sessions[3], "NEW", Side.SELL, quantity=None),
        )
        action = CorporateAction(
            "MERGER",
            sessions[2],
            "OLD",
            CorporateActionType.SUCCESSOR,
            share_multiplier=D("1.5"),
            successor_security_id="NEW",
        )
        result = zero_cost_engine().run(sessions, bars, orders, corporate_actions=(action,))
        self.assertEqual(next(fill for fill in result.fills if fill.order_id == "SELL-NEW").quantity, 3)
        self.assertEqual(result.final_positions, {})
        self.assertTrue(result.reconciliation.passed)

    def test_target_fill_is_not_better_than_predeclared_target(self) -> None:
        sessions = (date(2023, 1, 2), date(2023, 1, 3), date(2023, 1, 4))
        bars = (
            Bar(sessions[1], "A", D("100"), D("105"), D("99"), D("104")),
            Bar(sessions[2], "A", D("108"), D("115"), D("107"), D("112")),
        )
        order = Order("BUY", sessions[0], sessions[1], "A", Side.BUY, quantity=1, target_price=D("110"))
        result = zero_cost_engine().run(sessions, bars, (order,))
        sell = next(fill for fill in result.fills if fill.side is Side.SELL)
        self.assertEqual((sell.reference_price, sell.reason), (D("110"), "TARGET"))

    def test_partial_sell_cancels_remainder_and_keeps_long_position(self) -> None:
        sessions = (date(2023, 1, 2), date(2023, 1, 3), date(2023, 1, 4))
        bars = (
            Bar(sessions[1], "A", D("100"), D("100"), D("100"), D("100")),
            Bar(sessions[2], "A", D("101"), D("101"), D("101"), D("101"), max_sell_quantity=2),
        )
        orders = (
            Order("BUY", sessions[0], sessions[1], "A", Side.BUY, quantity=5),
            Order("SELL", sessions[1], sessions[2], "A", Side.SELL, quantity=None),
        )
        result = zero_cost_engine().run(sessions, bars, orders)
        self.assertEqual(result.final_positions, {"A": 3})
        self.assertEqual(result.order_events[-1].status, OrderStatus.PARTIALLY_FILLED)

    def test_unresolved_action_on_held_position_fails_closed(self) -> None:
        sessions = (date(2023, 1, 2), date(2023, 1, 3), date(2023, 1, 4))
        bars = (
            Bar(sessions[1], "A", D("100"), D("100"), D("100"), D("100")),
            Bar(sessions[2], "A", D("100"), D("100"), D("100"), D("100")),
        )
        order = Order("BUY", sessions[0], sessions[1], "A", Side.BUY, quantity=1)
        action = CorporateAction("RIGHTS", sessions[2], "A", CorporateActionType.UNRESOLVED, source_status="PENDING_TERMS")
        with self.assertRaises(UnresolvedCorporateActionError):
            zero_cost_engine().run(sessions, bars, (order,), corporate_actions=(action,))

    def test_duplicate_order_id_and_same_day_signal_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Order("BAD", date(2023, 1, 2), date(2023, 1, 2), "A", Side.BUY, quantity=1)
        sessions = (date(2023, 1, 2), date(2023, 1, 3))
        bar = Bar(sessions[1], "A", D("100"), D("100"), D("100"), D("100"))
        order = Order("DUP", sessions[0], sessions[1], "A", Side.BUY, quantity=1)
        with self.assertRaises(BacktestInputError):
            zero_cost_engine().run(sessions, (bar,), (order, order))

    def test_serialized_outputs_are_byte_deterministic(self) -> None:
        scenario = synthetic_scenario()
        result_one = BacktestEngine().run(scenario[0], scenario[1], scenario[2], corporate_actions=scenario[3], benchmark_close=scenario[4])
        result_two = BacktestEngine().run(scenario[0], reversed(scenario[1]), reversed(scenario[2]), corporate_actions=reversed(scenario[3]), benchmark_close=scenario[4])
        self.assertEqual((result_one.input_hash, result_one.config_hash), (result_two.input_hash, result_two.config_hash))
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first"
            second = Path(tmp) / "second"
            write_result(result_one, first)
            write_result(result_two, second)
            first_bytes = {path.name: path.read_bytes() for path in first.iterdir()}
            second_bytes = {path.name: path.read_bytes() for path in second.iterdir()}
            self.assertEqual(first_bytes, second_bytes)

    def test_250_seeded_accounting_stress_scenarios_reconcile(self) -> None:
        rng = random.Random(20260818)
        sessions = (date(2023, 6, 1), date(2023, 6, 2), date(2023, 6, 5))
        for scenario_id in range(250):
            entry = D(str(rng.randint(1000, 100000)))
            exit_price = entry * D(str(rng.randint(70, 130))) / D("100")
            requested = rng.randint(1, 50)
            buy_cap = rng.choice((None, 0, rng.randint(1, requested)))
            sell_cap = rng.choice((None, 0, rng.randint(1, requested)))
            bars = (
                Bar(sessions[1], "A", entry, entry, entry, entry, max_buy_quantity=buy_cap),
                Bar(sessions[2], "A", exit_price, exit_price, exit_price, exit_price, max_sell_quantity=sell_cap),
            )
            orders = (
                Order(f"BUY-{scenario_id}", sessions[0], sessions[1], "A", Side.BUY, quantity=requested),
                Order(f"SELL-{scenario_id}", sessions[1], sessions[2], "A", Side.SELL, quantity=None),
            )
            result = BacktestEngine().run(sessions, bars, orders)
            self.assertTrue(result.reconciliation.passed, scenario_id)
            self.assertGreaterEqual(result.final_cash, D("0"), scenario_id)
            self.assertTrue(all(quantity >= 0 for quantity in result.final_positions.values()), scenario_id)


if __name__ == "__main__":
    unittest.main()
