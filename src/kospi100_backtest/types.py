from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Mapping


ZERO = Decimal("0")


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED_REMAINDER_CANCELLED"
    UNFILLED_GAP_LIMIT = "UNFILLED_GAP_LIMIT"
    UNFILLED_NOT_TRADABLE = "UNFILLED_NOT_TRADABLE"
    UNFILLED_NO_BAR = "UNFILLED_NO_BAR"
    UNFILLED_LIQUIDITY = "UNFILLED_LIQUIDITY"
    REJECTED_INSUFFICIENT_CASH = "REJECTED_INSUFFICIENT_CASH"
    REJECTED_NO_POSITION = "REJECTED_NO_POSITION"
    REJECTED_EXCESS_SELL = "REJECTED_EXCESS_SELL"
    REJECTED_EXISTING_POSITION = "REJECTED_EXISTING_POSITION"
    REJECTED_MAX_POSITIONS = "REJECTED_MAX_POSITIONS"


class CorporateActionType(str, Enum):
    SPLIT = "SPLIT"
    BONUS_ISSUE = "BONUS_ISSUE"
    SUCCESSOR = "SUCCESSOR"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class Bar:
    session: date
    security_id: str
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    tradable: bool = True
    max_buy_quantity: int | None = None
    max_sell_quantity: int | None = None

    def __post_init__(self) -> None:
        if not self.security_id:
            raise ValueError("bar security_id is required")
        for value in (self.max_buy_quantity, self.max_sell_quantity):
            if value is not None and value < 0:
                raise ValueError("liquidity caps must be non-negative")
        prices = (self.open, self.high, self.low, self.close)
        if self.tradable:
            if any(value is None or value <= ZERO for value in prices):
                raise ValueError("tradable bars require positive OHLC")
            assert self.open is not None and self.high is not None and self.low is not None and self.close is not None
            if self.low > self.high or not (self.low <= self.open <= self.high) or not (self.low <= self.close <= self.high):
                raise ValueError("invalid OHLC range")


@dataclass(frozen=True)
class Order:
    order_id: str
    signal_date: date
    execute_date: date
    security_id: str
    side: Side
    quantity: int | None = None
    cash_budget: Decimal | None = None
    target_weight: Decimal | None = None
    priority: int = 0
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    target_price: Decimal | None = None
    max_holding_sessions: int | None = None
    reason: str = "SIGNAL"

    def __post_init__(self) -> None:
        if not self.order_id or not self.security_id:
            raise ValueError("order_id and security_id are required")
        if self.signal_date >= self.execute_date:
            raise ValueError("orders require signal_date < execute_date")
        if self.quantity is not None and self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.cash_budget is not None and self.cash_budget <= ZERO:
            raise ValueError("cash_budget must be positive")
        if self.target_weight is not None and not (ZERO < self.target_weight <= Decimal("1")):
            raise ValueError("target_weight must be in (0, 1]")
        if self.max_holding_sessions is not None and self.max_holding_sessions <= 0:
            raise ValueError("max_holding_sessions must be positive")
        for value in (self.limit_price, self.stop_price, self.target_price):
            if value is not None and value <= ZERO:
                raise ValueError("order prices must be positive")
        if self.side is Side.BUY:
            sizing_fields = (self.quantity, self.cash_budget, self.target_weight)
            if sum(value is not None for value in sizing_fields) != 1:
                raise ValueError("buy orders require exactly one sizing method")
            if self.stop_price is not None and self.target_price is not None and self.stop_price >= self.target_price:
                raise ValueError("stop_price must be below target_price")
        elif any(
            value is not None
            for value in (self.cash_budget, self.target_weight, self.stop_price, self.target_price, self.max_holding_sessions)
        ):
            raise ValueError("sell orders cannot carry entry sizing, barriers, or holding periods")


