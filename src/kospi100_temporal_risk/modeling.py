from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, IsolationForest
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from kospi100_absolute_alpha.modeling import NET_TARGET, attach_cost_adjusted_target
from kospi100_features.features import build_feature_matrix
from kospi100_features.labels import LABEL_COLUMN, attach_forward_label
from kospi100_ranking.data import SelectionBundle
from kospi100_ranking.modeling import fold_dates

from .config import MODEL_CONTRACT, TemporalRiskConfig


@dataclass(frozen=True)
class PreparedTemporalResearch:
    frame: pd.DataFrame
    model_features: tuple[str, ...]
    market_features: tuple[str, ...]
    audit: dict[str, object]


@dataclass(frozen=True)
class TemporalModelResult:
    predictions: pd.DataFrame
    metrics: pd.DataFrame
    fold_audit: pd.DataFrame


def _session_positions(index: pd.DataFrame) -> dict[pd.Timestamp, int]:
    sessions = pd.to_datetime(index["date"], errors="raise").drop_duplicates().sort_values()
    return {pd.Timestamp(value): position for position, value in enumerate(sessions)}


def add_stock_temporal_features(
    frame: pd.DataFrame,
    stock_features: tuple[str, ...],
    session_positions: dict[pd.Timestamp, int],
    window: int = 20,
) -> tuple[pd.DataFrame, tuple[str, ...], dict[str, object]]:
    work = frame.copy()
    work["date"] = pd.to_datetime(work["date"], errors="raise")
    work["_session_position"] = work["date"].map(session_positions)
    if work["_session_position"].isna().any():
        raise ValueError("종목 Feature 날짜가 거래소 세션에 없습니다")
    work = work.sort_values(
        ["security_id", "membership_spell_id", "date"], kind="mergesort"
    ).reset_index(drop=True)
    keys = ["security_id", "membership_spell_id"]
    gap = work.groupby(keys, sort=False)["_session_position"].diff().ne(1)
    work["_temporal_segment"] = gap.groupby([work[key] for key in keys], sort=False).cumsum()
    segment_keys = [*keys, "_temporal_segment"]
    names: list[str] = []
    for feature in stock_features:
        source = f"rank__{feature}"
        if source not in work:
            raise ValueError(f"종목 rank Feature가 없습니다: {source}")
        grouped = work.groupby(segment_keys, sort=False)[source]
        level = f"stock_level__{feature}"
        delta = f"stock_delta5__{feature}"
        mean = f"stock_mean20__{feature}"
        std = f"stock_std20__{feature}"
        persistence = f"stock_persistence20__{feature}"
        work[level] = work[source].astype(float)
        work[delta] = grouped.diff(5)
        work[mean] = grouped.transform(lambda values: values.rolling(window, min_periods=window).mean())
        work[std] = grouped.transform(
            lambda values: values.rolling(window, min_periods=window).std(ddof=0)
        )
        work[persistence] = grouped.transform(
            lambda values: values.gt(0.5).astype(float).rolling(window, min_periods=window).mean()
        )
        names.extend((level, delta, mean, std, persistence))
    complete = work[list(names)].notna().all(axis=1)
    audit = {
        "input_rows": len(work),
        "complete_temporal_rows": int(complete.sum()),
        "warmup_or_gap_rows_removed": int((~complete).sum()),
        "temporal_segments": int(work[segment_keys].drop_duplicates().shape[0]),
        "stock_base_features": len(stock_features),
        "stock_temporal_features": len(names),
        "delta_sessions": 5,
        "rolling_sessions": window,
        "membership_spell_reset": True,
        "exchange_session_gap_reset": True,
        "future_rows_used": False,
    }
    return work.loc[complete].copy(), tuple(names), audit


