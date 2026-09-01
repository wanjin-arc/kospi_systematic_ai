from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from kospi100_backtest.types import Order, Side

from .config import MODEL_CONTRACT, TemporalRiskConfig


def apply_temporal_policy(predictions: pd.DataFrame, config: TemporalRiskConfig) -> pd.DataFrame:
    required = {
        "date", "security_id", "membership_spell_id", "close", "fold",
        "predicted_mean_net_excess", "predicted_median_net_excess", "market_anomaly",
    }
    missing = required - set(predictions.columns)
    if missing:
        raise ValueError(f"Phase 5F 점수 입력 컬럼 누락: {sorted(missing)}")
    work = predictions.copy().sort_values(
        ["date", "predicted_mean_net_excess", "security_id"],
        ascending=[True, False, True], kind="mergesort",
    )
    work["absolute_rank"] = work.groupby("date", sort=False).cumcount() + 1
    work["passes_mean_gate"] = work["predicted_mean_net_excess"] >= config.entry_net_excess
    work["passes_median_gate"] = (
        work["predicted_median_net_excess"] > config.entry_median_net_excess
    )
    work["passes_market_gate"] = ~work["market_anomaly"].astype(bool)
    work["entry_eligible"] = (
        work["passes_mean_gate"]
        & work["passes_median_gate"]
        & work["passes_market_gate"]
        & (work["absolute_rank"] <= config.maximum_entry_candidates)
    )
    work["exit_signal"] = (
        (work["predicted_mean_net_excess"] <= config.exit_net_excess)
        | (work["predicted_median_net_excess"] <= config.exit_median_net_excess)
        | work["market_anomaly"].astype(bool)
    )
    work["model"] = MODEL_CONTRACT
    return work.sort_values(["fold", "date", "security_id"], kind="mergesort").reset_index(drop=True)


def generate_temporal_orders(
    predictions: pd.DataFrame,
    sessions: tuple[date, ...],
    config: TemporalRiskConfig,
) -> tuple[tuple[Order, ...], dict[str, object]]:
    next_session = {sessions[index]: sessions[index + 1] for index in range(len(sessions) - 1)}
    session_position = {session: index for index, session in enumerate(sessions)}
    work = predictions.copy()
    work["signal_date"] = work["date"].dt.date
    work = work.loc[work["signal_date"].isin(next_session)].copy()
    orders: list[Order] = []
    recently_submitted: dict[str, int] = {}
    entry_orders = 0
    model_exit_orders = 0
    no_trade_days = 0
    anomaly_veto_days = 0
    eligible_by_day: list[int] = []
    for signal_date, group in work.groupby("signal_date", sort=True):
        ranked = group.sort_values(
            ["predicted_mean_net_excess", "security_id"],
            ascending=[False, True], kind="mergesort",
        )
        eligible_count = int(ranked["entry_eligible"].sum())
        eligible_by_day.append(eligible_count)
        if eligible_count == 0:
            no_trade_days += 1
        if bool(ranked["market_anomaly"].iloc[0]):
            anomaly_veto_days += 1
        position = session_position[signal_date]
        for row in ranked.loc[ranked["exit_signal"]].itertuples(index=False):
            previous = recently_submitted.get(str(row.security_id))
            if previous is None or position - previous > config.maximum_holding_sessions:
                continue
            orders.append(Order(
                order_id=f"P5F:EXIT:{signal_date.isoformat()}:{row.security_id}",
                signal_date=signal_date, execute_date=next_session[signal_date],
                security_id=str(row.security_id), side=Side.SELL, priority=-25_000,
                reason="TEMPORAL_OR_MARKET_RISK_EXIT",
            ))
            model_exit_orders += 1
        for row in ranked.loc[ranked["entry_eligible"]].itertuples(index=False):
            rank = int(row.absolute_rank)
            recently_submitted[str(row.security_id)] = position
            orders.append(Order(
                order_id=f"P5F:{signal_date.isoformat()}:R{rank:02d}:{row.security_id}",
                signal_date=signal_date, execute_date=next_session[signal_date],
                security_id=str(row.security_id), side=Side.BUY,
                target_weight=config.base.target_weight, priority=rank,
                limit_price=Decimal(str(row.close)) * (Decimal("1") + config.base.entry_gap_cap),
                max_holding_sessions=config.maximum_holding_sessions,
                reason="TEMPORAL_MEAN_MEDIAN_NON_ANOMALOUS_ENTRY",
            ))
            entry_orders += 1
    audit: dict[str, object] = {
        "orders": len(orders),
        "entry_orders": entry_orders,
        "model_exit_orders": model_exit_orders,
        "signal_days": len(eligible_by_day),
        "no_trade_signal_days": no_trade_days,
        "no_trade_signal_day_ratio": no_trade_days / len(eligible_by_day) if eligible_by_day else 0.0,
        "anomaly_veto_signal_days": anomaly_veto_days,
        "anomaly_veto_signal_day_ratio": anomaly_veto_days / len(eligible_by_day) if eligible_by_day else 0.0,
        "average_eligible_candidates": sum(eligible_by_day) / len(eligible_by_day) if eligible_by_day else 0.0,
        "maximum_eligible_candidates": max(eligible_by_day, default=0),
        "minimum_required_holdings": 0,
        "average_cash_is_hard_gate": False,
        "market_anomaly_hard_entry_veto_used": True,
    }
    return tuple(orders), audit
