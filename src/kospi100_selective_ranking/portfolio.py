from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

import pandas as pd

from kospi100_backtest.costs import CostSchedule, ExecutionCostModel
from kospi100_backtest.engine import BacktestEngine, EngineConfig
from kospi100_backtest.types import OrderStatus
from kospi100_ranking.config import Period
from kospi100_ranking.data import SelectionBundle
from kospi100_ranking.portfolio import _assert_successor_safety, build_context, run_portfolio

from .config import SelectiveConfig
from .policy import generate_selective_orders


@dataclass(frozen=True)
class SelectiveEvaluation:
    metrics: pd.DataFrame
    regime_exposure: pd.DataFrame
    order_audit: dict[str, object]
    decision: dict[str, object]


def _engine(config: SelectiveConfig, multiplier: int) -> BacktestEngine:
    base = config.base
    cost = ExecutionCostModel(
        CostSchedule.from_csv(base.tax_schedule_path),
        commission_rate=base.commission_rate * multiplier,
        buy_slippage_rate=base.slippage_rate * multiplier,
        sell_slippage_rate=base.slippage_rate * multiplier,
    )
    return BacktestEngine(
        EngineConfig(initial_cash=base.initial_cash, allow_pyramiding=False, max_positions=10),
        cost,
    )


def _exposure_frame(result, predictions: pd.DataFrame, sessions: tuple[date, ...], period: str) -> pd.DataFrame:
    regime_by_signal = {
        row.date.date(): str(row.market_regime)
        for row in predictions[["date", "market_regime"]].drop_duplicates().itertuples(index=False)
    }
    next_session = {sessions[index]: sessions[index + 1] for index in range(len(sessions) - 1)}
    regime_by_execution = {
        next_session[signal]: regime for signal, regime in regime_by_signal.items() if signal in next_session
    }
    position_counts = Counter(snapshot.session for snapshot in result.position_snapshots)
    rows = []
    for point in result.equity_curve:
        regime = regime_by_execution.get(point.session)
        if regime is None:
            continue
        rows.append(
            {
                "period": period,
                "date": point.session.isoformat(),
                "market_regime": regime,
                "positions": position_counts.get(point.session, 0),
                "cash_weight": point.cash_weight,
            }
        )
    daily = pd.DataFrame(rows)
    if daily.empty:
        return pd.DataFrame(columns=["period", "market_regime", "days", "average_positions", "average_cash_weight"])
    return (
        daily.groupby("market_regime", sort=True)
        .agg(days=("date", "count"), average_positions=("positions", "mean"), average_cash_weight=("cash_weight", "mean"))
        .reset_index()
        .assign(period=period)[["period", "market_regime", "days", "average_positions", "average_cash_weight"]]
    )


def _run_selective(predictions, context, unresolved, config: SelectiveConfig, multiplier: int):
    orders, order_audit = generate_selective_orders(predictions, context.sessions, config)
    _assert_successor_safety(orders, context.sessions, unresolved)
    result = _engine(config, multiplier).run(
        context.sessions,
        context.bars,
        tuple(context.controls) + orders,
        corporate_actions=context.actions,
        benchmark_close=context.benchmark,
    )
    if not result.reconciliation.passed:
        raise AssertionError("Phase 5D portfolio 원장 조정 실패")
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
    evaluation_sessions = [point.session for point in result.equity_curve if point.session >= context.first_evaluation]
    counts = Counter(snapshot.session for snapshot in result.position_snapshots)
    average_positions = (
        sum(counts.get(session, 0) for session in evaluation_sessions) / len(evaluation_sessions)
        if evaluation_sessions
        else 0.0
    )
    row = {
        "policy": "phase5d_selective",
        "candidate": config.policy_candidate,
        "period": context.name,
        "cost_multiplier": multiplier,
        "total_return": total,
        "benchmark_total_return": benchmark,
        "net_excess_return": total - benchmark,
        "sharpe_zero_rf": metrics["sharpe_zero_rf"],
        "max_drawdown": metrics["max_drawdown"],
        "turnover_on_average_equity": metrics["turnover_on_average_equity"],
        "average_cash_weight": metrics["average_cash_weight"],
        "average_positions": average_positions,
        "unfilled_orders": sum(1 for event in result.order_events if event.status.value.startswith("UNFILLED")),
        "fills": metrics["fills"],
        "all_explicit_costs": metrics["all_explicit_costs"],
        "reconciliation": metrics["reconciliation"],
        "engine_input_hash": result.input_hash,
    }
    exposure = _exposure_frame(result, predictions, context.sessions, context.name)
    return row, order_audit, exposure


