from __future__ import annotations

import json
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import FeatureResearchConfig
from .labels import LABEL_COLUMN


@dataclass(frozen=True)
class EvaluationResult:
    metrics: pd.DataFrame
    daily_ic: pd.DataFrame
    redundancy: pd.DataFrame
    decisions: pd.DataFrame
    audit: dict[str, object]


def _purged_period_dates(index: pd.DataFrame, start: object, end: object, purge: int) -> set[pd.Timestamp]:
    dates = index.loc[index["date"].between(pd.Timestamp(start), pd.Timestamp(end)), "date"].sort_values().tolist()
    if len(dates) <= purge:
        raise ValueError("기간 길이가 purge 길이보다 짧습니다")
    return set(dates[:-purge])


def _forward_embargo_dates(
    index: pd.DataFrame,
    end: object,
    embargo: int,
    *,
    later_training_exists: bool,
) -> set[pd.Timestamp]:
    """Return dates forbidden from re-entering a later training block.

    Phase 4 has a single forward Train -> Validation screen and no later training
    block, so the effective set is empty. Keeping this explicit makes the frozen
    20-session embargo auditable and prevents it from silently becoming a no-op in
    a future workflow that does have a later fit.
    """

    if embargo < 0:
        raise ValueError("embargo는 음수일 수 없습니다")
    if not later_training_exists or embargo == 0:
        return set()
    dates = index.loc[index["date"].gt(pd.Timestamp(end)), "date"].sort_values().head(embargo)
    return set(dates)


def _daily_rank_ic(frame: pd.DataFrame, feature: str, minimum_cross_section: int) -> pd.Series:
    pair = frame[["date", feature, LABEL_COLUMN]].dropna().copy()
    if pair.empty:
        return pd.Series(dtype=float, name=feature)
    pair["x"] = pair.groupby("date", sort=False)[feature].rank(method="average", pct=True)
    pair["y"] = pair.groupby("date", sort=False)[LABEL_COLUMN].rank(method="average", pct=True)
    grouped = pair.groupby("date", sort=True)
    stats = grouped.agg(
        n=("x", "size"),
        sx=("x", "sum"),
        sy=("y", "sum"),
        sxx=("x", lambda values: float(np.square(values).sum())),
        syy=("y", lambda values: float(np.square(values).sum())),
    )
    pair["xy"] = pair["x"] * pair["y"]
    stats["sxy"] = grouped["xy"].sum()
    numerator = stats["sxy"] - stats["sx"] * stats["sy"] / stats["n"]
    variance_x = (stats["sxx"] - stats["sx"] ** 2 / stats["n"]).clip(lower=0.0)
    variance_y = (stats["syy"] - stats["sy"] ** 2 / stats["n"]).clip(lower=0.0)
    denominator = np.sqrt(variance_x * variance_y)
    result = numerator / denominator.where(denominator > 0)
    result = result.where(stats["n"] >= minimum_cross_section).dropna()
    result.name = feature
    return result


def _daily_quintile_spread(frame: pd.DataFrame, feature: str, minimum_cross_section: int) -> pd.Series:
    pair = frame[["date", feature, LABEL_COLUMN]].dropna().copy()
    pair["rank"] = pair.groupby("date", sort=False)[feature].rank(method="average", pct=True)
    counts = pair.groupby("date")[feature].size()
    top = pair.loc[pair["rank"] >= 0.8].groupby("date")[LABEL_COLUMN].mean()
    bottom = pair.loc[pair["rank"] <= 0.2].groupby("date")[LABEL_COLUMN].mean()
    spread = (top - bottom).where(counts >= minimum_cross_section).dropna()
    return spread


