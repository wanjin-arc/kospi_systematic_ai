from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from kospi100_baseline.features import MECHANICAL, _corporate_action_blackout, _feature_segments


@dataclass(frozen=True)
class FeatureMatrixResult:
    cross_sectional: pd.DataFrame
    regime: pd.DataFrame
    audit: dict[str, object]


def _adjust_price_column(panel: pd.DataFrame, actions: pd.DataFrame, column: str) -> pd.Series:
    adjusted = pd.to_numeric(panel[column], errors="coerce").astype(float).copy()
    mechanical = actions.loc[actions["feature_handling"].eq(MECHANICAL)]
    for action in mechanical.sort_values(["feature_boundary_date", "canonical_event_id"]).itertuples(index=False):
        factor = float(action.price_multiplier)
        if not np.isfinite(factor) or factor <= 0:
            raise ValueError(f"잘못된 가격 조정계수: {action.canonical_event_id}")
        mask = panel["security_id"].eq(action.security_id) & panel["date"].lt(action.feature_boundary_date)
        adjusted.loc[mask] *= factor
    adjusted.loc[~np.isfinite(adjusted) | adjusted.le(0)] = np.nan
    return adjusted


def _adjust_volume(panel: pd.DataFrame, actions: pd.DataFrame) -> pd.Series:
    adjusted = pd.to_numeric(panel["feature_volume"], errors="coerce").astype(float).copy()
    mechanical = actions.loc[actions["feature_handling"].eq(MECHANICAL)]
    for action in mechanical.sort_values(["feature_boundary_date", "canonical_event_id"]).itertuples(index=False):
        factor = float(action.share_multiplier)
        if not np.isfinite(factor) or factor <= 0:
            raise ValueError(f"잘못된 거래량 조정계수: {action.canonical_event_id}")
        mask = panel["security_id"].eq(action.security_id) & panel["date"].lt(action.feature_boundary_date)
        adjusted.loc[mask] *= factor
    adjusted.loc[~np.isfinite(adjusted) | adjusted.lt(0)] = np.nan
    return adjusted


def _group_keys(frame: pd.DataFrame) -> list[pd.Series]:
    return [frame["security_id"], frame["feature_segment"]]


def _lag(frame: pd.DataFrame, column: str, sessions: int) -> pd.Series:
    keys = _group_keys(frame)
    shifted = frame.groupby(keys, sort=False)[column].shift(sessions)
    shifted_index = frame.groupby(keys, sort=False)["session_index"].shift(sessions)
    return shifted.where(frame["session_index"] - shifted_index == sessions)


def _rolling(frame: pd.DataFrame, column: str, sessions: int, operation: str) -> pd.Series:
    keys = _group_keys(frame)
    grouped = frame.groupby(keys, sort=False)[column]
    if operation == "mean":
        result = grouped.transform(lambda values: values.rolling(sessions, min_periods=sessions).mean())
    elif operation == "std":
        result = grouped.transform(lambda values: values.rolling(sessions, min_periods=sessions).std(ddof=1))
    elif operation == "max":
        result = grouped.transform(lambda values: values.rolling(sessions, min_periods=sessions).max())
    elif operation == "count":
        result = grouped.transform(lambda values: values.rolling(sessions, min_periods=sessions).count())
    else:
        raise ValueError(operation)
    first_index = frame.groupby(keys, sort=False)["session_index"].shift(sessions - 1)
    return result.where(frame["session_index"] - first_index == sessions - 1)


def _index_features(index: pd.DataFrame) -> pd.DataFrame:
    work = index[["date", "close"]].copy().sort_values("date", kind="mergesort")
    work["index_log_return1"] = np.log(work["close"] / work["close"].shift(1))
    for horizon in (20, 63, 126):
        work[f"index_return_{horizon}"] = work["close"] / work["close"].shift(horizon) - 1.0
    work["index_sma200"] = work["close"].rolling(200, min_periods=200).mean()
    work["index_trend_200"] = work["close"] / work["index_sma200"] - 1.0
    work["index_momentum_63"] = work["index_return_63"]
    work["index_low_volatility_20"] = -work["index_log_return1"].rolling(20, min_periods=20).std(ddof=1) * math.sqrt(252)
    return work


