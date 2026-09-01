from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from kospi100_backtest.types import Order, Side

from .config import SelectiveConfig


REGIME_CAPACITY = {"risk_on": 10, "neutral": 5, "risk_off": 0}


def apply_selective_scores(
    predictions: pd.DataFrame,
    sessions: tuple[date, ...],
    config: SelectiveConfig,
) -> pd.DataFrame:
    required = {
        "date",
        "security_id",
        "membership_spell_id",
        "raw_prediction",
        "fold",
        "close",
        "index_trend_200",
        "breadth_above_sma200",
    }
    missing = required - set(predictions.columns)
    if missing:
        raise ValueError(f"Phase 5D 점수 입력 컬럼 누락: {sorted(missing)}")
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
    alpha = 2.0 / (config.ema_span_sessions + 1.0)
    work["smoothed_raw_prediction"] = work.groupby(
        [*group_keys, "continuity_segment"], sort=False
    )["raw_prediction"].transform(
        lambda values: values.ewm(alpha=alpha, adjust=False, min_periods=1).mean()
    )
    daily = work.groupby("date", sort=False)["smoothed_raw_prediction"]
    mean = daily.transform("mean")
    std = daily.transform(lambda values: values.std(ddof=0))
    work["score_z"] = np.where(std > 0.0, (work["smoothed_raw_prediction"] - mean) / std, 0.0)
    work["score"] = daily.rank(method="average", pct=True)
    work = work.sort_values(
        ["date", "score", "security_id"], ascending=[True, False, True], kind="mergesort"
    )
    work["daily_rank"] = work.groupby("date", sort=False).cumcount() + 1
    trend = work["index_trend_200"].astype(float) > 0.0
    breadth = work["breadth_above_sma200"].astype(float) >= 0.5
    work["market_regime"] = np.select(
        [trend & breadth, trend ^ breadth],
        ["risk_on", "neutral"],
        default="risk_off",
    )
    work["regime_capacity"] = work["market_regime"].map(REGIME_CAPACITY).astype(int)
    entry_rank_cap = np.where(
        work["market_regime"].eq("risk_on"),
        config.risk_on_entry_rank,
        np.where(work["market_regime"].eq("neutral"), config.neutral_entry_rank, 0),
    )
    work["entry_eligible"] = (
        (work["score_z"] >= config.entry_zscore)
        & (work["daily_rank"] <= entry_rank_cap)
        & (work["regime_capacity"] > 0)
    )
    work["candidate"] = config.policy_candidate
    return work.sort_values(["fold", "date", "security_id"], kind="mergesort").reset_index(drop=True)


def generate_selective_orders(
    predictions: pd.DataFrame,
    sessions: tuple[date, ...],
    config: SelectiveConfig,
) -> tuple[tuple[Order, ...], dict[str, object]]:
    next_session = {sessions[index]: sessions[index + 1] for index in range(len(sessions) - 1)}
    session_position = {session: index for index, session in enumerate(sessions)}
    work = predictions.copy()
    work["signal_date"] = work["date"].dt.date
    work = work.loc[work["signal_date"].isin(next_session)].copy()
    orders: list[Order] = []
    recently_submitted: dict[str, int] = {}
    regime_days = {name: 0 for name in REGIME_CAPACITY}
    entry_orders = {name: 0 for name in REGIME_CAPACITY}
    exit_reasons = {"risk_off": 0, "score_or_rank": 0}
    for signal_date, group in work.groupby("signal_date", sort=True):
        regimes = group["market_regime"].drop_duplicates().tolist()
        if len(regimes) != 1:
            raise ValueError(f"날짜별 시장상태가 하나가 아닙니다: {signal_date}")
        regime = str(regimes[0])
        regime_days[regime] += 1
        ranked = group.sort_values(
            ["score", "security_id"], ascending=[False, True], kind="mergesort"
        )
        position = session_position[signal_date]
        hold_rank = config.risk_on_hold_rank if regime == "risk_on" else config.neutral_hold_rank
        if regime == "risk_off":
            hold_rank = 0
        for row in ranked.itertuples(index=False):
            previous = recently_submitted.get(str(row.security_id))
            if previous is None or position - previous > config.maximum_holding_sessions:
                continue
            risk_off_exit = regime == "risk_off"
            signal_exit = float(row.score_z) < config.exit_zscore or int(row.daily_rank) > hold_rank
            if not (risk_off_exit or signal_exit):
                continue
            reason = "MARKET_RISK_OFF_EXIT" if risk_off_exit else "SCORE_OR_CAPACITY_EXIT"
            orders.append(
                Order(
                    order_id=f"P5D:EXIT:{signal_date.isoformat()}:{row.security_id}",
                    signal_date=signal_date,
                    execute_date=next_session[signal_date],
                    security_id=str(row.security_id),
                    side=Side.SELL,
                    priority=-25_000,
                    reason=reason,
                )
            )
            exit_reasons["risk_off" if risk_off_exit else "score_or_rank"] += 1
        for row in ranked.loc[ranked["entry_eligible"]].itertuples(index=False):
            rank = int(row.daily_rank)
            recently_submitted[str(row.security_id)] = position
            orders.append(
                Order(
                    order_id=f"P5D:{signal_date.isoformat()}:R{rank:02d}:{row.security_id}",
                    signal_date=signal_date,
                    execute_date=next_session[signal_date],
                    security_id=str(row.security_id),
                    side=Side.BUY,
                    target_weight=config.base.target_weight,
                    priority=rank,
                    limit_price=Decimal(str(row.close)) * (Decimal("1") + config.base.entry_gap_cap),
                    max_holding_sessions=config.maximum_holding_sessions,
                    reason=f"SELECTIVE_{regime.upper()}_ENTRY",
                )
            )
            entry_orders[regime] += 1
    audit: dict[str, object] = {
        "orders": len(orders),
        "entry_orders_by_regime": entry_orders,
        "regime_signal_days": regime_days,
        "exit_orders_by_reason": exit_reasons,
        "minimum_required_holdings": 0,
        "average_cash_is_hard_gate": False,
    }
    return tuple(orders), audit
