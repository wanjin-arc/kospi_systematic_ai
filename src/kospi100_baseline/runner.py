from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd

from kospi100_backtest.costs import CostSchedule, ExecutionCostModel
from kospi100_backtest.engine import BacktestEngine, EngineConfig
from kospi100_backtest.io import write_result
from kospi100_backtest.types import Bar, CorporateAction, CorporateActionType, Order, OrderStatus, RunResult, Side

from .config import BaselineConfig, Period, load_config
from .data import DevelopmentBundle, load_development_bundle
from .features import FeatureResult, build_features


@dataclass(frozen=True)
class PeriodContext:
    period: Period
    sessions: tuple[date, ...]
    bars: tuple[Bar, ...]
    benchmark_close: Mapping[date, Decimal]
    features: pd.DataFrame
    control_orders: tuple[Order, ...]
    corporate_actions: tuple[CorporateAction, ...]
    first_evaluation_session: date


def _decimal(value: object) -> Decimal | None:
    if pd.isna(value):
        return None
    return Decimal(str(value))


def _json_default(value: object) -> object:
    if isinstance(value, (date, Decimal, pd.Timestamp)):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )


def generate_signal_orders(
    features: pd.DataFrame,
    sessions: tuple[date, ...],
    *,
    holding_sessions: int,
    maximum_holdings: int,
) -> tuple[Order, ...]:
    next_session = {sessions[index]: sessions[index + 1] for index in range(len(sessions) - 1)}
    target_weight = min(Decimal(1) / Decimal(maximum_holdings), Decimal("0.10"))
    candidates = features.loc[features["baseline_candidate"]].copy()
    candidates["signal_date"] = candidates["date"].dt.date
    candidates = candidates.loc[candidates["signal_date"].isin(next_session)]
    orders: list[Order] = []
    for signal_date, group in candidates.groupby("signal_date", sort=True):
        ranked = group.sort_values(["excess_return126", "security_id"], ascending=[False, True], kind="mergesort")
        for rank, row in enumerate(ranked.head(maximum_holdings).itertuples(index=False), start=1):
            close = Decimal(str(row.close))
            orders.append(
                Order(
                    order_id=(
                        f"P3:{signal_date.isoformat()}:H{holding_sessions}:N{maximum_holdings}:"
                        f"R{rank:02d}:{row.security_id}"
                    ),
                    signal_date=signal_date,
                    execute_date=next_session[signal_date],
                    security_id=row.security_id,
                    side=Side.BUY,
                    target_weight=target_weight,
                    priority=rank,
                    limit_price=close * Decimal("1.05"),
                    max_holding_sessions=holding_sessions,
                    reason="DUAL_MOMENTUM_ENTRY",
                )
            )
    return tuple(orders)


def _sessions_for_period(index: pd.DataFrame, period: Period) -> tuple[tuple[date, ...], date]:
    ordered = index.sort_values("date", kind="mergesort")
    evaluation = ordered.loc[ordered["date"].between(pd.Timestamp(period.start), pd.Timestamp(period.end)), "date"]
    if evaluation.empty:
        raise ValueError(f"no index sessions in {period.name}")
    seed = ordered.loc[ordered["date"] < evaluation.iloc[0], "date"]
    if seed.empty:
        raise ValueError(f"no pre-period signal seed for {period.name}")
    selected = ordered.loc[ordered["date"].between(seed.iloc[-1], evaluation.iloc[-1]), "date"]
    sessions = tuple(item.date() for item in selected)
    return sessions, evaluation.iloc[0].date()


def _bars_for_period(full: pd.DataFrame, sessions: tuple[date, ...]) -> list[Bar]:
    start, end = pd.Timestamp(sessions[0]), pd.Timestamp(sessions[-1])
    rows = full.loc[full["date"].between(start, end)].sort_values(["date", "security_id"], kind="mergesort")
    bars: list[Bar] = []
    for row in rows.itertuples(index=False):
        tradable = bool(row.tradable)
        open_price = _decimal(row.open)
        high = _decimal(row.high)
        low = _decimal(row.low)
        close = _decimal(row.close)
        if tradable and any(value is None for value in (open_price, high, low, close)):
            raise ValueError(f"tradable row lacks OHLC: {row.date} {row.security_id}")
        bars.append(
            Bar(
                session=row.date.date(),
                security_id=row.security_id,
                open=open_price,
                high=high,
                low=low,
                close=close,
                tradable=tradable,
            )
        )
    return bars