def build_feature_matrix(panel: pd.DataFrame, index: pd.DataFrame, actions: pd.DataFrame) -> FeatureMatrixResult:
    required = {
        "date", "security_id", "open", "high", "low", "close", "feature_volume",
        "feature_trading_value", "rank_eligible", "tradable", "is_member", "eligible_new_entry",
    }
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"Feature panel 필수 열 누락: {sorted(missing)}")

    work = panel.copy().sort_values(["security_id", "date"], kind="mergesort").reset_index(drop=True)
    session_map = pd.Series(np.arange(len(index)), index=index.sort_values("date")["date"]).to_dict()
    work["session_index"] = work["date"].map(session_map)
    work["feature_segment"] = _feature_segments(work, actions)
    work["ca_entry_blocked"], late_notice_count = _corporate_action_blackout(work, actions)
    for column in ("open", "high", "low", "close"):
        work[f"adjusted_{column}"] = _adjust_price_column(work, actions, column)
    work["adjusted_volume"] = _adjust_volume(work, actions)
    work["adjusted_trading_value"] = pd.to_numeric(work["feature_trading_value"], errors="coerce")
    work.loc[~np.isfinite(work["adjusted_trading_value"]) | work["adjusted_trading_value"].lt(0), "adjusted_trading_value"] = np.nan

    keys = _group_keys(work)
    work["feature_close"] = work["adjusted_close"]
    lag1 = _lag(work, "feature_close", 1)
    work["log_return1"] = np.log(work["feature_close"] / lag1)
    returns: dict[int, pd.Series] = {}
    for horizon in (5, 20, 63, 126, 252):
        lagged = _lag(work, "feature_close", horizon)
        complete_window = _rolling(work, "feature_close", horizon + 1, "count").eq(horizon + 1)
        returns[horizon] = (work["feature_close"] / lagged - 1.0).where(complete_window)
        work[f"return_{horizon}"] = returns[horizon]

    for horizon in (20, 60, 200):
        work[f"sma_{horizon}"] = _rolling(work, "feature_close", horizon, "mean")
    work["rolling_high_252"] = _rolling(work, "feature_close", 252, "max")
    work["volatility_20"] = _rolling(work, "log_return1", 20, "std") * math.sqrt(252)
    work["downside_square"] = np.minimum(work["log_return1"], 0.0) ** 2
    work["downside_volatility_20"] = np.sqrt(_rolling(work, "downside_square", 20, "mean")) * math.sqrt(252)
    prev_close = _lag(work, "feature_close", 1)
    work["true_range"] = pd.concat(
        [
            work["adjusted_high"] - work["adjusted_low"],
            (work["adjusted_high"] - prev_close).abs(),
            (work["adjusted_low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1, skipna=False)
    work["atr_20"] = _rolling(work, "true_range", 20, "mean")
    for horizon in (5, 20):
        work[f"volume_mean_{horizon}"] = _rolling(work, "adjusted_volume", horizon, "mean")
        work[f"trading_value_mean_{horizon}"] = _rolling(work, "adjusted_trading_value", horizon, "mean")
    scaled_value = work["adjusted_trading_value"] / 1_000_000_000.0
    work["illiquidity_daily"] = work["log_return1"].abs() / scaled_value.where(scaled_value > 0)
    work["illiquidity_20"] = _rolling(work, "illiquidity_daily", 20, "mean")

    index_work = _index_features(index)
    work = work.merge(
        index_work[["date", "index_return_20", "index_return_63", "index_return_126"]],
        on="date",
        how="left",
        validate="many_to_one",
    )
    work["reversal_5"] = -work["return_5"]
    for horizon in (20, 63, 126, 252):
        work[f"momentum_{horizon}"] = work[f"return_{horizon}"]
    for horizon in (20, 63, 126):
        work[f"excess_momentum_{horizon}"] = work[f"return_{horizon}"] - work[f"index_return_{horizon}"]
    work["trend_close_sma20"] = work["feature_close"] / work["sma_20"] - 1.0
    work["trend_close_sma60"] = work["feature_close"] / work["sma_60"] - 1.0
    work["trend_close_sma200"] = work["feature_close"] / work["sma_200"] - 1.0
    work["trend_sma20_sma60"] = work["sma_20"] / work["sma_60"] - 1.0
    work["high_proximity_252"] = work["feature_close"] / work["rolling_high_252"] - 1.0
    work["low_volatility_20"] = -work["volatility_20"]
    work["low_downside_volatility_20"] = -work["downside_volatility_20"]
    work["low_atr_20"] = -work["atr_20"] / work["feature_close"]
    work["risk_adjusted_momentum_63"] = work["return_63"] / work["volatility_20"].where(work["volatility_20"] > 0)
    work["volume_confirmation_5_20"] = work["volume_mean_5"] / work["volume_mean_20"].where(work["volume_mean_20"] > 0) - 1.0
    work["trading_value_confirmation_5_20"] = work["trading_value_mean_5"] / work["trading_value_mean_20"].where(work["trading_value_mean_20"] > 0) - 1.0
    work["liquidity_20"] = np.log1p(work["trading_value_mean_20"])
    work["low_illiquidity_20"] = -work["illiquidity_20"]
    work["phase4_eligible"] = (
        work["rank_eligible"]
        & work["tradable"]
        & work["is_member"]
        & work["eligible_new_entry"]
        & ~work["ca_entry_blocked"]
    )

    breadth_source = work.loc[work["is_member"] & work["eligible_new_entry"]].copy()
    breadth_source["above_sma200"] = (breadth_source["feature_close"] > breadth_source["sma_200"]).fillna(False)
    breadth_source["positive_momentum20"] = (breadth_source["return_20"] > 0).fillna(False)
    breadth = breadth_source.groupby("date", sort=True).agg(
        breadth_above_sma200=("above_sma200", "mean"),
        breadth_positive_momentum20=("positive_momentum20", "mean"),
        breadth_member_count=("security_id", "nunique"),
        breadth_sma200_valid_count=("sma_200", "count"),
        breadth_momentum20_valid_count=("return_20", "count"),
    ).reset_index()
    regime = index_work.merge(breadth, on="date", how="left", validate="one_to_one")
    regime["breadth_sma200_coverage"] = regime["breadth_sma200_valid_count"] / regime["breadth_member_count"]
    regime["breadth_momentum20_coverage"] = regime["breadth_momentum20_valid_count"] / regime["breadth_member_count"]

    audit = {
        "rows": int(len(work)),
        "eligible_rows": int(work["phase4_eligible"].sum()),
        "eligible_dates": int(work.loc[work["phase4_eligible"], "date"].nunique()),
        "maximum_date": work["date"].max().date().isoformat(),
        "mechanical_actions": int(actions["feature_handling"].eq(MECHANICAL).sum()),
        "reset_actions": int(actions["feature_handling"].astype(str).str.startswith("RESET_").sum()),
        "ca_blocked_rows": int(work["ca_entry_blocked"].sum()),
        "late_notice_actions_protected": late_notice_count,
        "raw_ohlcv_overwritten": False,
        "future_bar_used": False,
        "regime_rows": int(len(regime)),
    }
    return FeatureMatrixResult(work, regime, audit)
