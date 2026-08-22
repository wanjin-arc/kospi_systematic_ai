from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)

from kospi100_backtest.costs import CostSchedule
from kospi100_features.features import build_feature_matrix
from kospi100_features.labels import LABEL_COLUMN, attach_forward_label
from kospi100_multifactor.modeling import _preprocessor_state, _transform
from kospi100_ranking.data import SelectionBundle
from kospi100_ranking.modeling import fold_dates

from .config import AbsoluteAlphaConfig, MODEL_CONTRACT


NET_TARGET = "forward_cost_adjusted_excess_log_return_10"
POSITIVE_TARGET = "forward_positive_cost_adjusted_excess_10"


@dataclass(frozen=True)
class PreparedAbsoluteResearch:
    frame: pd.DataFrame
    audit: dict[str, object]


@dataclass(frozen=True)
class AbsoluteModelResult:
    predictions: pd.DataFrame
    metrics: pd.DataFrame
    fold_audit: pd.DataFrame


def _tax_rate(exit_dates: pd.Series, schedule: CostSchedule) -> pd.Series:
    cache: dict[object, float] = {}
    result = []
    for value in exit_dates:
        session = pd.Timestamp(value).date()
        if session not in cache:
            transaction, rural = schedule.rates_on(session)
            cache[session] = float(transaction + rural)
        result.append(cache[session])
    return pd.Series(result, index=exit_dates.index, dtype=float)


def attach_cost_adjusted_target(
    labeled: pd.DataFrame,
    config: AbsoluteAlphaConfig,
) -> tuple[pd.DataFrame, dict[str, object]]:
    work = labeled.copy()
    valid = work[LABEL_COLUMN].notna() & work["exit_date"].notna()
    if "date" in work:
        valid &= work["date"].between(
            pd.Timestamp(config.base.periods["train"].start),
            pd.Timestamp(config.base.maximum_permitted_date),
        )
    work["estimated_roundtrip_log_cost"] = np.nan
    work[NET_TARGET] = np.nan
    work[POSITIVE_TARGET] = pd.Series(pd.NA, index=work.index, dtype="Int64")
    schedule = CostSchedule.from_csv(config.base.tax_schedule_path)
    tax = _tax_rate(work.loc[valid, "exit_date"], schedule)
    commission = float(config.base.commission_rate)
    slippage = float(config.base.slippage_rate)
    net_factor = ((1.0 - slippage) * (1.0 - commission - tax)) / (
        (1.0 + slippage) * (1.0 + commission)
    )
    if (net_factor <= 0.0).any():
        raise ValueError("비용 조정 factor가 양수가 아닙니다")
    log_cost = -np.log(net_factor)
    work.loc[valid, "estimated_roundtrip_log_cost"] = log_cost
    work.loc[valid, NET_TARGET] = work.loc[valid, LABEL_COLUMN].astype(float) - log_cost
    work.loc[valid, POSITIVE_TARGET] = (work.loc[valid, NET_TARGET] > 0.0).astype(int)
    audit = {
        "gross_target": LABEL_COLUMN,
        "regression_target": NET_TARGET,
        "classification_target": POSITIVE_TARGET,
        "cross_sectional_target_transform": "none",
        "binary_threshold": 0.0,
        "commission_rate_per_side": commission,
        "slippage_rate_per_side": slippage,
        "exit_date_sell_tax_used": True,
        "target_rows": int(work[NET_TARGET].notna().sum()),
        "positive_target_rows": int(work[POSITIVE_TARGET].eq(1).sum()),
        "outside_research_period_rows_excluded": int(
            (work[LABEL_COLUMN].notna() & work["exit_date"].notna() & ~valid).sum()
        ),
        "entry_offset_sessions": 1,
        "exit_offset_sessions": 11,
    }
    return work, audit