def _previous_session(sessions: tuple[date, ...], target: date) -> date | None:
    prior = [session for session in sessions if session < target]
    return prior[-1] if prior else None


def _control_events(
    bundle: DevelopmentBundle,
    sessions: tuple[date, ...],
    bars: list[Bar],
) -> tuple[tuple[Order, ...], tuple[CorporateAction, ...]]:
    session_set = set(sessions)
    bar_map = {(bar.session, bar.security_id): bar for bar in bars}
    orders: list[Order] = []
    actions: list[CorporateAction] = []

    mechanical = bundle.corporate_actions.loc[
        bundle.corporate_actions["feature_handling"].eq("PIT_MECHANICAL_ADJUSTMENT")
    ]
    for row in mechanical.sort_values(["feature_boundary_date", "canonical_event_id"]).itertuples(index=False):
        boundary = row.feature_boundary_date.date()
        if boundary not in session_set:
            continue
        bar = bar_map.get((boundary, row.security_id))
        cash_price = bar.open if bar is not None and bar.open is not None and bar.open > 0 else None
        actions.append(
            CorporateAction(
                action_id=f"P3:MECH:{row.canonical_event_id}",
                effective_date=boundary,
                security_id=row.security_id,
                kind=(CorporateActionType.BONUS_ISSUE if row.event_type == "BONUS_ISSUE" else CorporateActionType.SPLIT),
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
        filing = row.first_filing_date.date()
        if boundary not in session_set or filing >= boundary:
            continue
        signal_date = _previous_session(sessions, boundary)
        if signal_date is None:
            continue
        orders.append(
            Order(
                order_id=f"P3:CA_EXIT:{row.canonical_event_id}",
                signal_date=signal_date,
                execute_date=boundary,
                security_id=row.security_id,
                side=Side.SELL,
                priority=-30_000,
                reason="CA_DATA_SAFETY_EXIT",
            )
        )

    removals = bundle.removals.sort_values(["execution_date", "security_id", "membership_spell_id"])
    for row in removals.itertuples(index=False):
        execution = row.execution_date.date()
        signal = row.last_member_date.date()
        if execution not in session_set or signal not in session_set:
            continue
        if row.resolution_type == "DIRECT_OLD_SECURITY_FIRST_TRADABLE_OPEN":
            target_security = row.security_id
            actual = bar_map.get((execution, target_security))
            if actual is None or actual.open is None:
                raise ValueError(f"direct removal lacks execution bar: {row.membership_spell_id}")
            if abs(actual.open - Decimal(str(row.execution_open))) > Decimal("0.01"):
                raise ValueError(f"direct removal open mismatch: {row.membership_spell_id}")
        elif row.resolution_type == "CORPORATE_ACTION_SUCCESSOR_TRANSITION":
            target_security = f"REMOVAL_SUCCESSOR:{row.membership_spell_id}"
            execution_open = Decimal(str(row.execution_open))
            bars.append(Bar(execution, target_security, execution_open, execution_open, execution_open, execution_open))
            actions.append(
                CorporateAction(
                    action_id=f"P3:REMOVAL_TRANSFORM:{row.membership_spell_id}",
                    effective_date=execution,
                    security_id=row.security_id,
                    kind=CorporateActionType.SUCCESSOR,
                    share_multiplier=Decimal(str(row.qty_multiplier)),
                    successor_security_id=target_security,
                    cash_in_lieu_price=execution_open,
                    source_status="READY",
                )
            )
        else:
            raise ValueError(f"unknown removal resolution: {row.resolution_type}")
        orders.append(
            Order(
                order_id=f"P3:REMOVAL_EXIT:{row.membership_spell_id}",
                signal_date=signal,
                execute_date=execution,
                security_id=target_security,
                side=Side.SELL,
                priority=-40_000,
                reason="UNIVERSE_REMOVAL_EXIT",
            )
        )
    return tuple(orders), tuple(actions)


def _period_context(bundle: DevelopmentBundle, features: pd.DataFrame, period: Period) -> PeriodContext:
    sessions, first_evaluation = _sessions_for_period(bundle.index, period)
    bars = _bars_for_period(bundle.full_history, sessions)
    control_orders, actions = _control_events(bundle, sessions, bars)
    benchmark_rows = bundle.index.loc[
        bundle.index["date"].dt.date.isin(sessions), ["date", "close"]
    ]
    benchmark = {row.date.date(): Decimal(str(row.close)) for row in benchmark_rows.itertuples(index=False)}
    feature_rows = features.loc[features["date"].dt.date.isin(sessions)].copy()
    return PeriodContext(
        period=period,
        sessions=sessions,
        bars=tuple(bars),
        benchmark_close=benchmark,
        features=feature_rows,
        control_orders=control_orders,
        corporate_actions=actions,
        first_evaluation_session=first_evaluation,
    )


def _engine(config: BaselineConfig, maximum_holdings: int) -> BacktestEngine:
    costs = ExecutionCostModel(
        CostSchedule.from_csv(config.tax_schedule_path),
        commission_rate=config.commission_rate,
        buy_slippage_rate=config.slippage_rate,
        sell_slippage_rate=config.slippage_rate,
    )
    return BacktestEngine(
        EngineConfig(initial_cash=config.initial_cash, allow_pyramiding=False, max_positions=maximum_holdings),
        costs,
    )


def _run_candidate(
    config: BaselineConfig,
    context: PeriodContext,
    holding_sessions: int,
    maximum_holdings: int,
) -> tuple[RunResult, tuple[Order, ...]]:
    signal_orders = generate_signal_orders(
        context.features,
        context.sessions,
        holding_sessions=holding_sessions,
        maximum_holdings=maximum_holdings,
    )
    all_orders = tuple(context.control_orders) + signal_orders
    result = _engine(config, maximum_holdings).run(
        context.sessions,
        context.bars,
        all_orders,
        corporate_actions=context.corporate_actions,
        benchmark_close=context.benchmark_close,
    )
    unsafe = {
        OrderStatus.UNFILLED_GAP_LIMIT,
        OrderStatus.UNFILLED_NOT_TRADABLE,
        OrderStatus.UNFILLED_NO_BAR,
        OrderStatus.UNFILLED_LIQUIDITY,
        OrderStatus.PARTIALLY_FILLED,
    }
    failed_controls = [
        event
        for event in result.order_events
        if event.order_id.startswith(("P3:CA_EXIT:", "P3:REMOVAL_EXIT:")) and event.status in unsafe
    ]
    if failed_controls:
        raise RuntimeError(f"a mandatory safety/removal exit did not complete: {failed_controls[0]}")
    if not result.reconciliation.passed:
        raise AssertionError("candidate ledger failed reconciliation")
    return result, all_orders


def _metric_row(period: str, holding: int, holdings: int, result: RunResult) -> dict[str, object]:
    metrics = result.metrics
    strategy_return = Decimal(str(metrics["total_return"]))
    benchmark_return = Decimal(str(metrics["benchmark_total_return"]))
    return {
        "period": period,
        "holding_sessions": holding,
        "maximum_holdings": holdings,
        "total_return": strategy_return,
        "benchmark_total_return": benchmark_return,
        "net_excess_return": strategy_return - benchmark_return,
        "cagr": metrics["cagr"],
        "sharpe_zero_rf": metrics["sharpe_zero_rf"],
        "max_drawdown": metrics["max_drawdown"],
        "turnover_on_average_equity": metrics["turnover_on_average_equity"],
        "all_explicit_costs": metrics["all_explicit_costs"],
        "average_cash_weight": metrics["average_cash_weight"],
        "closed_trades": metrics["closed_trades"],
        "reconciliation": metrics["reconciliation"],
        "input_hash": result.input_hash,
        "engine_config_hash": result.config_hash,
    }


def _float_or_negative_infinity(value: object) -> float:
    if value is None or value == "":
        return float("-inf")
    return float(value)


def _select(validation_rows: Iterable[dict[str, object]]) -> dict[str, object]:
    return max(
        validation_rows,
        key=lambda row: (
            _float_or_negative_infinity(row["sharpe_zero_rf"]),
            float(row["net_excess_return"]),
            float(row["max_drawdown"]),
            -float(row["turnover_on_average_equity"]),
            -int(row["holding_sessions"]),
            -int(row["maximum_holdings"]),
        ),
    )


def _orders_frame(orders: tuple[Order, ...]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for order in orders:
        row = asdict(order)
        row["side"] = order.side.value
        rows.append({key: "" if value is None else str(value) for key, value in row.items()})
    return pd.DataFrame(rows)


def _source_hash() -> str:
    paths = sorted(Path("src/kospi100_backtest").glob("*.py")) + sorted(Path("src/kospi100_baseline").glob("*.py"))
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _build_manifest(output: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(output.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        hashes[path.relative_to(output).as_posix()] = digest
    _write_json(output / "manifest.json", hashes)
    return hashes


def run_phase3(config_path: Path, output: Path) -> dict[str, object]:
    config = load_config(config_path)
    bundle = load_development_bundle(config)
    feature_result: FeatureResult = build_features(bundle.feature_panel, bundle.index, bundle.corporate_actions)
    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / "data_audit.json", bundle.audit)
    _write_json(output / "feature_audit.json", feature_result.audit)

    contexts = {
        name: _period_context(bundle, feature_result.frame, config.periods[name])
        for name in ("train", "validation")
    }
    sensitivity: list[dict[str, object]] = []
    for holding in config.holding_sessions:
        for holdings in config.maximum_holdings:
            for period_name in ("train", "validation"):
                result, _ = _run_candidate(config, contexts[period_name], holding, holdings)
                sensitivity.append(_metric_row(period_name, holding, holdings, result))

    validation_rows = [row for row in sensitivity if row["period"] == "validation"]
    selected = _select(validation_rows)
    selected_holding = int(selected["holding_sessions"])
    selected_holdings = int(selected["maximum_holdings"])

    detailed_metrics: dict[str, dict[str, object]] = {}
    selected_orders: dict[str, tuple[Order, ...]] = {}
    for period_name in ("train", "validation"):
        result, orders = _run_candidate(
            config, contexts[period_name], selected_holding, selected_holdings
        )
        write_result(result, output / f"selected_{period_name}")
        detailed_metrics[period_name] = _metric_row(period_name, selected_holding, selected_holdings, result)
        selected_orders[period_name] = orders

    development_context = _period_context(bundle, feature_result.frame, config.periods["development_test"])
    development_result, development_orders = _run_candidate(
        config, development_context, selected_holding, selected_holdings
    )
    write_result(development_result, output / "selected_development_test")
    development_row = _metric_row(
        "development_test", selected_holding, selected_holdings, development_result
    )
    detailed_metrics["development_test"] = development_row
    selected_orders["development_test"] = development_orders

    sensitivity_frame = pd.DataFrame(sensitivity)
    sensitivity_frame.to_csv(output / "train_validation_sensitivity.csv", index=False, lineterminator="\n")
    for name, orders in selected_orders.items():
        _orders_frame(orders).to_csv(output / f"selected_{name}_orders.csv", index=False, lineterminator="\n")

    selected_validation_excess = Decimal(str(detailed_metrics["validation"]["net_excess_return"]))
    development_excess = Decimal(str(development_row["net_excess_return"]))
    trading_candidate = selected_validation_excess > 0 and development_excess > 0
    selection = {
        "experiment_id": config.experiment_id,
        "selection_partition": "validation_only",
        "selected_holding_sessions": selected_holding,
        "selected_maximum_holdings": selected_holdings,
        "selected_target_weight": str(min(Decimal(1) / Decimal(selected_holdings), Decimal("0.10"))),
        "selection_objective": config.payload["selection"]["objective"],
        "selection_tie_breaks": config.payload["selection"]["tie_breaks"],
        "development_test_candidates_run": 1,
        "reference_baseline_status": "ACCEPTED",
        "trading_candidate_status": "PASS" if trading_candidate else "FAIL",
        "trading_candidate_gate": "validation and development-test net excess returns must both be positive",
        "validation_net_excess_return": selected_validation_excess,
        "development_test_net_excess_return": development_excess,
        "final_oos_accessed": False,
    }
    _write_json(output / "selection.json", selection)
    _write_json(output / "selected_period_metrics.json", detailed_metrics)
    summary = {
        "experiment_id": config.experiment_id,
        "status": "COMPLETED",
        "code_hash": _source_hash(),
        "config_hash": config.config_hash,
        "data_hash": bundle.data_hash,
        "parameter_combinations": 9,
        "train_runs": 9,
        "validation_runs": 9,
        "development_test_runs": 1,
        "selected": selection,
        "data_checks": bundle.audit,
        "feature_checks": feature_result.audit,
        "all_reconciliations_passed": all(row["reconciliation"] == "PASS" for row in sensitivity)
        and development_row["reconciliation"] == "PASS",
        "final_oos_accessed": False,
    }
    _write_json(output / "run_summary.json", summary)
    _build_manifest(output)
    return summary
