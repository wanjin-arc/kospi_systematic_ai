from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


MECHANICAL = "PIT_MECHANICAL_ADJUSTMENT"


@dataclass(frozen=True)
class FeatureResult:
    frame: pd.DataFrame
    audit: dict[str, object]


def mechanically_adjusted_close(
    panel: pd.DataFrame,
    actions: pd.DataFrame,
    *,
    action_cutoff: pd.Timestamp | None = None,
) -> pd.Series:
    """Return a split-continuous close series.

    The production calculation may include later mechanical split factors because
    every supported Phase-3 statistic is scale invariant. Before a future split,
    that factor multiplies the entire available history by the same constant and
    therefore cannot change close/SMA, return, gate, or rank results. Tests compare
    this representation with an explicit effective-as-of calculation.
    """

    adjusted = pd.to_numeric(panel["close"], errors="coerce").astype(float).copy()
    mechanical = actions.loc[actions["feature_handling"].eq(MECHANICAL)].copy()
    if action_cutoff is not None:
        mechanical = mechanical.loc[mechanical["feature_boundary_date"] <= action_cutoff]
    for action in mechanical.sort_values(["feature_boundary_date", "canonical_event_id"]).itertuples(index=False):
        boundary = pd.Timestamp(action.feature_boundary_date)
        factor = float(action.price_multiplier)
        if not np.isfinite(factor) or factor <= 0:
            raise ValueError(f"invalid mechanical price multiplier: {action.canonical_event_id}")
        mask = panel["security_id"].eq(action.security_id) & panel["date"].lt(boundary)
        adjusted.loc[mask] *= factor
    return adjusted


def _feature_segments(panel: pd.DataFrame, actions: pd.DataFrame) -> pd.Series:
    resets = actions.loc[actions["feature_handling"].astype(str).str.startswith("RESET_")].copy()
    output = pd.Series(0, index=panel.index, dtype="int64")
    boundary_map = {
        security_id: np.sort(group["feature_boundary_date"].dropna().to_numpy(dtype="datetime64[ns]"))
        for security_id, group in resets.groupby("security_id", sort=False)
    }
    for security_id, indices in panel.groupby("security_id", sort=False).groups.items():
        boundaries = boundary_map.get(security_id)
        if boundaries is None or len(boundaries) == 0:
            continue
        dates = panel.loc[indices, "date"].to_numpy(dtype="datetime64[ns]")
        output.loc[indices] = np.searchsorted(boundaries, dates, side="right")
    return output


def _corporate_action_blackout(panel: pd.DataFrame, actions: pd.DataFrame) -> tuple[pd.Series, int]:
    resets = actions.loc[actions["feature_handling"].astype(str).str.startswith("RESET_")].copy()
    blocked = pd.Series(False, index=panel.index, dtype=bool)
    permanent_windows: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
    for action in resets.sort_values(["security_id", "feature_boundary_date", "canonical_event_id"]).itertuples(index=False):
        boundary = pd.Timestamp(action.feature_boundary_date)
        filing = pd.Timestamp(action.first_filing_date)
        if pd.isna(boundary) or pd.isna(filing):
            raise ValueError(f"reset action lacks a public filing or boundary: {action.canonical_event_id}")
        pending = "PENDING" in str(action.portfolio_terms_status)
        end = panel["date"].max() if pending else boundary
        mask = panel["security_id"].eq(action.security_id) & panel["date"].ge(filing) & panel["date"].le(end)
        blocked.loc[mask] = True
        if pending:
            permanent_windows.setdefault(action.security_id, []).append((filing, end))

    late_notice_count = 0
    late = resets.loc[resets["first_filing_date"] >= resets["feature_boundary_date"]]
    for action in late.itertuples(index=False):
        boundary = pd.Timestamp(action.feature_boundary_date)
        protected = any(start < boundary <= end for start, end in permanent_windows.get(action.security_id, []))
        if not protected:
            raise ValueError(f"late-notice reset lacks a prior permanent block: {action.canonical_event_id}")
        late_notice_count += 1
    return blocked, late_notice_count


def build_features(
    panel: pd.DataFrame,
    index: pd.DataFrame,
    actions: pd.DataFrame,
    *,
    moving_average_sessions: int = 200,
    momentum_sessions: int = 126,
) -> FeatureResult:
    required = {"date", "security_id", "close", "rank_eligible", "tradable", "is_member"}
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"feature panel missing columns: {sorted(missing)}")

    work = panel.copy().sort_values(["security_id", "date"], kind="mergesort").reset_index(drop=True)
    work["feature_segment"] = _feature_segments(work, actions)
    work["feature_close"] = mechanically_adjusted_close(work, actions)
    work.loc[~np.isfinite(work["feature_close"]) | work["feature_close"].le(0), "feature_close"] = np.nan
    group_keys = [work["security_id"], work["feature_segment"]]
    work["feature_close_ffill"] = work.groupby(group_keys, sort=False)["feature_close"].ffill()
    work["sma200"] = work.groupby(group_keys, sort=False)["feature_close_ffill"].transform(
        lambda series: series.rolling(moving_average_sessions, min_periods=moving_average_sessions).mean()
    )
    lagged = work.groupby(group_keys, sort=False)["feature_close_ffill"].shift(momentum_sessions)
    work["stock_return126"] = work["feature_close_ffill"] / lagged - 1.0

    benchmark = index[["date", "close"]].copy().sort_values("date", kind="mergesort")
    benchmark["index_return126"] = benchmark["close"] / benchmark["close"].shift(momentum_sessions) - 1.0
    work = work.merge(benchmark[["date", "index_return126"]], on="date", how="left", validate="many_to_one")
    work["excess_return126"] = work["stock_return126"] - work["index_return126"]
    work["ca_entry_blocked"], late_notice_count = _corporate_action_blackout(work, actions)
    work["absolute_trend_pass"] = work["feature_close"] > work["sma200"]
    work["relative_momentum_pass"] = work["excess_return126"] > 0.0
    work["baseline_candidate"] = (
        work["rank_eligible"]
        & work["tradable"]
        & work["is_member"]
        & ~work["ca_entry_blocked"]
        & work["absolute_trend_pass"]
        & work["relative_momentum_pass"]
        & work["excess_return126"].notna()
    )

    candidate = work.loc[work["baseline_candidate"]]
    if not candidate["rank_eligible"].all() or not candidate["tradable"].all() or not candidate["is_member"].all():
        raise AssertionError("candidate eligibility invariant failed")
    if candidate["ca_entry_blocked"].any():
        raise AssertionError("corporate-action blackout invariant failed")

    mechanical = actions.loc[actions["feature_handling"].eq(MECHANICAL)]
    audit = {
        "feature_rows": int(len(work)),
        "candidate_rows": int(work["baseline_candidate"].sum()),
        "candidate_dates": int(candidate["date"].nunique()),
        "mechanical_actions": int(len(mechanical)),
        "feature_reset_actions": int(actions["feature_handling"].astype(str).str.startswith("RESET_").sum()),
        "corporate_action_blocked_rows": int(work["ca_entry_blocked"].sum()),
        "late_notice_actions_protected_by_prior_permanent_block": late_notice_count,
        "scale_invariant_features_only": True,
        "rank_eligible_only": True,
        "same_day_execution": False,
    }
    return FeatureResult(work, audit)