def prepare_absolute_frame(
    bundle: SelectionBundle,
    config: AbsoluteAlphaConfig,
) -> PreparedAbsoluteResearch:
    features = build_feature_matrix(bundle.feature_panel, bundle.index, bundle.corporate_actions)
    labeled, label_audit = attach_forward_label(
        features.cross_sectional,
        bundle.full_history,
        bundle.index,
        bundle.corporate_actions,
    )
    labeled, target_audit = attach_cost_adjusted_target(labeled, config)
    missing_stock = set(config.base.stock_features) - set(labeled.columns)
    missing_regime = set(config.base.regime_features) - set(features.regime.columns)
    if missing_stock or missing_regime:
        raise ValueError(f"Phase 5E 입력 열 누락: stock={sorted(missing_stock)} regime={sorted(missing_regime)}")
    eligible = labeled.loc[
        labeled["phase4_eligible"]
        & labeled[NET_TARGET].notna()
        & labeled[POSITIVE_TARGET].notna()
    ].copy()
    counts = eligible.groupby("date", sort=False)["security_id"].transform("size")
    eligible = eligible.loc[counts >= config.base.minimum_cross_section].copy()
    rank_columns = []
    for name in config.base.stock_features:
        column = f"rank__{name}"
        eligible[column] = eligible.groupby("date", sort=False)[name].rank(method="average", pct=True)
        rank_columns.append(column)
    regime = features.regime[["date", *config.base.regime_features]].copy()
    eligible = eligible.merge(regime, on="date", how="left", validate="many_to_one")
    columns = [
        "date", "entry_date", "exit_date", "security_id", "membership_spell_id", "close",
        LABEL_COLUMN, "estimated_roundtrip_log_cost", NET_TARGET, POSITIVE_TARGET,
        *rank_columns, *config.base.regime_features,
    ]
    result = eligible[columns].sort_values(["date", "security_id"], kind="mergesort").reset_index(drop=True)
    if result.empty:
        raise ValueError("Phase 5E 연구 표본이 비었습니다")
    maximum = result["date"].max().date()
    if maximum > config.base.maximum_permitted_date:
        raise PermissionError("Phase 5E 연구 계산이 2021년을 넘었습니다")
    audit = {
        "research_rows": len(result),
        "research_dates": int(result["date"].nunique()),
        "minimum_signal_date": result["date"].min().date().isoformat(),
        "maximum_signal_date": maximum.isoformat(),
        "stock_feature_count": len(config.base.stock_features),
        "regime_feature_count": len(config.base.regime_features),
        "interaction_count": len(config.base.interactions),
        "market_state_hard_capacity_used": False,
        "daily_cross_sectional_target_rank_used": False,
        "future_bar_used_for_feature": False,
        "label_entry_after_signal": label_audit["entry_is_after_signal"],
        "label_exit_after_entry": label_audit["exit_is_after_entry"],
        "feature_audit": features.audit,
        "label_audit": label_audit,
        "target_audit": target_audit,
    }
    return PreparedAbsoluteResearch(result, audit)


def _fold_metrics(frame: pd.DataFrame, fold: str, config: AbsoluteAlphaConfig) -> dict[str, object]:
    y = frame[NET_TARGET].to_numpy(dtype=float)
    positive = frame[POSITIVE_TARGET].to_numpy(dtype=int)
    predicted = frame["predicted_net_excess"].to_numpy(dtype=float)
    probability = frame["positive_probability"].to_numpy(dtype=float)
    eligible = (
        (predicted >= config.entry_net_excess)
        & (probability >= config.entry_probability)
    )
    pearson = pd.Series(predicted).corr(pd.Series(y), method="pearson")
    spearman = pd.Series(predicted).corr(pd.Series(y), method="spearman")
    return {
        "model": MODEL_CONTRACT,
        "fold": fold,
        "validation_year": int(frame["date"].dt.year.iloc[0]),
        "rows": len(frame),
        "dates": int(frame["date"].nunique()),
        "target_positive_rate": float(np.mean(positive)),
        "predicted_positive_rate": float(np.mean(probability >= 0.5)),
        "mae": float(mean_absolute_error(y, predicted)),
        "rmse": float(np.sqrt(mean_squared_error(y, predicted))),
        "r2": float(r2_score(y, predicted)),
        "pearson": None if pd.isna(pearson) else float(pearson),
        "spearman": None if pd.isna(spearman) else float(spearman),
        "roc_auc": float(roc_auc_score(positive, probability)),
        "average_precision": float(average_precision_score(positive, probability)),
        "log_loss": float(log_loss(positive, probability, labels=[0, 1])),
        "brier": float(brier_score_loss(positive, probability)),
        "dual_gate_rows": int(eligible.sum()),
        "dual_gate_rate": float(np.mean(eligible)),
        "dual_gate_realized_mean_net_excess": float(np.mean(y[eligible])) if eligible.any() else None,
        "dual_gate_realized_positive_rate": float(np.mean(positive[eligible])) if eligible.any() else None,
    }


