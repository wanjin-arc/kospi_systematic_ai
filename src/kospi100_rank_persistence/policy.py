from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from kospi100_backtest.types import Order, Side

from .config import Phase5CConfig


def apply_causal_persistence(
    predictions: pd.DataFrame,
    sessions: tuple[date, ...],
    config: Phase5CConfig,
) -> pd.DataFrame:
    required = {"date", "security_id", "membership_spell_id", "score", "fold", "close"}
    missing = required - set(predictions.columns)
    if missing:
        raise ValueError(f"Phase 5C 점수 입력 컬럼 누락: {sorted(missing)}")
    session_index = {pd.Timestamp(session): index for index, session in enumerate(sessions)}
    work = predictions.copy()
    work["session_index"] = work["date"].map(session_index)
    if work["session_index"].isna().any():
        raise ValueError("점수 날짜가 거래소 세션에 없습니다")
    work["session_index"] = work["session_index"].astype(int)
    work = work.sort_values(
        ["fold", "security_id", "membership_spell_id", "date"], kind="mergesort"
    ).reset_index(drop=True)
    group_keys = ["fold", "security_id", "membership_spell_id"]
    gap = work.groupby(group_keys, sort=False)["session_index"].diff().ne(1)
    work["continuity_segment"] = gap.groupby(
        [work[key] for key in group_keys], sort=False
    ).cumsum().astype(int)
    ema_keys = [*group_keys, "continuity_segment"]
    alpha = 2.0 / (config.ema_span_sessions + 1.0)
    work["raw_score"] = work["score"].astype(float)
    work["smoothed_score"] = work.groupby(ema_keys, sort=False)["raw_score"].transform(
        lambda values: values.ewm(alpha=alpha, adjust=False, min_periods=1).mean()
    )
    work["score"] = work.groupby("date", sort=False)["smoothed_score"].rank(
        method="average", pct=True
    )
    work = work.sort_values(
        ["date", "score", "security_id"], ascending=[True, False, True], kind="mergesort"
    )
    work["daily_rank"] = work.groupby("date", sort=False).cumcount() + 1
    work["candidate"] = config.policy_candidate
    return work.sort_values(["fold", "date", "security_id"], kind="mergesort").reset_index(drop=True)


def generate_persistent_orders(
    predictions: pd.DataFrame,
    sessions: tuple[date, ...],
    config: Phase5CConfig,
) -> tuple[tuple[Order, ...], dict[str, int]]:
    next_session = {sessions[index]: sessions[index + 1] for index in range(len(sessions) - 1)}
    session_position = {session: index for index, session in enumerate(sessions)}
    work = predictions.copy()
    work["signal_date"] = work["date"].dt.date
    work = work.loc[work["signal_date"].isin(next_session)].copy()
    orders: list[Order] = []
    last_fallback_eligible: dict[str, int] = {}
    desired_buys = fallback_buys = rank_exits = 0
    for signal_date, group in work.groupby("signal_date", sort=True):
        ranked = group.sort_values(
            ["score", "security_id"], ascending=[False, True], kind="mergesort"
        ).copy()
        ranked["daily_rank"] = range(1, len(ranked) + 1)
        position = session_position[signal_date]
        for row in ranked.loc[ranked["daily_rank"] > config.exit_rank].itertuples(index=False):
            previous = last_fallback_eligible.get(str(row.security_id))
            if previous is None or position - previous > config.maximum_holding_sessions:
                continue
            orders.append(
                Order(
                    order_id=f"P5C:RANK_EXIT:{signal_date.isoformat()}:{row.security_id}",
                    signal_date=signal_date,
                    execute_date=next_session[signal_date],
                    security_id=str(row.security_id),
                    side=Side.SELL,
                    priority=-25_000,
                    reason="PERSISTENT_RANK_LOSS_EXIT",
                )
            )
            rank_exits += 1
        entry_rows = ranked.head(config.fallback_max_rank)
        for row in entry_rows.itertuples(index=False):
            rank = int(row.daily_rank)
            last_fallback_eligible[str(row.security_id)] = position
            orders.append(
                Order(
                    order_id=f"P5C:{signal_date.isoformat()}:R{rank:02d}:{row.security_id}",
                    signal_date=signal_date,
                    execute_date=next_session[signal_date],
                    security_id=str(row.security_id),
                    side=Side.BUY,
                    target_weight=config.base.target_weight,
                    priority=rank,
                    limit_price=Decimal(str(row.close)) * (Decimal("1") + config.base.entry_gap_cap),
                    max_holding_sessions=config.maximum_holding_sessions,
                    reason="PERSISTENT_RANKING_ENTRY" if rank <= config.desired_entry_rank else "PERSISTENT_FALLBACK_ENTRY",
                )
            )
            if rank <= config.desired_entry_rank:
                desired_buys += 1
            else:
                fallback_buys += 1
    audit = {
        "orders": len(orders),
        "desired_entry_orders": desired_buys,
        "fallback_entry_orders": fallback_buys,
        "rank_loss_exit_orders": rank_exits,
    }
    return tuple(orders), audit
