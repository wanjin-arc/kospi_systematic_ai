from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from kospi100_backtest.types import Order, Side

from .config import MODEL_CONTRACT, MultiHorizonConfig


def apply_consensus_policy(predictions: pd.DataFrame, config: MultiHorizonConfig) -> pd.DataFrame:
    predicted = [f"predicted_net_excess_{value}" for value in config.horizons]
    required = {"date", "security_id", "membership_spell_id", "close", "fold", *predicted}
    missing = required - set(predictions.columns)
    if missing:
        raise ValueError(f"Phase 5G 점수 입력 컬럼 누락: {sorted(missing)}")
    work = predictions.copy()
    work["positive_horizons"] = work[predicted].gt(0.0).sum(axis=1)
    work["predicted_median_net_excess"] = np.median(work[predicted].to_numpy(dtype=float), axis=1)
    work = work.sort_values(
        ["date", "predicted_median_net_excess", "security_id"],
        ascending=[True, False, True], kind="mergesort",
    )
    work["consensus_rank"] = work.groupby("date", sort=False).cumcount() + 1
    work["passes_direction_gate"] = work["positive_horizons"] >= config.minimum_positive_horizons
    work["passes_magnitude_gate"] = (
        work["predicted_median_net_excess"] >= config.entry_median_net_excess
    )
    work["entry_eligible"] = (
        work["passes_direction_gate"] & work["passes_magnitude_gate"]
        & (work["consensus_rank"] <= config.maximum_entry_candidates)
    )
    work["exit_signal"] = (
        (work["positive_horizons"] <= config.exit_positive_horizons)
        | (work["predicted_median_net_excess"] <= config.exit_median_net_excess)
    )
    work["model"] = MODEL_CONTRACT
    return work.sort_values(["fold", "date", "security_id"], kind="mergesort").reset_index(drop=True)


def generate_orders(
    policy: pd.DataFrame,
    sessions: tuple[date, ...],
    config: MultiHorizonConfig,
) -> tuple[tuple[Order, ...], dict[str, object]]:
    next_session = {sessions[index]: sessions[index + 1] for index in range(len(sessions) - 1)}
    positions = {session: index for index, session in enumerate(sessions)}
    work = policy.copy()
    work["signal_date"] = pd.to_datetime(work["date"]).dt.date
    work = work.loc[work["signal_date"].isin(next_session)].copy()
    orders: list[Order] = []
    recently_submitted: dict[str, int] = {}
    entry_orders = 0
    exit_orders = 0
    no_trade_days = 0
    eligible_by_day: list[int] = []
    for signal_date, group in work.groupby("signal_date", sort=True):
        ranked = group.sort_values(
            ["predicted_median_net_excess", "security_id"],
            ascending=[False, True], kind="mergesort",
        )
        eligible = int(ranked["entry_eligible"].sum())
        eligible_by_day.append(eligible)
        if eligible == 0:
            no_trade_days += 1
        position = positions[signal_date]
        for row in ranked.loc[ranked["exit_signal"]].itertuples(index=False):
            last = recently_submitted.get(str(row.security_id))
            if last is None or position - last > config.maximum_holding_sessions:
                continue
            orders.append(Order(
                order_id=f"P5G:EXIT:{signal_date.isoformat()}:{row.security_id}",
                signal_date=signal_date, execute_date=next_session[signal_date],
                security_id=str(row.security_id), side=Side.SELL, priority=-25_000,
                reason="MULTIHORIZON_CONSENSUS_LOST",
            ))
            exit_orders += 1
        for row in ranked.loc[ranked["entry_eligible"]].itertuples(index=False):
            rank = int(row.consensus_rank)
            recently_submitted[str(row.security_id)] = position
            orders.append(Order(
                order_id=f"P5G:{signal_date.isoformat()}:R{rank:02d}:{row.security_id}",
                signal_date=signal_date, execute_date=next_session[signal_date],
                security_id=str(row.security_id), side=Side.BUY,
                target_weight=config.base.target_weight, priority=rank,
                limit_price=Decimal(str(row.close)) * (Decimal("1") + config.base.entry_gap_cap),
                max_holding_sessions=config.maximum_holding_sessions,
                reason="MULTIHORIZON_POSITIVE_CONSENSUS_ENTRY",
            ))
            entry_orders += 1
    return tuple(orders), {
        "orders": len(orders), "entry_orders": entry_orders, "model_exit_orders": exit_orders,
        "signal_days": len(eligible_by_day), "no_trade_signal_days": no_trade_days,
        "no_trade_signal_day_ratio": no_trade_days / len(eligible_by_day) if eligible_by_day else 0.0,
        "average_eligible_candidates": sum(eligible_by_day) / len(eligible_by_day) if eligible_by_day else 0.0,
        "maximum_eligible_candidates": max(eligible_by_day, default=0),
        "minimum_required_holdings": 0, "average_cash_is_hard_gate": False,
    }
