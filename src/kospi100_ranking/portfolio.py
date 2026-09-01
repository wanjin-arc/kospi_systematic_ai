from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pandas as pd

from kospi100_backtest.costs import CostSchedule, ExecutionCostModel
from kospi100_backtest.engine import BacktestEngine, EngineConfig
from kospi100_backtest.types import Bar, CorporateAction, CorporateActionType, Order, OrderStatus, Side
from kospi100_baseline.features import MECHANICAL

from .config import Period, RankingConfig
from .data import SelectionBundle


@dataclass(frozen=True)
class PortfolioEvaluation:
    metrics: pd.DataFrame
    selected_candidate: str


@dataclass(frozen=True)
class Context:
    name: str
    sessions: tuple[date, ...]
    first_evaluation: date
    bars: tuple[Bar, ...]
    benchmark: dict[date, Decimal]
    controls: tuple[Order, ...]
    actions: tuple[CorporateAction, ...]


def _decimal(value: object) -> Decimal | None:
    if pd.isna(value):
        return None
    return Decimal(str(value))


def _sessions(index: pd.DataFrame, period: Period) -> tuple[tuple[date, ...], date]:
    ordered = index.sort_values("date", kind="mergesort")
    evaluation = ordered.loc[
        ordered["date"].between(pd.Timestamp(period.start), pd.Timestamp(period.end)), "date"
    ]
    if evaluation.empty:
        raise ValueError(f"평가 세션 없음: {period.name}")
    seed = ordered.loc[ordered["date"] < evaluation.iloc[0], "date"]
    if seed.empty:
        raise ValueError(f"직전 signal seed 세션 없음: {period.name}")
    selected = ordered.loc[ordered["date"].between(seed.iloc[-1], evaluation.iloc[-1]), "date"]
    return tuple(value.date() for value in selected), evaluation.iloc[0].date()


def _bars(full: pd.DataFrame, sessions: tuple[date, ...]) -> list[Bar]:
    start, end = pd.Timestamp(sessions[0]), pd.Timestamp(sessions[-1])
    rows = full.loc[full["date"].between(start, end)].sort_values(["date", "security_id"], kind="mergesort")
    result: list[Bar] = []
    for row in rows.itertuples(index=False):
        tradable = bool(row.tradable)
        prices = [_decimal(getattr(row, column)) for column in ("open", "high", "low", "close")]
        if tradable and any(value is None for value in prices):
            raise ValueError(f"tradable OHLC 누락: {row.date} {row.security_id}")
        result.append(Bar(row.date.date(), row.security_id, *prices, tradable=tradable))
    return result


def _previous_session(sessions: tuple[date, ...], target: date) -> date | None:
    previous = [session for session in sessions if session < target]
    return previous[-1] if previous else None


def _controls(
    bundle: SelectionBundle,
    sessions: tuple[date, ...],
    bars: list[Bar],
) -> tuple[tuple[Order, ...], tuple[CorporateAction, ...], tuple[tuple[str, date], ...]]:
    session_set = set(sessions)
    bar_map = {(bar.session, bar.security_id): bar for bar in bars}
    orders: list[Order] = []
    actions: list[CorporateAction] = []
    unresolved_successors: list[tuple[str, date]] = []
    mechanical = bundle.corporate_actions.loc[bundle.corporate_actions["feature_handling"].eq(MECHANICAL)]
    for row in mechanical.sort_values(["feature_boundary_date", "canonical_event_id"]).itertuples(index=False):
        boundary = row.feature_boundary_date.date()
        if boundary not in session_set:
            continue
        bar = bar_map.get((boundary, row.security_id))
        cash_price = bar.open if bar is not None and bar.open is not None and bar.open > 0 else None
        actions.append(
            CorporateAction(
                action_id=f"P5:MECH:{row.canonical_event_id}",
                effective_date=boundary,
                security_id=row.security_id,
                kind=CorporateActionType.BONUS_ISSUE if row.event_type == "BONUS_ISSUE" else CorporateActionType.SPLIT,
                share_multiplier=Decimal(str(row.share_multiplier)),
                cash_in_lieu_price=cash_price,
                source_status="READY",
            )
        )
    resets = bundle.corporate_actions.loc[
        bundle.corporate_actions["feature_handling"].astype(str).str.startswith("RESET_")
    ]
    for row in resets.sort_values(["feature_boundary_date", "canonical_event_id"]).itertuples(index=False):
        boundary = row.feature_boundary_date.date()
        if boundary not in session_set or pd.isna(row.first_filing_date) or row.first_filing_date.date() >= boundary:
            continue
        signal = _previous_session(sessions, boundary)
        if signal is not None:
            orders.append(
                Order(
                    order_id=f"P5:CA_EXIT:{row.canonical_event_id}",
                    signal_date=signal,
                    execute_date=boundary,
                    security_id=row.security_id,
                    side=Side.SELL,
                    priority=-30_000,
                    reason="CA_DATA_SAFETY_EXIT",
                )
            )
    for row in bundle.removal_orders.sort_values(["execution_date", "order_id"]).itertuples(index=False):
        execution = row.execution_date.date()
        signal = row.signal_date.date()
        if execution not in session_set or signal not in session_set:
            continue
        if row.resolution_type == "SUCCESSOR_TRANSITION_REQUIRES_RESOLVED_POSITION":
            ticker = str(row.membership_spell_id).split(":", 1)[0]
            unresolved_successors.append((f"KRX_COMMON:{ticker}", execution))
            continue
        security = str(row.execution_security_id)
        actual = bar_map.get((execution, security))
        if actual is None or actual.open is None:
            raise ValueError(f"직접 구성종목 제외 실행 bar 누락: {row.membership_spell_id}")
        orders.append(
            Order(
                order_id=str(row.order_id).replace("P3:", "P5:", 1),
                signal_date=signal,
                execute_date=execution,
                security_id=security,
                side=Side.SELL,
                priority=-40_000,
                reason="UNIVERSE_REMOVAL_EXIT",
            )
        )
    return tuple(orders), tuple(actions), tuple(unresolved_successors)


