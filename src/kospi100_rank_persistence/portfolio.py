from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pandas as pd

from kospi100_backtest.costs import CostSchedule, ExecutionCostModel
from kospi100_backtest.engine import BacktestEngine, EngineConfig
from kospi100_backtest.types import OrderStatus
from kospi100_ranking.config import Period
from kospi100_ranking.data import SelectionBundle
from kospi100_ranking.portfolio import _assert_successor_safety, build_context, run_portfolio

from .config import Phase5CConfig
from .policy import generate_persistent_orders


@dataclass(frozen=True)
class PolicyEvaluation:
    metrics: pd.DataFrame
    order_audit: dict[str, object]
    decision: dict[str, object]


def _engine(config: Phase5CConfig, multiplier: int) -> BacktestEngine:
    base = config.base
    cost = ExecutionCostModel(
        CostSchedule.from_csv(base.tax_schedule_path),
        commission_rate=base.commission_rate * multiplier,
        buy_slippage_rate=base.slippage_rate * multiplier,
        sell_slippage_rate=base.slippage_rate * multiplier,
    )
    return BacktestEngine(
        EngineConfig(
            initial_cash=base.initial_cash,
            allow_pyramiding=False,
            max_positions=base.maximum_holdings,
        ),
        cost,
    )


def _run_persistent(
    predictions: pd.DataFrame,
    context,
    unresolved: tuple[tuple[str, date], ...],
    config: Phase5CConfig,
    multiplier: int,
) -> tuple[dict[str, object], dict[str, int]]:
    signal_orders, order_audit = generate_persistent_orders(predictions, context.sessions, config)
    _assert_successor_safety(signal_orders, context.sessions, unresolved)
    result = _engine(config, multiplier).run(
        context.sessions,
        context.bars,
        tuple(context.controls) + signal_orders,
        corporate_actions=context.actions,
        benchmark_close=context.benchmark,
    )
    if not result.reconciliation.passed:
        raise AssertionError("Phase 5C portfolio 원장 조정 실패")
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
    row = {
        "policy": "phase5c_persistent",
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
        "unfilled_orders": sum(1 for event in result.order_events if event.status.value.startswith("UNFILLED")),
        "fills": metrics["fills"],
        "all_explicit_costs": metrics["all_explicit_costs"],
        "reconciliation": metrics["reconciliation"],
        "engine_input_hash": result.input_hash,
    }
    return row, order_audit


def _ratio_reduction(new: float, old: float) -> float:
    return 0.0 if old == 0.0 else 1.0 - new / old


def evaluate_policy(
    raw_predictions: pd.DataFrame,
    persistent_predictions: pd.DataFrame,
    bundle: SelectionBundle,
    config: Phase5CConfig,
) -> PolicyEvaluation:
    connected_period = Period("internal_validation_2015_2018", date(2015, 1, 1), date(2018, 12, 31))
    rows: list[dict[str, object]] = []
    audits: dict[str, object] = {}
    context, unresolved = build_context(bundle, connected_period)
    reference = run_portfolio(
        config.inherited_candidate,
        raw_predictions,
        context,
        unresolved,
        config.base,
        1,
    )
    reference["policy"] = "phase5b_reference"
    rows.append(reference)
    for multiplier in config.base.stress_multipliers:
        row, audit = _run_persistent(persistent_predictions, context, unresolved, config, multiplier)
        rows.append(row)
        audits[f"connected_cost_{multiplier}x"] = audit
    for fold in config.base.folds:
        context, unresolved = build_context(bundle, fold.validation)
        raw_fold = raw_predictions.loc[raw_predictions["fold"].eq(fold.name)]
        reference = run_portfolio(
            config.inherited_candidate,
            raw_fold,
            context,
            unresolved,
            config.base,
            1,
        )
        reference["policy"] = "phase5b_reference"
        rows.append(reference)
        persistent_fold = persistent_predictions.loc[persistent_predictions["fold"].eq(fold.name)]
        row, audit = _run_persistent(persistent_fold, context, unresolved, config, 1)
        rows.append(row)
        audits[f"{fold.name}_cost_1x"] = audit
    metrics = pd.DataFrame(rows)
    reference_row = metrics.loc[
        metrics["policy"].eq("phase5b_reference")
        & metrics["period"].eq(connected_period.name)
        & metrics["cost_multiplier"].eq(1)
    ].iloc[0]
    persistent_row = metrics.loc[
        metrics["policy"].eq("phase5c_persistent")
        & metrics["period"].eq(connected_period.name)
        & metrics["cost_multiplier"].eq(1)
    ].iloc[0]
    turnover_reduction = _ratio_reduction(
        float(persistent_row["turnover_on_average_equity"]),
        float(reference_row["turnover_on_average_equity"]),
    )
    cost_reduction = _ratio_reduction(
        float(persistent_row["all_explicit_costs"]),
        float(reference_row["all_explicit_costs"]),
    )
    net_excess_improvement = float(persistent_row["net_excess_return"]) - float(
        reference_row["net_excess_return"]
    )
    mdd_deterioration = max(
        0.0,
        float(reference_row["max_drawdown"]) - float(persistent_row["max_drawdown"]),
    )
    checks = {
        "turnover_reduction": turnover_reduction >= config.minimum_turnover_reduction_ratio,
        "explicit_cost_reduction": cost_reduction >= config.minimum_explicit_cost_reduction_ratio,
        "average_cash_weight": float(persistent_row["average_cash_weight"])
        <= config.maximum_average_cash_weight,
        "net_excess_improvement": net_excess_improvement > config.minimum_net_excess_improvement,
        "mdd_deterioration": mdd_deterioration <= config.maximum_mdd_deterioration,
    }
    annual = metrics.loc[
        metrics["policy"].eq("phase5c_persistent")
        & metrics["period"].str.startswith("I")
        & metrics["cost_multiplier"].eq(1)
    ]
    decision = {
        "experiment_id": config.experiment_id,
        "status": "ADAPTIVE_DIAGNOSTIC_PASS" if all(checks.values()) else "ADAPTIVE_DIAGNOSTIC_FAIL",
        "checks": checks,
        "turnover_reduction_ratio": turnover_reduction,
        "explicit_cost_reduction_ratio": cost_reduction,
        "net_excess_improvement": net_excess_improvement,
        "mdd_deterioration_percentage_points": mdd_deterioration,
        "nonnegative_annual_excess_folds": int((annual["net_excess_return"].astype(float) >= 0.0).sum()),
        "annual_folds": len(annual),
        "result_is_confirmatory": False,
        "trading_candidate": False,
        "development_test_candidate": False,
        "development_test_runs": 0,
        "d20_superseded": False,
    }
    return PolicyEvaluation(metrics, audits, decision)