def evaluate_policy(
    raw_predictions: pd.DataFrame,
    selective_predictions: pd.DataFrame,
    bundle: SelectionBundle,
    config: SelectiveConfig,
) -> SelectiveEvaluation:
    connected_period = Period("reused_validation_2019_2021", date(2019, 1, 1), date(2021, 12, 31))
    rows: list[dict[str, object]] = []
    exposure_rows: list[pd.DataFrame] = []
    audits: dict[str, object] = {}
    reference_config = replace(config.base, holding_sessions=10)
    context, unresolved = build_context(bundle, connected_period)
    reference = run_portfolio(
        config.model_candidate, raw_predictions, context, unresolved, reference_config, 1
    )
    reference["policy"] = "phase5b_top10_hold10_reference"
    reference["average_positions"] = None
    rows.append(reference)
    for multiplier in config.base.stress_multipliers:
        row, audit, exposure = _run_selective(
            selective_predictions, context, unresolved, config, multiplier
        )
        rows.append(row)
        audits[f"connected_cost_{multiplier}x"] = audit
        if multiplier == 1:
            exposure_rows.append(exposure)
    for fold in config.base.folds:
        context, unresolved = build_context(bundle, fold.validation)
        raw_fold = raw_predictions.loc[raw_predictions["fold"].eq(fold.name)]
        reference = run_portfolio(
            config.model_candidate, raw_fold, context, unresolved, reference_config, 1
        )
        reference["policy"] = "phase5b_top10_hold10_reference"
        reference["average_positions"] = None
        rows.append(reference)
        selective_fold = selective_predictions.loc[selective_predictions["fold"].eq(fold.name)]
        row, audit, exposure = _run_selective(selective_fold, context, unresolved, config, 1)
        rows.append(row)
        audits[f"{fold.name}_cost_1x"] = audit
        exposure_rows.append(exposure)
    metrics = pd.DataFrame(rows)
    connected = metrics.loc[
        metrics["policy"].eq("phase5d_selective")
        & metrics["period"].eq(connected_period.name)
        & metrics["cost_multiplier"].eq(1)
    ].iloc[0]
    annual = metrics.loc[
        metrics["policy"].eq("phase5d_selective")
        & metrics["period"].str.startswith("F")
        & metrics["cost_multiplier"].eq(1)
    ]
    decision = {
        "experiment_id": config.experiment_id,
        "status": "REUSED_VALIDATION_DIAGNOSTIC_COMPLETED",
        "connected_net_excess_return": connected["net_excess_return"],
        "connected_outperformed_index": float(connected["net_excess_return"]) > 0.0,
        "nonnegative_annual_excess_folds": int((annual["net_excess_return"].astype(float) >= 0.0).sum()),
        "annual_folds": len(annual),
        "average_cash_is_hard_gate": False,
        "minimum_holdings_is_hard_gate": False,
        "promotion_allowed": False,
        "trading_candidate": False,
        "development_test_candidate": False,
        "development_test_runs": 0,
        "reason": "2019~2021은 이미 소비된 재사용 진단 구간이므로 성과와 무관하게 승격하지 않습니다.",
    }
    exposure = pd.concat(exposure_rows, ignore_index=True) if exposure_rows else pd.DataFrame()
    return SelectiveEvaluation(metrics, exposure, audits, decision)