def build_context(bundle: SelectionBundle, period: Period) -> tuple[Context, tuple[tuple[str, date], ...]]:
    sessions, first = _sessions(bundle.index, period)
    bars = _bars(bundle.full_history, sessions)
    controls, actions, unresolved = _controls(bundle, sessions, bars)
    benchmark_rows = bundle.index.loc[bundle.index["date"].dt.date.isin(sessions), ["date", "close"]]
    benchmark = {row.date.date(): Decimal(str(row.close)) for row in benchmark_rows.itertuples(index=False)}
    return Context(period.name, sessions, first, tuple(bars), benchmark, controls, actions), unresolved


def generate_orders(predictions: pd.DataFrame, sessions: tuple[date, ...], config: RankingConfig) -> tuple[Order, ...]:
    next_session = {sessions[index]: sessions[index + 1] for index in range(len(sessions) - 1)}
    work = predictions.copy()
    work["signal_date"] = work["date"].dt.date
    work = work.loc[work["signal_date"].isin(next_session)]
    orders: list[Order] = []
    for signal_date, group in work.groupby("signal_date", sort=True):
        ranked = group.sort_values(["score", "security_id"], ascending=[False, True], kind="mergesort")
        for rank, row in enumerate(ranked.head(config.maximum_holdings).itertuples(index=False), start=1):
            orders.append(
                Order(
                    order_id=f"P5:{row.candidate}:{signal_date.isoformat()}:R{rank:02d}:{row.security_id}",
                    signal_date=signal_date,
                    execute_date=next_session[signal_date],
                    security_id=row.security_id,
                    side=Side.BUY,
                    target_weight=config.target_weight,
                    priority=rank,
                    limit_price=Decimal(str(row.close)) * (Decimal("1") + config.entry_gap_cap),
                    max_holding_sessions=config.holding_sessions,
                    reason="RANKING_ENTRY",
                )
            )
    return tuple(orders)


def _assert_successor_safety(
    signal_orders: tuple[Order, ...],
    sessions: tuple[date, ...],
    unresolved: tuple[tuple[str, date], ...],
) -> None:
    positions = {session: index for index, session in enumerate(sessions)}
    for security, execution in unresolved:
        execution_index = positions[execution]
        for order in signal_orders:
            if order.security_id != security:
                continue
            entry_index = positions[order.execute_date]
            if entry_index <= execution_index < entry_index + int(order.max_holding_sessions or 0):
                raise RuntimeError(
                    f"successor 강제청산 조건이 안전 파티션에서 완전하지 않습니다: {security} {execution}"
                )


