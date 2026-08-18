from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, ROUND_FLOOR
from typing import Iterable, Mapping

from .costs import ExecutionCostModel, default_kospi_cost_schedule
from .metrics import calculate_metrics
from .types import (
    AuditEvent,
    Bar,
    CashLedgerEntry,
    ClosedTrade,
    CorporateAction,
    CorporateActionType,
    EquityPoint,
    Fill,
    Order,
    OrderEvent,
    OrderStatus,
    PositionLedgerEntry,
    PositionSnapshot,
    ReconciliationReport,
    RunResult,
    Side,
    ZERO,
)


class BacktestInputError(ValueError):
    pass


class UnresolvedCorporateActionError(RuntimeError):
    pass


@dataclass(frozen=True)
class EngineConfig:
    initial_cash: Decimal = Decimal("5000000")
    allow_pyramiding: bool = False
    apply_barriers_on_entry_day: bool = True
    same_bar_policy: str = "STOP_FIRST"
    day_order_remainder_policy: str = "CANCEL"
    max_positions: int | None = None

    def __post_init__(self) -> None:
        if self.initial_cash <= ZERO:
            raise ValueError("initial_cash must be positive")
        if self.allow_pyramiding:
            raise ValueError("pyramiding is outside the frozen Phase-2 baseline")
        if self.max_positions is not None and self.max_positions <= 0:
            raise ValueError("max_positions must be positive")
        if self.same_bar_policy != "STOP_FIRST":
            raise ValueError("Phase 2 supports only the frozen STOP_FIRST policy")
        if self.day_order_remainder_policy != "CANCEL":
            raise ValueError("Phase 2 supports only deterministic day-order cancellation")


@dataclass
class _Position:
    security_id: str
    quantity: int
    cost_basis: Decimal
    stop_price: Decimal | None
    target_price: Decimal | None
    entry_date: date
    entry_session_index: int
    cycle_entry_cost: Decimal
    max_holding_sessions: int | None
    cycle_realized_pnl: Decimal = ZERO