def add_regime_temporal_features(
    regime: pd.DataFrame,
    regime_features: tuple[str, ...],
    session_positions: dict[pd.Timestamp, int],
    window: int = 20,
) -> tuple[pd.DataFrame, tuple[str, ...], dict[str, object]]:
    work = regime[["date", *regime_features]].copy()
    work["date"] = pd.to_datetime(work["date"], errors="raise")
    work["_session_position"] = work["date"].map(session_positions)
    if work["_session_position"].isna().any() or work["date"].duplicated().any():
        raise ValueError("시장 Feature 날짜 경계가 올바르지 않습니다")
    work = work.sort_values("date", kind="mergesort").reset_index(drop=True)
    work["_regime_segment"] = work["_session_position"].diff().ne(1).cumsum()
    names: list[str] = []
    for feature in regime_features:
        grouped = work.groupby("_regime_segment", sort=False)[feature]
        level = f"market_level__{feature}"
        delta = f"market_delta5__{feature}"
        std = f"market_std20__{feature}"
        work[level] = work[feature].astype(float)
        work[delta] = grouped.diff(5)
        work[std] = grouped.transform(
            lambda values: values.rolling(window, min_periods=window).std(ddof=0)
        )
        names.extend((level, delta, std))
    complete = work[list(names)].notna().all(axis=1)
    audit = {
        "input_dates": len(work),
        "complete_temporal_dates": int(complete.sum()),
        "warmup_or_gap_dates_removed": int((~complete).sum()),
        "regime_segments": int(work["_regime_segment"].nunique()),
        "regime_base_features": len(regime_features),
        "regime_temporal_features": len(names),
        "delta_sessions": 5,
        "rolling_sessions": window,
        "exchange_session_gap_reset": True,
        "future_rows_used": False,
    }
    return work.loc[complete, ["date", *names]].copy(), tuple(names), audit


def prepare_temporal_frame(
    bundle: SelectionBundle,
    config: TemporalRiskConfig,
) -> PreparedTemporalResearch:
    features = build_feature_matrix(bundle.feature_panel, bundle.index, bundle.corporate_actions)
    labeled, label_audit = attach_forward_label(
        features.cross_sectional, bundle.full_history, bundle.index, bundle.corporate_actions
    )
    labeled, target_audit = attach_cost_adjusted_target(labeled, config)  # type: ignore[arg-type]
    missing_stock = set(config.stock_features) - set(labeled.columns)
    missing_regime = set(config.regime_features) - set(features.regime.columns)
    if missing_stock or missing_regime:
        raise ValueError(f"Phase 5F 입력 열 누락: stock={sorted(missing_stock)} regime={sorted(missing_regime)}")
    eligible = labeled.loc[labeled["phase4_eligible"] & labeled[NET_TARGET].notna()].copy()
    counts = eligible.groupby("date", sort=False)["security_id"].transform("size")
    eligible = eligible.loc[counts >= config.base.minimum_cross_section].copy()
    for name in config.stock_features:
        eligible[f"rank__{name}"] = eligible.groupby("date", sort=False)[name].rank(
            method="average", pct=True
        )
    positions = _session_positions(bundle.index)
    stock, stock_names, stock_audit = add_stock_temporal_features(
        eligible, config.stock_features, positions, config.temporal_sessions
    )
    market, market_names, market_audit = add_regime_temporal_features(
        features.regime, config.regime_features, positions, config.temporal_sessions
    )
    result = stock.merge(market, on="date", how="inner", validate="many_to_one")
    columns = [
        "date", "entry_date", "exit_date", "security_id", "membership_spell_id", "close",
        LABEL_COLUMN, "estimated_roundtrip_log_cost", NET_TARGET, *stock_names, *market_names,
    ]
    result = result[columns].sort_values(["date", "security_id"], kind="mergesort").reset_index(drop=True)
    if result.empty:
        raise ValueError("Phase 5F 연구 표본이 비었습니다")
    if result["date"].max().date() > config.base.maximum_permitted_date:
        raise PermissionError("Phase 5F 연구 계산이 2021년을 넘었습니다")
    audit = {
        "research_rows": len(result),
        "research_dates": int(result["date"].nunique()),
        "minimum_signal_date": result["date"].min().date().isoformat(),
        "maximum_signal_date": result["date"].max().date().isoformat(),
        "model_feature_count": len(stock_names) + len(market_names),
        "stock_temporal_audit": stock_audit,
        "market_temporal_audit": market_audit,
        "daily_cross_sectional_target_rank_used": False,
        "minute_data_used": False,
        "future_bar_used_for_feature": False,
        "label_entry_after_signal": label_audit["entry_is_after_signal"],
        "label_exit_after_entry": label_audit["exit_is_after_entry"],
        "feature_audit": features.audit,
        "label_audit": label_audit,
        "target_audit": target_audit,
    }
    return PreparedTemporalResearch(result, (*stock_names, *market_names), market_names, audit)