def _engine(config: RankingConfig, multiplier: int) -> BacktestEngine:
    cost = ExecutionCostModel(
        CostSchedule.from_csv(config.tax_schedule_path),
        commission_rate=config.commission_rate * multiplier,
        buy_slippage_rate=config.slippage_rate * multiplier,
        sell_slippage_rate=config.slippage_rate * multiplier,
    )
    return BacktestEngine(
        EngineConfig(
            initial_cash=config.initial_cash,
            allow_pyramiding=False,
            max_positions=config.maximum_holdings,
        ),
        cost,
    )


def run_portfolio(
    candidate: str,
    predictions: pd.DataFrame,
    context: Context,
    unresolved: tuple[tuple[str, date], ...],
    config: RankingConfig,
    multiplier: int,
) -> dict[str, object]:
    signal_orders = generate_orders(predictions, context.sessions, config)
    _assert_successor_safety(signal_orders, context.sessions, unresolved)
    result = _engine(config, multiplier).run(
        context.sessions,
        context.bars,
        tuple(context.controls) + signal_orders,
        corporate_actions=context.actions,
        benchmark_close=context.benchmark,
    )
    if not result.reconciliation.passed:
        raise AssertionError("Phase 5 portfolio 원장 조정 실패")
    unsafe = {
        OrderStatus.UNFILLED_NOT_TRADABLE,
        OrderStatus.UNFILLED_NO_BAR,
        OrderStatus.UNFILLED_LIQUIDITY,
        OrderStatus.PARTIALLY_FILLED,
    }
    failed_controls = [
        event
        for event in result.order_events
        if event.order_id.startswith(("P5:CA_EXIT:", "P5:REMOVAL_EXIT:")) and event.status in unsafe
    ]
    if failed_controls:
        raise RuntimeError(f"필수 강제청산 미체결: {failed_controls[0].order_id}")
    metrics = result.metrics
    total = Decimal(str(metrics["total_return"]))
    benchmark = Decimal(str(metrics["benchmark_total_return"]))
    unfilled = sum(1 for event in result.order_events if event.status.value.startswith("UNFILLED"))
    return {
        "candidate": candidate,
        "period": context.name,
        "cost_multiplier": multiplier,
        "total_return": total,
        "benchmark_total_return": benchmark,
        "net_excess_return": total - benchmark,
        "sharpe_zero_rf": metrics["sharpe_zero_rf"],
        "max_drawdown": metrics["max_drawdown"],
        "turnover_on_average_equity": metrics["turnover_on_average_equity"],
        "average_cash_weight": metrics["average_cash_weight"],
        "unfilled_orders": unfilled,
        "fills": metrics["fills"],
        "all_explicit_costs": metrics["all_explicit_costs"],
        "reconciliation": metrics["reconciliation"],
        "engine_input_hash": result.input_hash,
    }


def _score(row: pd.Series, order: tuple[str, ...]) -> tuple[float, float, float, float, int]:
    sharpe = float(row["sharpe_zero_rf"]) if pd.notna(row["sharpe_zero_rf"]) else float("-inf")
    return (
        sharpe,
        float(row["net_excess_return"]),
        float(row["max_drawdown"]),
        -float(row["turnover_on_average_equity"]),
        -order.index(str(row["candidate"])),
    )


def evaluate_portfolios(
    predictions: pd.DataFrame,
    bundle: SelectionBundle,
    config: RankingConfig,
) -> PortfolioEvaluation:
    connected_period = Period("validation_2019_2021", date(2019, 1, 1), date(2021, 12, 31))
    connected, unresolved = build_context(bundle, connected_period)
    rows: list[dict[str, object]] = []
    for candidate in config.candidate_order:
        candidate_predictions = predictions.loc[predictions["candidate"].eq(candidate)]
        for multiplier in config.stress_multipliers:
            rows.append(run_portfolio(candidate, candidate_predictions, connected, unresolved, config, multiplier))
    connected_base = pd.DataFrame(rows).loc[lambda frame: frame["cost_multiplier"].eq(1)]
    selected_row = max((row for _, row in connected_base.iterrows()), key=lambda row: _score(row, config.candidate_order))
    selected = str(selected_row["candidate"])
    for fold in config.folds:
        context, fold_unresolved = build_context(bundle, fold.validation)
        fold_predictions = predictions.loc[
            predictions["candidate"].eq(selected) & predictions["fold"].eq(fold.name)
        ]
        for multiplier in (1, 2):
            rows.append(run_portfolio(selected, fold_predictions, context, fold_unresolved, config, multiplier))
    return PortfolioEvaluation(pd.DataFrame(rows), selected)