def evaluate_models(
    frame: pd.DataFrame,
    index: pd.DataFrame,
    config: AbsoluteAlphaConfig,
) -> AbsoluteModelResult:
    predictions = []
    metrics = []
    audits = []
    for fold in config.base.folds:
        train_dates, validation_dates = fold_dates(
            index, fold, config.base.purge_sessions, config.base.embargo_sessions
        )
        train = frame.loc[frame["date"].isin(train_dates)].copy()
        validation = frame.loc[frame["date"].isin(validation_dates)].copy()
        if train.empty or validation.empty or train["date"].max() >= validation["date"].min():
            raise ValueError(f"안전한 Phase 5E fold가 아닙니다: {fold.name}")
        state = _preprocessor_state(train, config.base)
        x_train, names = _transform(train, state, config.base)
        x_validation, validation_names = _transform(validation, state, config.base)
        if names != validation_names:
            raise AssertionError("Train/diagnostic 입력 순서가 다릅니다")
        y_regression = train[NET_TARGET].to_numpy(dtype=float)
        y_binary = train[POSITIVE_TARGET].to_numpy(dtype=int)
        if set(np.unique(y_binary)) != {0, 1}:
            raise ValueError(f"분류 Train에 두 클래스가 없습니다: {fold.name}")
        regressor = Ridge(alpha=config.ridge_alpha, fit_intercept=True).fit(x_train, y_regression)
        classifier = LogisticRegression(
            C=config.logistic_c,
            fit_intercept=True,
            max_iter=config.logistic_max_iter,
            solver="lbfgs",
            class_weight=None,
            random_state=config.base.random_seed,
        ).fit(x_train, y_binary)
        output_columns = [
            "date", "security_id", "membership_spell_id", "close", LABEL_COLUMN,
            NET_TARGET, POSITIVE_TARGET,
        ]
        output = validation[output_columns].copy()
        output["predicted_net_excess"] = regressor.predict(x_validation)
        output["positive_probability"] = classifier.predict_proba(x_validation)[:, 1]
        output["fold"] = fold.name
        output["model"] = MODEL_CONTRACT
        predictions.append(output)
        metrics.append(_fold_metrics(output, fold.name, config))
        audits.append({
            "model": MODEL_CONTRACT,
            "fold": fold.name,
            "train_min_date": state["fit_min_date"],
            "train_max_date": state["fit_max_date"],
            "train_rows": len(train),
            "validation_min_date": validation["date"].min().date().isoformat(),
            "validation_max_date": validation["date"].max().date().isoformat(),
            "validation_rows": len(validation),
            "input_columns": len(names),
            "purge_sessions": config.base.purge_sessions,
            "embargo_sessions": config.base.embargo_sessions,
            "preprocessing_fit_used_validation": False,
            "regression_fit_used_validation": False,
            "classification_fit_used_validation": False,
            "target_cross_sectional_rank_used": False,
            "adaptive_diagnostic_not_oos": True,
        })
    combined = pd.concat(predictions, ignore_index=True).sort_values(
        ["fold", "date", "security_id"], kind="mergesort"
    ).reset_index(drop=True)
    return AbsoluteModelResult(combined, pd.DataFrame(metrics), pd.DataFrame(audits))