def _fill_state(train: pd.DataFrame, feature_names: tuple[str, ...]) -> dict[str, object]:
    medians = train[list(feature_names)].median().fillna(0.0)
    return {
        "medians": {name: float(value) for name, value in medians.items()},
        "fit_min_date": train["date"].min().date().isoformat(),
        "fit_max_date": train["date"].max().date().isoformat(),
        "fit_rows": len(train),
    }


def _matrix(frame: pd.DataFrame, names: tuple[str, ...], state: dict[str, object]) -> np.ndarray:
    medians = pd.Series(state["medians"], dtype=float)
    values = frame[list(names)].astype(float).fillna(medians).to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Train-only 결측 대체 후 비유한 값이 남았습니다")
    return values


def _regressor(config: TemporalRiskConfig, loss: str) -> HistGradientBoostingRegressor:
    kwargs: dict[str, object] = {"loss": loss}
    if loss == "quantile":
        kwargs["quantile"] = 0.5
    return HistGradientBoostingRegressor(
        **kwargs,
        learning_rate=config.learning_rate,
        max_iter=config.max_iter,
        max_depth=config.max_depth,
        min_samples_leaf=config.min_samples_leaf,
        l2_regularization=config.l2_regularization,
        early_stopping=False,
        random_state=config.base.random_seed,
    )


def _fold_metrics(frame: pd.DataFrame, fold: str, config: TemporalRiskConfig) -> dict[str, object]:
    target = frame[NET_TARGET].to_numpy(dtype=float)
    mean = frame["predicted_mean_net_excess"].to_numpy(dtype=float)
    median = frame["predicted_median_net_excess"].to_numpy(dtype=float)
    eligible = (
        (mean >= config.entry_net_excess)
        & (median > config.entry_median_net_excess)
        & ~frame["market_anomaly"].to_numpy(dtype=bool)
    )
    mean_spearman = pd.Series(mean).corr(pd.Series(target), method="spearman")
    median_spearman = pd.Series(median).corr(pd.Series(target), method="spearman")
    return {
        "model": MODEL_CONTRACT,
        "fold": fold,
        "validation_year": int(frame["date"].dt.year.iloc[0]),
        "rows": len(frame),
        "dates": int(frame["date"].nunique()),
        "mean_mae": float(mean_absolute_error(target, mean)),
        "mean_rmse": float(np.sqrt(mean_squared_error(target, mean))),
        "mean_r2": float(r2_score(target, mean)),
        "mean_spearman": None if pd.isna(mean_spearman) else float(mean_spearman),
        "median_mae": float(mean_absolute_error(target, median)),
        "median_spearman": None if pd.isna(median_spearman) else float(median_spearman),
        "market_anomaly_dates": int(frame.loc[frame["market_anomaly"], "date"].nunique()),
        "entry_gate_rows": int(eligible.sum()),
        "entry_gate_rate": float(np.mean(eligible)),
        "entry_gate_realized_mean_net_excess": float(np.mean(target[eligible])) if eligible.any() else None,
        "entry_gate_realized_positive_rate": float(np.mean(target[eligible] > 0.0)) if eligible.any() else None,
    }