def _hac_tstat(values: pd.Series, lag: int) -> float | None:
    array = values.dropna().to_numpy(dtype=float)
    n = len(array)
    if n < max(30, lag + 2):
        return None
    demeaned = array - array.mean()
    long_run = float(np.dot(demeaned, demeaned) / n)
    for offset in range(1, min(lag, n - 1) + 1):
        covariance = float(np.dot(demeaned[offset:], demeaned[:-offset]) / n)
        long_run += 2.0 * (1.0 - offset / (lag + 1.0)) * covariance
    if long_run <= 0:
        return None
    return float(array.mean() / math.sqrt(long_run / n))


def _period_metrics(
    frame: pd.DataFrame,
    feature: str,
    period: str,
    config: FeatureResearchConfig,
) -> tuple[dict[str, object], pd.Series]:
    base = frame.loc[frame["period"].eq(period) & frame["phase4_eligible"] & frame[LABEL_COLUMN].notna()]
    available = base[feature].notna()
    ic = _daily_rank_ic(base, feature, config.minimum_cross_section)
    spread = _daily_quintile_spread(base, feature, config.minimum_cross_section)
    annual = ic.groupby(ic.index.year).mean() if not ic.empty else pd.Series(dtype=float)
    return {
        "feature_id": feature,
        "period": period,
        "eligible_label_rows": int(len(base)),
        "available_rows": int(available.sum()),
        "coverage": float(available.mean()) if len(base) else 0.0,
        "ic_days": int(len(ic)),
        "mean_daily_spearman_ic": float(ic.mean()) if not ic.empty else None,
        "median_daily_spearman_ic": float(ic.median()) if not ic.empty else None,
        "ic_positive_day_ratio": float((ic > 0).mean()) if not ic.empty else None,
        "hac_t_stat": _hac_tstat(ic, config.hac_lag_sessions),
        "mean_top_bottom_label_spread": float(spread.mean()) if not spread.empty else None,
        "positive_years": int((annual > 0).sum()),
        "year_count": int(len(annual)),
        "annual_ic_json": json.dumps({str(year): float(value) for year, value in annual.items()}, sort_keys=True),
    }, ic


