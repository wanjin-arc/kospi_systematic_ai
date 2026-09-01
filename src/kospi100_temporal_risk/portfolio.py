from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pandas as pd

from kospi100_backtest.costs import CostSchedule, ExecutionCostModel
from kospi100_backtest.engine import BacktestEngine, EngineConfig
from kospi100_backtest.types import OrderStatus
from kospi100_ranking.config import Period
from kospi100_ranking.data import SelectionBundle
from kospi100_ranking.portfolio import _assert_successor_safety, build_context

from .config import MODEL_CONTRACT, TemporalRiskConfig
from .policy import generate_temporal_orders


@dataclass(frozen=True)
class TemporalPortfolioEvaluation:
    metrics: pd.DataFrame
    order_audit: dict[str, object]
    decision: dict[str, object]


def _engine(config: TemporalRiskConfig, multiplier: int) -> BacktestEngine:
    base = config.base
    cost = ExecutionCostModel(
        CostSchedule.from_csv(base.tax_schedule_path),
        commission_rate=base.commission_rate * multiplier,
        buy_slippage_rate=base.slippage_rate * multiplier,
        sell_slippage_rate=base.slippage_rate * multiplier,
    )
    return BacktestEngine(
        EngineConfig(initial_cash=base.initial_cash, allow_pyramiding=False, max_positions=10), cost
    )


def _benchmark_mdd(benchmark: dict[date, Decimal], first: date) -> float:
    values = pd.Series(
        [float(value) for session, value in sorted(benchmark.items()) if session >= first], dtype=float
    )
    if values.empty:
        raise ValueError("Benchmark MDD 평가값이 없습니다")
    return float((values / values.cummax() - 1.0).min())


def _run(predictions, context, unresolved, config: TemporalRiskConfig, multiplier: int):
    orders, order_audit = generate_temporal_orders(predictions, context.sessions, config)
    _assert_successor_safety(orders, context.sessions, unresolved)
    result = _engine(config, multiplier).run(
        context.sessions, context.bars, tuple(context.controls) + orders,
        corporate_actions=context.actions, benchmark_close=context.benchmark,
    )
    if not result.reconciliation.passed:
        raise AssertionError("Phase 5F portfolio 원장 조정 실패")
    unsafe = {
        OrderStatus.UNFILLED_NOT_TRADABLE, OrderStatus.UNFILLED_NO_BAR,
        OrderStatus.UNFILLED_LIQUIDITY, OrderStatus.PARTIALLY_FILLED,
    }
    failed_controls = [
        event for event in result.order_events
        if event.order_id.startswith(("P5:CA_EXIT:", "P5:REMOVAL_EXIT:")) and event.status in unsafe
    ]
    if failed_controls:
        raise RuntimeError(f"필수 강제청산 미체결: {failed_controls[0].order_id}")
    metrics = result.metrics
    total = Decimal(str(metrics["total_return"]))
    benchmark = Decimal(str(metrics["benchmark_total_return"]))
    evaluation_sessions = [
        point.session for point in result.equity_curve if point.session >= context.first_evaluation
    ]
    position_counts = Counter(snapshot.session for snapshot in result.position_snapshots)
    average_positions = (
        sum(position_counts.get(session, 0) for session in evaluation_sessions) / len(evaluation_sessions)
        if evaluation_sessions else 0.0
    )
    row = {
        "policy": "phase5f_temporal_mean_median_anomaly_veto",
        "model": MODEL_CONTRACT,
        "period": context.name,
        "cost_multiplier": multiplier,
        "total_return": total,
        "benchmark_total_return": benchmark,
        "net_excess_return": total - benchmark,
        "sharpe_zero_rf": metrics["sharpe_zero_rf"],
        "max_drawdown": metrics["max_drawdown"],
        "benchmark_max_drawdown": _benchmark_mdd(context.benchmark, context.first_evaluation),
        "turnover_on_average_equity": metrics["turnover_on_average_equity"],
        "average_cash_weight": metrics["average_cash_weight"],
        "average_positions": average_positions,
        "unfilled_orders": sum(1 for event in result.order_events if event.status.value.startswith("UNFILLED")),
        "fills": metrics["fills"],
        "all_explicit_costs": metrics["all_explicit_costs"],
        "entry_orders": order_audit["entry_orders"],
        "no_trade_signal_days": order_audit["no_trade_signal_days"],
        "anomaly_veto_signal_days": order_audit["anomaly_veto_signal_days"],
        "reconciliation": metrics["reconciliation"],
        "engine_input_hash": result.input_hash,
    }
    return row, order_audit


def evaluate_policy(
    predictions: pd.DataFrame,
    bundle: SelectionBundle,
    config: TemporalRiskConfig,
) -> TemporalPortfolioEvaluation:
    connected = Period("adaptive_diagnostic_2019_2021", date(2019, 1, 1), date(2021, 12, 31))
    rows: list[dict[str, object]] = []
    audits: dict[str, object] = {}
    context, unresolved = build_context(bundle, connected)
    for multiplier in config.base.stress_multipliers:
        row, audit = _run(predictions, context, unresolved, config, multiplier)
        rows.append(row)
        audits[f"connected_cost_{multiplier}x"] = audit
    for fold in config.base.folds:
        context, unresolved = build_context(bundle, fold.validation)
        selected = predictions.loc[predictions["fold"].eq(fold.name)]
        row, audit = _run(selected, context, unresolved, config, 1)
        rows.append(row)
        audits[f"{fold.name}_cost_1x"] = audit
    metrics = pd.DataFrame(rows)
    base = metrics.loc[
        metrics["period"].eq(connected.name) & metrics["cost_multiplier"].eq(1)
    ].iloc[0]
    stress = metrics.loc[
        metrics["period"].eq(connected.name) & metrics["cost_multiplier"].eq(2)
    ].iloc[0]
    annual = metrics.loc[metrics["period"].str.startswith("F")]
    base_gate = float(base["net_excess_return"]) > 0.0
    stress_gate = float(stress["net_excess_return"]) >= 0.0
    activity_gate = int(base["entry_orders"]) >= config.minimum_entry_orders
    mdd_gate = float(base["max_drawdown"]) >= (
        float(base["benchmark_max_drawdown"]) - config.maximum_mdd_worsening
    )
    decision = {
        "experiment_id": config.experiment_id,
        "status": "ADAPTIVE_DIAGNOSTIC_COMPLETED",
        "connected_net_excess_return": base["net_excess_return"],
        "cost_2x_net_excess_return": stress["net_excess_return"],
        "entry_orders": int(base["entry_orders"]),
        "nonnegative_annual_excess_folds": int((annual["net_excess_return"].astype(float) >= 0.0).sum()),
        "annual_folds": len(annual),
        "diagnostic_gates": {
            "base_cost_positive_net_excess": base_gate,
            "cost_2x_nonnegative_net_excess": stress_gate,
            "minimum_100_entry_orders": activity_gate,
            "mdd_not_worse_than_benchmark_by_over_5pp": mdd_gate,
        },
        "all_diagnostic_gates_passed": base_gate and stress_gate and activity_gate and mdd_gate,
        "annual_positive_ratio_is_hard_gate": False,
        "average_cash_is_hard_gate": False,
        "minimum_holdings_is_hard_gate": False,
        "promotion_allowed": False,
        "trading_candidate": False,
        "development_test_candidate": False,
        "development_test_runs": 0,
        "reason": "2019~2021은 이미 소비된 adaptive diagnostic이므로 성과와 무관하게 승격하지 않습니다.",
    }
    return TemporalPortfolioEvaluation(metrics, audits, decision)