def evaluate_models(
    prepared: PreparedTemporalResearch,
    index: pd.DataFrame,
    config: TemporalRiskConfig,
) -> TemporalModelResult:
    predictions: list[pd.DataFrame] = []
    metrics: list[dict[str, object]] = []
    audits: list[dict[str, object]] = []
    frame = prepared.frame
    for fold in config.base.folds:
        train_dates, validation_dates = fold_dates(
            index, fold, config.base.purge_sessions, config.base.embargo_sessions
        )
        train = frame.loc[frame["date"].isin(train_dates)].copy()
        validation = frame.loc[frame["date"].isin(validation_dates)].copy()
        if train.empty or validation.empty or train["date"].max() >= validation["date"].min():
            raise ValueError(f"안전한 Phase 5F fold가 아닙니다: {fold.name}")
        state = _fill_state(train, prepared.model_features)
        x_train = _matrix(train, prepared.model_features, state)
        x_validation = _matrix(validation, prepared.model_features, state)
        target = train[NET_TARGET].to_numpy(dtype=float)
        mean_model = _regressor(config, "squared_error").fit(x_train, target)
        median_model = _regressor(config, "quantile").fit(x_train, target)

        daily_train = train[["date", *prepared.market_features]].drop_duplicates("date").sort_values("date")
        daily_validation = validation[["date", *prepared.market_features]].drop_duplicates("date").sort_values("date")
        market_state = _fill_state(daily_train, prepared.market_features)
        anomaly_model = IsolationForest(
            n_estimators=config.anomaly_estimators,
            max_samples=config.anomaly_max_samples,
            contamination="auto",
            random_state=config.base.random_seed,
            n_jobs=1,
        ).fit(_matrix(daily_train, prepared.market_features, market_state))
        train_scores = anomaly_model.score_samples(_matrix(daily_train, prepared.market_features, market_state))
        threshold = float(np.quantile(train_scores, config.anomaly_quantile))
        validation_scores = anomaly_model.score_samples(
            _matrix(daily_validation, prepared.market_features, market_state)
        )
        anomaly_by_date = pd.DataFrame({
            "date": daily_validation["date"].to_numpy(),
            "market_anomaly_score": validation_scores,
            "market_anomaly": validation_scores < threshold,
        })
        output = validation[[
            "date", "security_id", "membership_spell_id", "close", LABEL_COLUMN, NET_TARGET,
        ]].copy()
        output["predicted_mean_net_excess"] = mean_model.predict(x_validation)
        output["predicted_median_net_excess"] = median_model.predict(x_validation)
        output = output.merge(anomaly_by_date, on="date", how="left", validate="many_to_one")
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
            "model_input_columns": len(prepared.model_features),
            "anomaly_input_columns": len(prepared.market_features),
            "anomaly_train_dates": len(daily_train),
            "anomaly_validation_dates": len(daily_validation),
            "anomaly_threshold_quantile": config.anomaly_quantile,
            "anomaly_threshold": threshold,
            "anomaly_train_dates_below_threshold": int((train_scores < threshold).sum()),
            "anomaly_validation_dates_below_threshold": int((validation_scores < threshold).sum()),
            "purge_sessions": config.base.purge_sessions,
            "embargo_sessions": config.base.embargo_sessions,
            "preprocessing_fit_used_validation": False,
            "mean_model_fit_used_validation": False,
            "median_model_fit_used_validation": False,
            "anomaly_model_fit_used_validation": False,
            "event_labels_used_for_anomaly": False,
            "target_cross_sectional_rank_used": False,
            "adaptive_diagnostic_not_oos": True,
        })
    combined = pd.concat(predictions, ignore_index=True).sort_values(
        ["fold", "date", "security_id"], kind="mergesort"
    ).reset_index(drop=True)
    return TemporalModelResult(combined, pd.DataFrame(metrics), pd.DataFrame(audits))