def evaluate_features(
    labeled: pd.DataFrame,
    index: pd.DataFrame,
    config: FeatureResearchConfig,
) -> EvaluationResult:
    frame = labeled.copy()
    frame["period"] = ""
    partition_dates: dict[str, set[pd.Timestamp]] = {}
    for name, period in config.periods.items():
        dates = _purged_period_dates(index, period.start, period.end, config.purge_sessions)
        partition_dates[name] = dates
        frame.loc[frame["date"].isin(dates), "period"] = name
    embargo_dates = _forward_embargo_dates(
        index,
        config.periods["validation"].end,
        config.embargo_sessions,
        later_training_exists=False,
    )
    if frame.loc[frame["period"].ne(""), "date"].max() > pd.Timestamp("2021-12-31"):
        raise PermissionError("Phase 4 평가가 검증 구간을 초과했습니다")

    rows: list[dict[str, object]] = []
    daily: dict[str, pd.Series] = {}
    feature_ids = [item.feature_id for item in config.features]
    for feature in feature_ids:
        for period in ("train", "validation"):
            metrics, ic = _period_metrics(frame, feature, period, config)
            rows.append(metrics)
            daily[f"{feature}__{period}"] = ic
    metrics_frame = pd.DataFrame(rows)
    daily_frame = pd.DataFrame(daily).sort_index()
    daily_frame.index.name = "date"

    train = frame.loc[frame["period"].eq("train") & frame["phase4_eligible"] & frame[LABEL_COLUMN].notna()]
    ranked = train[["date"] + feature_ids].copy()
    ranked[feature_ids] = ranked.groupby("date", sort=False)[feature_ids].rank(method="average", pct=True)
    redundancy = ranked[feature_ids].corr(method="pearson")

    lookup = metrics_frame.set_index(["feature_id", "period"])
    prelim: list[str] = []
    decision_rows: list[dict[str, object]] = []
    for definition in config.features:
        train_metric = lookup.loc[(definition.feature_id, "train")]
        validation_metric = lookup.loc[(definition.feature_id, "validation")]
        coverage = min(float(train_metric["coverage"]), float(validation_metric["coverage"]))
        if coverage < config.minimum_coverage:
            decision = "폐기_결측과다"
            reason = f"Train/Validation 최소 coverage {coverage:.3f} < {config.minimum_coverage:.2f}"
        elif not (float(train_metric["mean_daily_spearman_ic"] or 0) > 0):
            decision = "보류_학습방향불일치"
            reason = "Train 평균 IC가 사전 기대 방향과 일치하지 않음"
        elif not (float(validation_metric["mean_daily_spearman_ic"] or 0) > 0):
            decision = "보류_검증방향불일치"
            reason = "Validation 평균 IC가 사전 기대 방향과 일치하지 않음"
        elif validation_metric["hac_t_stat"] is None or float(validation_metric["hac_t_stat"]) < config.minimum_validation_hac_t:
            decision = "보류_검증불안정"
            reason = f"Validation HAC t값이 {config.minimum_validation_hac_t:.1f} 미만"
        elif int(validation_metric["positive_years"]) < config.minimum_positive_validation_years:
            decision = "보류_연도불안정"
            reason = "Validation 양(+)의 연도 수가 사전 기준 미달"
        else:
            decision = "중복검사대상"
            reason = "방향·안정성·coverage 기준 통과"
            prelim.append(definition.feature_id)
        decision_rows.append(
            {
                "feature_id": definition.feature_id,
                "family": definition.family,
                "preliminary_decision": decision,
                "decision": decision,
                "reason": reason,
                "redundant_with": "",
            }
        )

    validation_ic = {
        feature: float(lookup.loc[(feature, "validation"), "mean_daily_spearman_ic"])
        for feature in prelim
    }
    accepted: list[str] = []
    decisions_by_id = {row["feature_id"]: row for row in decision_rows}
    for feature in sorted(prelim, key=lambda name: (-validation_ic[name], name)):
        redundant_with = next(
            (
                kept
                for kept in accepted
                if pd.notna(redundancy.loc[feature, kept])
                and abs(float(redundancy.loc[feature, kept])) >= config.redundancy_threshold
            ),
            None,
        )
        if redundant_with is None:
            accepted.append(feature)
            decisions_by_id[feature]["decision"] = "채택_Phase5후보"
            decisions_by_id[feature]["reason"] = "사전 방향·안정성·coverage·중복 기준 통과"
        else:
            decisions_by_id[feature]["decision"] = "보류_중복"
            decisions_by_id[feature]["reason"] = f"더 강한 채택 변수와 Train 횡단면 순위상관 절댓값이 {config.redundancy_threshold:.2f} 이상"
            decisions_by_id[feature]["redundant_with"] = redundant_with
    decisions = pd.DataFrame(decision_rows)
    evaluated = frame.loc[frame["period"].ne("") & frame["phase4_eligible"] & frame[LABEL_COLUMN].notna()]
    audit = {
        "train_dates_after_purge": len(partition_dates["train"]),
        "validation_dates_after_purge": len(partition_dates["validation"]),
        "purge_sessions": config.purge_sessions,
        "embargo_sessions": config.embargo_sessions,
        "embargo_later_training_exists": False,
        "embargoed_dates": len(embargo_dates),
        "development_test_accessed": False,
        "final_oos_accessed": False,
        "model_trained": False,
        "portfolio_backtest_run": False,
        "accepted_features": accepted,
        "minimum_evaluated_signal_date": evaluated["date"].min().date().isoformat() if not evaluated.empty else None,
        "maximum_evaluated_signal_date": evaluated["date"].max().date().isoformat() if not evaluated.empty else None,
        "evaluated_signal_rows": int(len(evaluated)),
    }
    return EvaluationResult(metrics_frame, daily_frame, redundancy, decisions, audit)
