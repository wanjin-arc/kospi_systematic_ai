from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from kospi100_backtest.types import Order, Side

from .config import Phase5IConfig


def add_policy_flags(predictions: pd.DataFrame, config: Phase5IConfig) -> pd.DataFrame:
    work = predictions.sort_values(
        ["fold", "security_id", "membership_spell_id", "continuity_segment", "date"], kind="mergesort"
    ).copy()
    keys = ["fold", "security_id", "membership_spell_id", "continuity_segment"]
    entry_hit = work["daily_rank"].le(config.entry_rank).astype(int)
    exit_hit = work["daily_rank"].gt(config.exit_rank).astype(int)
    work["entry_persistent"] = entry_hit.groupby([work[key] for key in keys], sort=False).transform(
        lambda values: values.rolling(config.entry_persistence_sessions, min_periods=config.entry_persistence_sessions).sum().eq(config.entry_persistence_sessions)
    )
    work["exit_persistent"] = exit_hit.groupby([work[key] for key in keys], sort=False).transform(
        lambda values: values.rolling(config.exit_persistence_sessions, min_periods=config.exit_persistence_sessions).sum().eq(config.exit_persistence_sessions)
    )
    rebalance_dates: set[pd.Timestamp] = set()
    for _, group in work.groupby("fold", sort=True):
        dates = sorted(group["date"].drop_duplicates())
        rebalance_dates.update(dates[:: config.rebalance_sessions])
    work["rebalance_date"] = work["date"].isin(rebalance_dates)
    return work.sort_values(["fold", "date", "security_id"], kind="mergesort").reset_index(drop=True)


def generate_orders(
    predictions: pd.DataFrame,
    sessions: tuple[date, ...],
    config: Phase5IConfig,
) -> tuple[tuple[Order, ...], dict[str, int]]:
    next_session = {sessions[index]: sessions[index + 1] for index in range(len(sessions) - 1)}
    work = predictions.loc[predictions["rebalance_date"]].copy()
    work["signal_date"] = work["date"].dt.date
    work = work.loc[work["signal_date"].isin(next_session)]
    orders: list[Order] = []
    entry_orders = exit_orders = 0
    for signal_date, group in work.groupby("signal_date", sort=True):
        exits = group.loc[group["exit_persistent"]].sort_values(["daily_rank", "security_id"], ascending=[False, True])
        for row in exits.itertuples(index=False):
            orders.append(
                Order(
                    order_id=f"P5I:EXIT:{signal_date.isoformat()}:{row.security_id}",
                    signal_date=signal_date,
                    execute_date=next_session[signal_date],
                    security_id=str(row.security_id),
                    side=Side.SELL,
                    priority=-25_000,
                    reason="THREE_SESSION_RANK_LOSS",
                )
            )
            exit_orders += 1
        entries = group.loc[group["entry_persistent"]].sort_values(["daily_rank", "security_id"]).head(config.base.maximum_holdings)
        for row in entries.itertuples(index=False):
            orders.append(
                Order(
                    order_id=f"P5I:ENTRY:{signal_date.isoformat()}:R{int(row.daily_rank):02d}:{row.security_id}",
                    signal_date=signal_date,
                    execute_date=next_session[signal_date],
                    security_id=str(row.security_id),
                    side=Side.BUY,
                    target_weight=config.base.target_weight,
                    priority=int(row.daily_rank),
                    limit_price=Decimal(str(row.close)) * (Decimal("1") + config.base.entry_gap_cap),
                    max_holding_sessions=config.maximum_holding_sessions,
                    reason="THREE_SESSION_TOP10_FIVE_SESSION_REBALANCE",
                )
            )
            entry_orders += 1
    return tuple(orders), {"orders": len(orders), "entry_orders": entry_orders, "exit_orders": exit_orders}