@dataclass(frozen=True)
class CorporateAction:
    action_id: str
    effective_date: date
    security_id: str
    kind: CorporateActionType
    share_multiplier: Decimal | None = None
    successor_security_id: str | None = None
    cash_in_lieu_price: Decimal | None = None
    cash_per_old_share: Decimal = ZERO
    source_status: str = "READY"

    def __post_init__(self) -> None:
        if not self.action_id or not self.security_id:
            raise ValueError("action_id and security_id are required")
        if self.kind in {CorporateActionType.SPLIT, CorporateActionType.BONUS_ISSUE, CorporateActionType.SUCCESSOR}:
            if self.share_multiplier is None or self.share_multiplier <= ZERO:
                raise ValueError("mechanical actions require a positive share_multiplier")
        if self.kind is CorporateActionType.SUCCESSOR and not self.successor_security_id:
            raise ValueError("successor actions require successor_security_id")
        if self.cash_in_lieu_price is not None and self.cash_in_lieu_price <= ZERO:
            raise ValueError("cash_in_lieu_price must be positive")
        if self.cash_per_old_share < ZERO:
            raise ValueError("cash_per_old_share cannot be negative")


@dataclass(frozen=True)
class Fill:
    fill_id: str
    order_id: str
    session: date
    security_id: str
    side: Side
    quantity: int
    reference_price: Decimal
    fill_price: Decimal
    gross_notional: Decimal
    commission: Decimal
    transaction_tax: Decimal
    rural_special_tax: Decimal
    slippage_cost: Decimal
    cash_delta: Decimal
    reason: str


@dataclass(frozen=True)
class OrderEvent:
    order_id: str
    session: date
    security_id: str
    side: Side
    status: OrderStatus
    requested_quantity: int | None
    filled_quantity: int
    reason: str


@dataclass(frozen=True)
class CashLedgerEntry:
    entry_id: str
    session: date
    category: str
    security_id: str
    amount: Decimal
    balance_after: Decimal
    reference_id: str


@dataclass(frozen=True)
class PositionLedgerEntry:
    entry_id: str
    session: date
    security_id: str
    quantity_delta: int
    quantity_after: int
    cost_basis_after: Decimal
    category: str
    reference_id: str


@dataclass(frozen=True)
class PositionSnapshot:
    session: date
    security_id: str
    quantity: int
    cost_basis: Decimal
    mark_price: Decimal
    market_value: Decimal
    mark_status: str


@dataclass(frozen=True)
class EquityPoint:
    session: date
    cash: Decimal
    positions_value: Decimal
    equity: Decimal
    daily_return: Decimal
    cash_weight: Decimal
    stale_position_count: int
    benchmark_close: Decimal | None = None


@dataclass(frozen=True)
class ClosedTrade:
    security_id: str
    entry_date: date
    exit_date: date
    holding_sessions: int
    entry_cost: Decimal
    net_pnl: Decimal
    net_return: Decimal
    exit_reason: str


@dataclass(frozen=True)
class AuditEvent:
    session: date
    severity: str
    code: str
    security_id: str
    reference_id: str
    detail: str


@dataclass(frozen=True)
class ReconciliationReport:
    passed: bool
    checks: Mapping[str, bool]
    detail: Mapping[str, str]


@dataclass(frozen=True)
class RunResult:
    initial_cash: Decimal
    final_cash: Decimal
    fills: tuple[Fill, ...]
    order_events: tuple[OrderEvent, ...]
    cash_ledger: tuple[CashLedgerEntry, ...]
    position_ledger: tuple[PositionLedgerEntry, ...]
    position_snapshots: tuple[PositionSnapshot, ...]
    equity_curve: tuple[EquityPoint, ...]
    closed_trades: tuple[ClosedTrade, ...]
    audit_events: tuple[AuditEvent, ...]
    final_positions: Mapping[str, int]
    final_cost_basis: Mapping[str, Decimal]
    reconciliation: ReconciliationReport
    input_hash: str
    config_hash: str
    metrics: Mapping[str, Decimal | int | str | None] = field(default_factory=dict)