class BacktestEngine:
    """Pure daily-bar execution/accounting engine.

    The engine consumes already-frozen orders. It does not calculate features,
    ranks, labels, or strategy rules, and therefore cannot silently use future
    data to create an order.
    """

    def __init__(
        self,
        config: EngineConfig | None = None,
        cost_model: ExecutionCostModel | None = None,
    ) -> None:
        self.config = config or EngineConfig()
        self.cost_model = cost_model or ExecutionCostModel(default_kospi_cost_schedule())

    def run(
        self,
        sessions: Iterable[date],
        bars: Iterable[Bar],
        orders: Iterable[Order],
        *,
        corporate_actions: Iterable[CorporateAction] = (),
        benchmark_close: Mapping[date, Decimal] | None = None,
    ) -> RunResult:
        session_list = tuple(sessions)
        bar_list = tuple(bars)
        order_list = tuple(orders)
        action_list = tuple(corporate_actions)
        self._validate_inputs(session_list, bar_list, order_list, action_list)

        bars_by_key = {(bar.session, bar.security_id): bar for bar in bar_list}
        bars_by_session: dict[date, list[Bar]] = defaultdict(list)
        for bar in bar_list:
            bars_by_session[bar.session].append(bar)
        orders_by_date: dict[date, list[Order]] = defaultdict(list)
        for order in order_list:
            orders_by_date[order.execute_date].append(order)
        actions_by_date: dict[date, list[CorporateAction]] = defaultdict(list)
        for action in action_list:
            actions_by_date[action.effective_date].append(action)

        cash = ZERO
        positions: dict[str, _Position] = {}
        last_marks: dict[str, Decimal] = {}
        fills: list[Fill] = []
        order_events: list[OrderEvent] = []
        cash_ledger: list[CashLedgerEntry] = []
        position_ledger: list[PositionLedgerEntry] = []
        position_snapshots: list[PositionSnapshot] = []
        equity_curve: list[EquityPoint] = []
        closed_trades: list[ClosedTrade] = []
        audit_events: list[AuditEvent] = []

        def post_cash(session: date, category: str, security_id: str, amount: Decimal, reference_id: str) -> None:
            nonlocal cash
            cash += amount
            cash_ledger.append(
                CashLedgerEntry(
                    entry_id=f"CASH-{len(cash_ledger):08d}",
                    session=session,
                    category=category,
                    security_id=security_id,
                    amount=amount,
                    balance_after=cash,
                    reference_id=reference_id,
                )
            )
            if cash < ZERO:
                raise AssertionError("cash ledger became negative")

        post_cash(session_list[0], "INITIAL_CAPITAL", "", self.config.initial_cash, "INITIAL")

        for session_index, session in enumerate(session_list):
            for action in sorted(actions_by_date.get(session, []), key=lambda item: (item.security_id, item.action_id)):
                cash = self._apply_corporate_action(
                    action,
                    session_index,
                    cash,
                    positions,
                    cash_ledger,
                    position_ledger,
                    closed_trades,
                    audit_events,
                )

            for security_id in sorted(tuple(positions)):
                position = positions.get(security_id)
                if position is None or position.max_holding_sessions is None:
                    continue
                if session_index - position.entry_session_index < position.max_holding_sessions:
                    continue
                signal_date = session_list[max(0, session_index - 1)]
                if signal_date == session:
                    raise AssertionError("a time exit cannot occur on the first session")
                time_exit = Order(
                    order_id=f"TIME:{session.isoformat()}:{security_id}",
                    signal_date=signal_date,
                    execute_date=session,
                    security_id=security_id,
                    side=Side.SELL,
                    quantity=None,
                    priority=-20_000,
                    reason="TIME_EXIT",
                )
                cash = self._process_sell_order(
                    time_exit,
                    bars_by_key.get((session, security_id)),
                    session_index,
                    cash,
                    positions,
                    fills,
                    order_events,
                    cash_ledger,
                    position_ledger,
                    closed_trades,
                )

            day_orders = orders_by_date.get(session, [])
            sell_orders = sorted(
                (item for item in day_orders if item.side is Side.SELL),
                key=lambda item: (item.priority, item.security_id, item.order_id),
            )
            buy_orders = sorted(
                (item for item in day_orders if item.side is Side.BUY),
                key=lambda item: (item.priority, item.security_id, item.order_id),
            )

            for order in sell_orders:
                bar = bars_by_key.get((session, order.security_id))
                cash = self._process_sell_order(
                    order,
                    bar,
                    session_index,
                    cash,
                    positions,
                    fills,
                    order_events,
                    cash_ledger,
                    position_ledger,
                    closed_trades,
                )
            for order in buy_orders:
                bar = bars_by_key.get((session, order.security_id))
                sizing_equity = equity_curve[-1].equity if equity_curve else self.config.initial_cash
                cash = self._process_buy_order(
                    order,
                    bar,
                    session_index,
                    cash,
                    positions,
                    fills,
                    order_events,
                    cash_ledger,
                    position_ledger,
                    sizing_equity,
                )

            for security_id in sorted(tuple(positions)):
                position = positions.get(security_id)
                if position is None or position.quantity == 0:
                    continue
                if not self.config.apply_barriers_on_entry_day and position.entry_date == session:
                    continue
                if position.stop_price is None and position.target_price is None:
                    continue
                bar = bars_by_key.get((session, security_id))
                if bar is None or not bar.tradable:
                    if bar is not None:
                        audit_events.append(
                            AuditEvent(session, "WARNING", "PROTECTIVE_EXIT_BLOCKED", security_id, "", "bar not tradable")
                        )
                    continue
                trigger = self._barrier_trigger(position, bar)
                if trigger is None:
                    continue
                reason, reference_price = trigger
                signal_date = session_list[max(0, session_index - 1)]
                if signal_date == session:
                    raise AssertionError("a held position cannot first exist before the first session")
                protective = Order(
                    order_id=f"RISK:{session.isoformat()}:{security_id}:{reason}",
                    signal_date=signal_date,
                    execute_date=session,
                    security_id=security_id,
                    side=Side.SELL,
                    quantity=None,
                    priority=-10_000,
                    reason=reason,
                )
                cash = self._process_sell_order(
                    protective,
                    bar,
                    session_index,
                    cash,
                    positions,
                    fills,
                    order_events,
                    cash_ledger,
                    position_ledger,
                    closed_trades,
                    reference_price_override=reference_price,
                )

            for bar in sorted(bars_by_session.get(session, []), key=lambda item: item.security_id):
                if bar.tradable and bar.close is not None and bar.close > ZERO:
                    last_marks[bar.security_id] = bar.close

            positions_value = ZERO
            stale_count = 0
            for security_id in sorted(positions):
                position = positions[security_id]
                if position.quantity <= 0:
                    continue
                bar = bars_by_key.get((session, security_id))
                if bar is not None and bar.tradable and bar.close is not None and bar.close > ZERO:
                    mark = bar.close
                    mark_status = "CURRENT_CLOSE"
                else:
                    mark = last_marks.get(security_id)
                    if mark is None:
                        raise BacktestInputError(f"no valid mark for held {security_id} on {session.isoformat()}")
                    mark_status = "STALE_LAST_VALID_CLOSE"
                    stale_count += 1
                    audit_events.append(
                        AuditEvent(session, "WARNING", "STALE_MARK", security_id, "", "last valid close carried forward")
                    )
                market_value = mark * position.quantity
                positions_value += market_value
                position_snapshots.append(
                    PositionSnapshot(
                        session=session,
                        security_id=security_id,
                        quantity=position.quantity,
                        cost_basis=position.cost_basis,
                        mark_price=mark,
                        market_value=market_value,
                        mark_status=mark_status,
                    )
                )

            equity = cash + positions_value
            previous_equity = equity_curve[-1].equity if equity_curve else self.config.initial_cash
            daily_return = equity / previous_equity - Decimal("1") if previous_equity else ZERO
            cash_weight = cash / equity if equity else ZERO
            equity_curve.append(
                EquityPoint(
                    session=session,
                    cash=cash,
                    positions_value=positions_value,
                    equity=equity,
                    daily_return=daily_return,
                    cash_weight=cash_weight,
                    stale_position_count=stale_count,
                    benchmark_close=(benchmark_close or {}).get(session),
                )
            )

        final_positions = {key: value.quantity for key, value in sorted(positions.items()) if value.quantity > 0}
        final_cost_basis = {key: value.cost_basis for key, value in sorted(positions.items()) if value.quantity > 0}
        reconciliation = self._reconcile(
            self.config.initial_cash,
            cash,
            cash_ledger,
            position_ledger,
            final_positions,
            fills,
            equity_curve,
            position_snapshots,
        )
        if not reconciliation.passed:
            raise AssertionError(f"ledger reconciliation failed: {reconciliation.detail}")

        result = RunResult(
            initial_cash=self.config.initial_cash,
            final_cash=cash,
            fills=tuple(fills),
            order_events=tuple(order_events),
            cash_ledger=tuple(cash_ledger),
            position_ledger=tuple(position_ledger),
            position_snapshots=tuple(position_snapshots),
            equity_curve=tuple(equity_curve),
            closed_trades=tuple(closed_trades),
            audit_events=tuple(audit_events),
            final_positions=final_positions,
            final_cost_basis=final_cost_basis,
            reconciliation=reconciliation,
            input_hash=self._input_hash(session_list, bar_list, order_list, action_list),
            config_hash=self._config_hash(),
        )
        return replace(result, metrics=calculate_metrics(result))

    def _validate_inputs(
        self,
        sessions: tuple[date, ...],
        bars: tuple[Bar, ...],
        orders: tuple[Order, ...],
        actions: tuple[CorporateAction, ...],
    ) -> None:
        if not sessions:
            raise BacktestInputError("sessions cannot be empty")
        if sessions != tuple(sorted(set(sessions))):
            raise BacktestInputError("sessions must be unique and strictly increasing")
        session_set = set(sessions)
        bar_keys = [(item.session, item.security_id) for item in bars]
        if len(bar_keys) != len(set(bar_keys)):
            raise BacktestInputError("duplicate bar key")
        if any(item.session not in session_set for item in bars):
            raise BacktestInputError("bar outside session calendar")
        order_ids = [item.order_id for item in orders]
        if len(order_ids) != len(set(order_ids)):
            raise BacktestInputError("duplicate order_id")
        if any(item.execute_date not in session_set or item.signal_date not in session_set for item in orders):
            raise BacktestInputError("order signal/execute date outside session calendar")
        action_ids = [item.action_id for item in actions]
        if len(action_ids) != len(set(action_ids)):
            raise BacktestInputError("duplicate corporate action id")
        if any(item.effective_date not in session_set for item in actions):
            raise BacktestInputError("corporate action outside session calendar")

    def _process_buy_order(
        self,
        order: Order,
        bar: Bar | None,
        session_index: int,
        cash: Decimal,
        positions: dict[str, _Position],
        fills: list[Fill],
        order_events: list[OrderEvent],
        cash_ledger: list[CashLedgerEntry],
        position_ledger: list[PositionLedgerEntry],
        sizing_equity: Decimal,
    ) -> Decimal:
        if not self.config.allow_pyramiding and order.security_id in positions and positions[order.security_id].quantity > 0:
            order_events.append(self._order_event(order, OrderStatus.REJECTED_EXISTING_POSITION, 0, "pyramiding disabled"))
            return cash
        if self.config.max_positions is not None and len(positions) >= self.config.max_positions:
            order_events.append(self._order_event(order, OrderStatus.REJECTED_MAX_POSITIONS, 0, "maximum holdings reached"))
            return cash
        unavailable = self._unavailable_status(order, bar)
        if unavailable is not None:
            order_events.append(unavailable)
            return cash
        assert bar is not None and bar.open is not None
        if order.limit_price is not None and bar.open > order.limit_price:
            order_events.append(self._order_event(order, OrderStatus.UNFILLED_GAP_LIMIT, 0, "opening price above precommitted cap"))
            return cash

        fill_price = self.cost_model.fill_price(Side.BUY, bar.open)
        requested_budget = order.cash_budget
        if order.target_weight is not None:
            requested_budget = sizing_equity * order.target_weight
        cash_limit = min(cash, requested_budget) if requested_budget is not None else cash
        if order.quantity is not None:
            desired = order.quantity
        else:
            assert requested_budget is not None
            desired = self._max_affordable_quantity(requested_budget, fill_price)
        quantity = desired
        if bar.max_buy_quantity is not None:
            quantity = min(quantity, bar.max_buy_quantity)
        quantity = min(quantity, self._max_affordable_quantity(cash_limit, fill_price))
        if quantity <= 0:
            status = OrderStatus.UNFILLED_LIQUIDITY if bar.max_buy_quantity == 0 else OrderStatus.REJECTED_INSUFFICIENT_CASH
            order_events.append(self._order_event(order, status, 0, "no executable whole share"))
            return cash

        gross = fill_price * quantity
        commission = self.cost_model.commission(gross)
        total = gross + commission
        if total > cash or total > cash_limit:
            raise AssertionError("affordability calculation exceeded cash")
        fill = Fill(
            fill_id=f"FILL-{len(fills):08d}",
            order_id=order.order_id,
            session=order.execute_date,
            security_id=order.security_id,
            side=Side.BUY,
            quantity=quantity,
            reference_price=bar.open,
            fill_price=fill_price,
            gross_notional=gross,
            commission=commission,
            transaction_tax=ZERO,
            rural_special_tax=ZERO,
            slippage_cost=(fill_price - bar.open) * quantity,
            cash_delta=-total,
            reason=order.reason,
        )
        fills.append(fill)
        cash = self._append_cash(cash_ledger, cash, order.execute_date, "BUY_NOTIONAL", order.security_id, -gross, fill.fill_id)
        cash = self._append_cash(cash_ledger, cash, order.execute_date, "BUY_COMMISSION", order.security_id, -commission, fill.fill_id)
        position = _Position(
            security_id=order.security_id,
            quantity=quantity,
            cost_basis=total,
            stop_price=order.stop_price,
            target_price=order.target_price,
            entry_date=order.execute_date,
            entry_session_index=session_index,
            cycle_entry_cost=total,
            max_holding_sessions=order.max_holding_sessions,
        )
        positions[order.security_id] = position
        position_ledger.append(
            PositionLedgerEntry(
                entry_id=f"POS-{len(position_ledger):08d}",
                session=order.execute_date,
                security_id=order.security_id,
                quantity_delta=quantity,
                quantity_after=quantity,
                cost_basis_after=total,
                category="BUY",
                reference_id=fill.fill_id,
            )
        )
        status = OrderStatus.FILLED if quantity == desired else OrderStatus.PARTIALLY_FILLED
        order_events.append(self._order_event(order, status, quantity, "executed at opening reference plus adverse slippage"))
        return cash

    def _process_sell_order(
        self,
        order: Order,
        bar: Bar | None,
        session_index: int,
        cash: Decimal,
        positions: dict[str, _Position],
        fills: list[Fill],
        order_events: list[OrderEvent],
        cash_ledger: list[CashLedgerEntry],
        position_ledger: list[PositionLedgerEntry],
        closed_trades: list[ClosedTrade],
        *,
        reference_price_override: Decimal | None = None,
    ) -> Decimal:
        position = positions.get(order.security_id)
        if position is None or position.quantity <= 0:
            order_events.append(self._order_event(order, OrderStatus.REJECTED_NO_POSITION, 0, "no long position"))
            return cash
        if order.quantity is not None and order.quantity > position.quantity:
            order_events.append(self._order_event(order, OrderStatus.REJECTED_EXCESS_SELL, 0, "requested sell exceeds long position"))
            return cash
        unavailable = self._unavailable_status(order, bar)
        if unavailable is not None:
            order_events.append(unavailable)
            return cash
        assert bar is not None and bar.open is not None
        reference_price = reference_price_override or bar.open
        desired = position.quantity if order.quantity is None else order.quantity
        quantity = desired
        if bar.max_sell_quantity is not None:
            quantity = min(quantity, bar.max_sell_quantity)
        if quantity <= 0:
            order_events.append(self._order_event(order, OrderStatus.UNFILLED_LIQUIDITY, 0, "sell liquidity cap is zero"))
            return cash

        fill_price = self.cost_model.fill_price(Side.SELL, reference_price)
        gross = fill_price * quantity
        commission = self.cost_model.commission(gross)
        transaction_tax, rural_tax = self.cost_model.sell_taxes(order.execute_date, gross)
        net_proceeds = gross - commission - transaction_tax - rural_tax
        old_quantity = position.quantity
        allocated_basis = position.cost_basis if quantity == old_quantity else position.cost_basis * Decimal(quantity) / Decimal(old_quantity)
        realized_pnl = net_proceeds - allocated_basis
        fill = Fill(
            fill_id=f"FILL-{len(fills):08d}",
            order_id=order.order_id,
            session=order.execute_date,
            security_id=order.security_id,
            side=Side.SELL,
            quantity=quantity,
            reference_price=reference_price,
            fill_price=fill_price,
            gross_notional=gross,
            commission=commission,
            transaction_tax=transaction_tax,
            rural_special_tax=rural_tax,
            slippage_cost=(reference_price - fill_price) * quantity,
            cash_delta=net_proceeds,
            reason=order.reason,
        )
        fills.append(fill)
        cash = self._append_cash(cash_ledger, cash, order.execute_date, "SELL_NOTIONAL", order.security_id, gross, fill.fill_id)
        cash = self._append_cash(cash_ledger, cash, order.execute_date, "SELL_COMMISSION", order.security_id, -commission, fill.fill_id)
        cash = self._append_cash(cash_ledger, cash, order.execute_date, "TRANSACTION_TAX", order.security_id, -transaction_tax, fill.fill_id)
        cash = self._append_cash(cash_ledger, cash, order.execute_date, "RURAL_SPECIAL_TAX", order.security_id, -rural_tax, fill.fill_id)
        position.quantity -= quantity
        position.cost_basis -= allocated_basis
        position.cycle_realized_pnl += realized_pnl
        position_ledger.append(
            PositionLedgerEntry(
                entry_id=f"POS-{len(position_ledger):08d}",
                session=order.execute_date,
                security_id=order.security_id,
                quantity_delta=-quantity,
                quantity_after=position.quantity,
                cost_basis_after=position.cost_basis,
                category="SELL",
                reference_id=fill.fill_id,
            )
        )
        if position.quantity == 0:
            net_return = position.cycle_realized_pnl / position.cycle_entry_cost if position.cycle_entry_cost else ZERO
            closed_trades.append(
                ClosedTrade(
                    security_id=order.security_id,
                    entry_date=position.entry_date,
                    exit_date=order.execute_date,
                    holding_sessions=session_index - position.entry_session_index + 1,
                    entry_cost=position.cycle_entry_cost,
                    net_pnl=position.cycle_realized_pnl,
                    net_return=net_return,
                    exit_reason=order.reason,
                )
            )
            del positions[order.security_id]
        status = OrderStatus.FILLED if quantity == desired else OrderStatus.PARTIALLY_FILLED
        order_events.append(self._order_event(order, status, quantity, "executed with sell costs and adverse slippage"))
        return cash

    def _apply_corporate_action(
        self,
        action: CorporateAction,
        session_index: int,
        cash: Decimal,
        positions: dict[str, _Position],
        cash_ledger: list[CashLedgerEntry],
        position_ledger: list[PositionLedgerEntry],
        closed_trades: list[ClosedTrade],
        audit_events: list[AuditEvent],
    ) -> Decimal:
        position = positions.get(action.security_id)
        if position is None:
            return cash
        if action.kind is CorporateActionType.UNRESOLVED or action.source_status != "READY":
            raise UnresolvedCorporateActionError(
                f"held position {action.security_id} reached unresolved action {action.action_id}"
            )
        assert action.share_multiplier is not None
        old_quantity = position.quantity
        exact_new_quantity = Decimal(old_quantity) * action.share_multiplier
        new_quantity = int(exact_new_quantity.to_integral_value(rounding=ROUND_FLOOR))
        fractional_quantity = exact_new_quantity - Decimal(new_quantity)
        if fractional_quantity and action.cash_in_lieu_price is None:
            raise UnresolvedCorporateActionError(
                f"action {action.action_id} creates a fractional share without cash-in-lieu price"
            )
        removed_basis = ZERO
        if fractional_quantity:
            removed_basis = position.cost_basis * fractional_quantity / exact_new_quantity
        retained_basis = position.cost_basis - removed_basis
        cash_amount = action.cash_per_old_share * old_quantity
        if fractional_quantity:
            assert action.cash_in_lieu_price is not None
            cash_amount += fractional_quantity * action.cash_in_lieu_price
        if cash_amount:
            cash = self._append_cash(
                cash_ledger,
                cash,
                action.effective_date,
                "CORPORATE_ACTION_CASH",
                action.security_id,
                cash_amount,
                action.action_id,
            )
            position.cycle_realized_pnl += cash_amount - removed_basis

        target_security = action.successor_security_id if action.kind is CorporateActionType.SUCCESSOR else action.security_id
        assert target_security is not None
        if target_security != action.security_id and target_security in positions:
            raise UnresolvedCorporateActionError("successor transformation would merge two live positions")
        position_ledger.append(
            PositionLedgerEntry(
                entry_id=f"POS-{len(position_ledger):08d}",
                session=action.effective_date,
                security_id=action.security_id,
                quantity_delta=-old_quantity,
                quantity_after=0 if target_security != action.security_id else new_quantity,
                cost_basis_after=ZERO if target_security != action.security_id else retained_basis,
                category="CORPORATE_ACTION_OLD",
                reference_id=action.action_id,
            )
        )
        if target_security != action.security_id:
            del positions[action.security_id]
            position.security_id = target_security
            position.quantity = new_quantity
            position.cost_basis = retained_basis
            positions[target_security] = position
            position_ledger.append(
                PositionLedgerEntry(
                    entry_id=f"POS-{len(position_ledger):08d}",
                    session=action.effective_date,
                    security_id=target_security,
                    quantity_delta=new_quantity,
                    quantity_after=new_quantity,
                    cost_basis_after=retained_basis,
                    category="CORPORATE_ACTION_SUCCESSOR",
                    reference_id=action.action_id,
                )
            )
        else:
            # Replace the old quantity with the adjusted quantity. The ledger's
            # single delta must reconcile from old to new.
            position_ledger[-1] = replace(position_ledger[-1], quantity_delta=new_quantity - old_quantity)
            position.quantity = new_quantity
            position.cost_basis = retained_basis

        audit_events.append(
            AuditEvent(
                session=action.effective_date,
                severity="INFO",
                code="CORPORATE_ACTION_APPLIED",
                security_id=target_security,
                reference_id=action.action_id,
                detail=f"old_qty={old_quantity};new_qty={new_quantity};cash={cash_amount}",
            )
        )
        if new_quantity == 0:
            net_return = position.cycle_realized_pnl / position.cycle_entry_cost if position.cycle_entry_cost else ZERO
            closed_trades.append(
                ClosedTrade(
                    security_id=target_security,
                    entry_date=position.entry_date,
                    exit_date=action.effective_date,
                    holding_sessions=session_index - position.entry_session_index + 1,
                    entry_cost=position.cycle_entry_cost,
                    net_pnl=position.cycle_realized_pnl,
                    net_return=net_return,
                    exit_reason="CORPORATE_ACTION_CASH_OUT",
                )
            )
            positions.pop(target_security, None)
        return cash

    def _barrier_trigger(self, position: _Position, bar: Bar) -> tuple[str, Decimal] | None:
        assert bar.open is not None and bar.high is not None and bar.low is not None
        stop = position.stop_price
        target = position.target_price
        if stop is not None and bar.open <= stop:
            return "STOP_GAP", bar.open
        if target is not None and bar.open >= target:
            return "TARGET", target
        stop_hit = stop is not None and bar.low <= stop
        target_hit = target is not None and bar.high >= target
        if stop_hit:
            return ("STOP_FIRST_SAME_BAR" if target_hit else "STOP"), stop  # frozen conservative ordering
        if target_hit:
            return "TARGET", target
        return None

    def _unavailable_status(self, order: Order, bar: Bar | None) -> OrderEvent | None:
        if bar is None:
            return self._order_event(order, OrderStatus.UNFILLED_NO_BAR, 0, "no execution bar")
        if not bar.tradable:
            return self._order_event(order, OrderStatus.UNFILLED_NOT_TRADABLE, 0, "security not tradable")
        return None

    def _order_event(self, order: Order, status: OrderStatus, filled: int, reason: str) -> OrderEvent:
        return OrderEvent(
            order_id=order.order_id,
            session=order.execute_date,
            security_id=order.security_id,
            side=order.side,
            status=status,
            requested_quantity=order.quantity,
            filled_quantity=filled,
            reason=reason,
        )

    def _max_affordable_quantity(self, cash_limit: Decimal, fill_price: Decimal) -> int:
        if cash_limit <= ZERO:
            return 0
        estimate = int((cash_limit / fill_price).to_integral_value(rounding=ROUND_FLOOR))
        while estimate > 0:
            gross = fill_price * estimate
            if gross + self.cost_model.commission(gross) <= cash_limit:
                return estimate
            estimate -= 1
        return 0

    @staticmethod
    def _append_cash(
        ledger: list[CashLedgerEntry],
        cash: Decimal,
        session: date,
        category: str,
        security_id: str,
        amount: Decimal,
        reference_id: str,
    ) -> Decimal:
        updated = cash + amount
        if updated < ZERO:
            raise AssertionError("cash cannot become negative")
        ledger.append(
            CashLedgerEntry(
                entry_id=f"CASH-{len(ledger):08d}",
                session=session,
                category=category,
                security_id=security_id,
                amount=amount,
                balance_after=updated,
                reference_id=reference_id,
            )
        )
        return updated

    @staticmethod
    def _reconcile(
        initial_cash: Decimal,
        final_cash: Decimal,
        cash_ledger: list[CashLedgerEntry],
        position_ledger: list[PositionLedgerEntry],
        final_positions: Mapping[str, int],
        fills: list[Fill],
        equity_curve: list[EquityPoint],
        snapshots: list[PositionSnapshot],
    ) -> ReconciliationReport:
        cash_sum = sum((item.amount for item in cash_ledger), ZERO)
        cash_running_ok = all(item.balance_after >= ZERO for item in cash_ledger)
        quantities: dict[str, int] = defaultdict(int)
        for item in position_ledger:
            quantities[item.security_id] += item.quantity_delta
        quantities = {key: value for key, value in quantities.items() if value != 0}
        fill_cash_ok = all(
            (
                fill.cash_delta == -(fill.gross_notional + fill.commission)
                if fill.side is Side.BUY
                else fill.cash_delta
                == fill.gross_notional - fill.commission - fill.transaction_tax - fill.rural_special_tax
            )
            for fill in fills
        )
        last_session = equity_curve[-1].session
        last_market_value = sum((item.market_value for item in snapshots if item.session == last_session), ZERO)
        checks = {
            "cash_sum": cash_sum == final_cash,
            "cash_nonnegative": cash_running_ok and final_cash >= ZERO,
            "positions_from_ledger": quantities == dict(final_positions),
            "positions_long_only": all(value >= 0 for value in final_positions.values()),
            "fill_cash_decomposition": fill_cash_ok,
            "final_equity_identity": equity_curve[-1].equity == final_cash + last_market_value,
            "initial_capital_recorded_once": bool(cash_ledger)
            and cash_ledger[0].category == "INITIAL_CAPITAL"
            and cash_ledger[0].amount == initial_cash,
        }
        detail = {
            "cash_sum": str(cash_sum),
            "final_cash": str(final_cash),
            "ledger_positions": json.dumps(quantities, sort_keys=True),
            "final_positions": json.dumps(dict(final_positions), sort_keys=True),
            "final_market_value": str(last_market_value),
        }
        return ReconciliationReport(passed=all(checks.values()), checks=checks, detail=detail)

    def _config_hash(self) -> str:
        payload = {
            "config": self.config.__dict__,
            "commission_rate": self.cost_model.commission_rate,
            "buy_slippage_rate": self.cost_model.buy_slippage_rate,
            "sell_slippage_rate": self.cost_model.sell_slippage_rate,
            "money_quantum": self.cost_model.money_quantum,
            "cost_bands": [item.__dict__ for item in self.cost_model.schedule.bands],
        }
        return self._stable_hash(payload)

    @classmethod
    def _input_hash(
        cls,
        sessions: tuple[date, ...],
        bars: tuple[Bar, ...],
        orders: tuple[Order, ...],
        actions: tuple[CorporateAction, ...],
    ) -> str:
        return cls._stable_hash(
            {
                "sessions": sessions,
                "bars": [item.__dict__ for item in sorted(bars, key=lambda item: (item.session, item.security_id))],
                "orders": [item.__dict__ for item in sorted(orders, key=lambda item: item.order_id)],
                "actions": [item.__dict__ for item in sorted(actions, key=lambda item: item.action_id)],
            }
        )

    @staticmethod
    def _stable_hash(value: object) -> str:
        def default(item: object) -> str:
            if isinstance(item, (date, Decimal)):
                return str(item)
            if hasattr(item, "value"):
                return str(getattr(item, "value"))
            raise TypeError(type(item).__name__)

        encoded = json.dumps(value, default=default, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
