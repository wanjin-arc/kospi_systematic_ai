from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.metrics import ndcg_score

from kospi100_features.evaluate import _hac_tstat
from kospi100_features.features import build_feature_matrix
from kospi100_features.labels import LABEL_COLUMN, attach_forward_label
from kospi100_ranking.data import SelectionBundle
from kospi100_ranking.modeling import fold_dates

from .config import MultifactorConfig


@dataclass(frozen=True)
class PreparedResearch:
    frame: pd.DataFrame
    audit: dict[str, object]


@dataclass(frozen=True)
class CandidateResult:
    predictions: pd.DataFrame
    rank_metrics: pd.DataFrame
    fold_audit: pd.DataFrame
    feature_metrics: pd.DataFrame


def prepare_multifactor_frame(bundle: SelectionBundle, config: MultifactorConfig) -> PreparedResearch:
    features = build_feature_matrix(bundle.feature_panel, bundle.index, bundle.corporate_actions)
    labeled, label_audit = attach_forward_label(
        features.cross_sectional,
        bundle.full_history,
        bundle.index,
        bundle.corporate_actions,
    )
    missing = set(config.stock_features) - set(labeled.columns)
    missing_regime = set(config.regime_features) - set(features.regime.columns)
    if missing or missing_regime:
        raise ValueError(f"다변수 입력 열 누락: stock={sorted(missing)} regime={sorted(missing_regime)}")
    eligible = labeled.loc[labeled["phase4_eligible"] & labeled[LABEL_COLUMN].notna()].copy()
    counts = eligible.groupby("date", sort=False)["security_id"].transform("size")
    eligible = eligible.loc[counts >= config.minimum_cross_section].copy()
    rank_columns: list[str] = []
    for name in config.stock_features:
        rank_name = f"rank__{name}"
        eligible[rank_name] = eligible.groupby("date", sort=False)[name].rank(method="average", pct=True)
        rank_columns.append(rank_name)
    eligible["target_rank"] = eligible.groupby("date", sort=False)[LABEL_COLUMN].rank(
        method="average", pct=True
    )
    regime = features.regime[["date", *config.regime_features]].copy()
    eligible = eligible.merge(regime, on="date", how="left", validate="many_to_one")
    columns = [
        "date",
        "security_id",
        "membership_spell_id",
        "close",
        LABEL_COLUMN,
        "target_rank",
        *rank_columns,
        *config.regime_features,
    ]
    result = eligible[columns].sort_values(["date", "security_id"], kind="mergesort").reset_index(drop=True)
    maximum = result["date"].max().date()
    if maximum > config.maximum_permitted_date:
        raise PermissionError("Phase 4B/5B 연구 계산이 2018년을 넘었습니다")
    coverage = {
        name: float(result[f"rank__{name}"].notna().mean()) for name in config.stock_features
    }
    audit = {
        "stock_feature_count": len(config.stock_features),
        "regime_feature_count": len(config.regime_features),
        "interaction_count": len(config.interactions),
        "stock_feature_coverage": coverage,
        "research_rows": len(result),
        "research_dates": int(result["date"].nunique()),
        "minimum_signal_date": result["date"].min().date().isoformat(),
        "maximum_signal_date": maximum.isoformat(),
        "daily_cross_sectional_rank": True,
        "future_bar_used_for_feature": False,
        "label_entry_after_signal": label_audit["entry_is_after_signal"],
        "label_exit_after_entry": label_audit["exit_is_after_entry"],
        "feature_audit": features.audit,
        "label_audit": label_audit,
    }
    return PreparedResearch(result, audit)


def _preprocessor_state(train: pd.DataFrame, config: MultifactorConfig) -> dict[str, object]:
    rank_columns = [f"rank__{name}" for name in config.stock_features]
    rank_medians = train[rank_columns].median().fillna(0.5)
    daily_regime = train[["date", *config.regime_features]].drop_duplicates("date").sort_values("date")
    regime_medians = daily_regime[list(config.regime_features)].median().fillna(0.0)
    filled = daily_regime[list(config.regime_features)].fillna(regime_medians)
    regime_means = filled.mean()
    regime_stds = filled.std(ddof=0).replace(0.0, 1.0).fillna(1.0)
    return {
        "rank_medians": {key: float(value) for key, value in rank_medians.items()},
        "regime_medians": {key: float(value) for key, value in regime_medians.items()},
        "regime_means": {key: float(value) for key, value in regime_means.items()},
        "regime_stds": {key: float(value) for key, value in regime_stds.items()},
        "fit_min_date": train["date"].min().date().isoformat(),
        "fit_max_date": train["date"].max().date().isoformat(),
        "fit_rows": len(train),
    }


def _transform(
    frame: pd.DataFrame,
    state: dict[str, object],
    config: MultifactorConfig,
) -> tuple[np.ndarray, tuple[str, ...]]:
    rank_names = tuple(f"rank__{name}" for name in config.stock_features)
    rank_medians = pd.Series(state["rank_medians"], dtype=float)
    ranks = frame[list(rank_names)].astype(float).fillna(rank_medians)
    regime_medians = pd.Series(state["regime_medians"], dtype=float)
    regime_means = pd.Series(state["regime_means"], dtype=float)
    regime_stds = pd.Series(state["regime_stds"], dtype=float)
    regime = frame[list(config.regime_features)].astype(float).fillna(regime_medians)
    regime_z = ((regime - regime_means) / regime_stds).clip(-3.0, 3.0)
    regime_z.columns = [f"z__{name}" for name in config.regime_features]
    interactions: dict[str, pd.Series] = {}
    for stock, market in config.interactions:
        name = f"interaction__{stock}__{market}"
        interactions[name] = (ranks[f"rank__{stock}"] - 0.5) * regime_z[f"z__{market}"]
    interaction_frame = pd.DataFrame(interactions, index=frame.index)
    matrix = pd.concat([ranks, regime_z, interaction_frame], axis=1)
    if not np.isfinite(matrix.to_numpy(dtype=float)).all():
        raise ValueError("Train-only 전처리 후 비유한 값이 남았습니다")
    return matrix.to_numpy(dtype=float), tuple(matrix.columns)


def _fit(candidate: str, x: np.ndarray, y: np.ndarray, seed: int) -> object | None:
    if candidate == "equal_weight_rank":
        return None
    if candidate == "ridge_a1":
        return Ridge(alpha=1.0, fit_intercept=True).fit(x, y)
    if candidate == "ridge_a100":
        return Ridge(alpha=100.0, fit_intercept=True).fit(x, y)
    if candidate == "elastic_a005_l02":
        return ElasticNet(
            alpha=0.005,
            l1_ratio=0.2,
            fit_intercept=True,
            max_iter=10000,
            tol=0.00002,
            selection="cyclic",
            random_state=seed,
        ).fit(x, y)
    if candidate.startswith("histgb_"):
        depth = 2 if "_d2_" in candidate else 3
        return HistGradientBoostingRegressor(
            learning_rate=0.05,
            max_iter=150,
            max_depth=depth,
            min_samples_leaf=200,
            l2_regularization=1.0,
            early_stopping=False,
            random_state=seed,
        ).fit(x, y)
    raise ValueError(f"직접 적합할 수 없는 후보: {candidate}")


def _predict(candidate: str, model: object | None, x: np.ndarray, stock_feature_count: int) -> np.ndarray:
    if candidate == "equal_weight_rank":
        return np.mean(x[:, :stock_feature_count], axis=1)
    if model is None:
        raise AssertionError("학습 후보 모델이 없습니다")
    return np.asarray(model.predict(x), dtype=float)


def _daily_rank(values: np.ndarray, frame: pd.DataFrame) -> pd.Series:
    temporary = pd.DataFrame({"date": frame["date"].to_numpy(), "raw": values}, index=frame.index)
    return temporary.groupby("date", sort=False)["raw"].rank(method="average", pct=True)


def _rank_metrics(frame: pd.DataFrame, candidate: str, fold: str) -> dict[str, object]:
    daily_ic: list[float] = []
    daily_ndcg: list[float] = []
    daily_spread: list[float] = []
    for _, group in frame.groupby("date", sort=True):
        if group["score"].nunique() > 1 and group["target_rank"].nunique() > 1:
            daily_ic.append(float(group["score"].corr(group["target_rank"], method="spearman")))
        daily_ndcg.append(
            float(
                ndcg_score(
                    group[["target_rank"]].to_numpy(dtype=float).T,
                    group[["score"]].to_numpy(dtype=float).T,
                    k=10,
                )
            )
        )
        ranked = group.sort_values(["score", "security_id"], ascending=[True, True], kind="mergesort")
        count = len(ranked)
        top = ranked.iloc[max(0, int(np.floor(count * 0.9))):]["target_rank"].mean()
        bottom = ranked.iloc[: max(1, int(np.ceil(count * 0.1)))]["target_rank"].mean()
        daily_spread.append(float(top - bottom))
    return {
        "candidate": candidate,
        "fold": fold,
        "validation_year": int(frame["date"].dt.year.iloc[0]),
        "rows": len(frame),
        "dates": int(frame["date"].nunique()),
        "coverage": float(frame[["score", "target_rank"]].notna().all(axis=1).mean()),
        "mean_daily_spearman_ic": float(np.mean(daily_ic)) if daily_ic else None,
        "positive_ic_day_ratio": float(np.mean(np.asarray(daily_ic) > 0)) if daily_ic else None,
        "ndcg_at_10": float(np.mean(daily_ndcg)),
        "top_bottom_decile_target_spread": float(np.mean(daily_spread)),
    }


def feature_diagnostics(frame: pd.DataFrame, index: pd.DataFrame, config: MultifactorConfig) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for fold in config.folds:
        _, validation_dates = fold_dates(index, fold, config.purge_sessions, config.embargo_sessions)
        validation = frame.loc[frame["date"].isin(validation_dates)]
        for feature in config.stock_features:
            column = f"rank__{feature}"
            available = validation[["date", column, "target_rank"]].dropna()
            daily = available.groupby("date", sort=True).apply(
                lambda group: group[column].corr(group["target_rank"], method="spearman"),
                include_groups=False,
            ).dropna()
            rows.append(
                {
                    "fold": fold.name,
                    "validation_year": fold.validation.start.year,
                    "feature_id": feature,
                    "coverage": float(validation[column].notna().mean()),
                    "ic_days": len(daily),
                    "mean_daily_spearman_ic": float(daily.mean()) if not daily.empty else None,
                    "hac_t_stat": _hac_tstat(daily, int(config.payload.get("hac_lag_sessions", 10))),
                    "positive_ic_day_ratio": float((daily > 0).mean()) if not daily.empty else None,
                }
            )
    return pd.DataFrame(rows)


def evaluate_candidates(frame: pd.DataFrame, index: pd.DataFrame, config: MultifactorConfig) -> CandidateResult:
    predictions: list[pd.DataFrame] = []
    metrics: list[dict[str, object]] = []
    audits: list[dict[str, object]] = []
    diagnostics = feature_diagnostics(frame, index, config)
    direct_candidates = tuple(name for name in config.candidate_order if name != "blend_ridge_histgb")
    for fold in config.folds:
        train_dates, validation_dates = fold_dates(index, fold, config.purge_sessions, config.embargo_sessions)
        train = frame.loc[frame["date"].isin(train_dates)].copy()
        validation = frame.loc[frame["date"].isin(validation_dates)].copy()
        if train.empty or validation.empty or train["date"].max() >= validation["date"].min():
            raise ValueError(f"안전한 Train/Validation fold가 아닙니다: {fold.name}")
        state = _preprocessor_state(train, config)
        x_train, input_names = _transform(train, state, config)
        x_validation, validation_names = _transform(validation, state, config)
        if input_names != validation_names:
            raise AssertionError("Train/Validation 입력 순서가 다릅니다")
        y_train = train["target_rank"].to_numpy(dtype=float)
        fold_scores: dict[str, pd.Series] = {}
        for candidate in direct_candidates:
            model = _fit(candidate, x_train, y_train, config.random_seed)
            raw = _predict(candidate, model, x_validation, len(config.stock_features))
            fold_scores[candidate] = _daily_rank(raw, validation)
        blend = 0.5 * fold_scores["ridge_a100"] + 0.5 * fold_scores["histgb_d3_l200"]
        fold_scores["blend_ridge_histgb"] = _daily_rank(blend.to_numpy(dtype=float), validation)
        for candidate in config.candidate_order:
            output = validation[
                ["date", "security_id", "membership_spell_id", "close", LABEL_COLUMN, "target_rank"]
            ].copy()
            output["score"] = fold_scores[candidate].to_numpy(dtype=float)
            output["candidate"] = candidate
            output["fold"] = fold.name
            predictions.append(output)
            metrics.append(_rank_metrics(output, candidate, fold.name))
            audits.append(
                {
                    "candidate": candidate,
                    "fold": fold.name,
                    "train_min_date": state["fit_min_date"],
                    "train_max_date": state["fit_max_date"],
                    "train_rows": len(train),
                    "validation_min_date": validation["date"].min().date().isoformat(),
                    "validation_max_date": validation["date"].max().date().isoformat(),
                    "validation_rows": len(validation),
                    "input_columns": len(input_names),
                    "purge_sessions": config.purge_sessions,
                    "embargo_sessions": config.embargo_sessions,
                    "preprocessing_fit_used_validation": False,
                    "model_fit_used_validation": False,
                }
            )
    prediction_frame = pd.concat(predictions, ignore_index=True).sort_values(
        ["candidate", "date", "security_id"], kind="mergesort"
    )
    return CandidateResult(
        prediction_frame,
        pd.DataFrame(metrics),
        pd.DataFrame(audits),
        diagnostics,
    )


def refit_candidate(
    candidate: str,
    frame: pd.DataFrame,
    index: pd.DataFrame,
    config: MultifactorConfig,
) -> tuple[dict[str, object], bytes]:
    sessions = index.loc[index["date"].between("2011-01-01", "2018-12-31"), "date"].sort_values().tolist()
    train = frame.loc[frame["date"].isin(set(sessions[:-config.purge_sessions]))].copy()
    state = _preprocessor_state(train, config)
    x, input_names = _transform(train, state, config)
    y = train["target_rank"].to_numpy(dtype=float)
    if candidate == "blend_ridge_histgb":
        model: Any = {
            "ridge_a100": _fit("ridge_a100", x, y, config.random_seed),
            "histgb_d3_l200": _fit("histgb_d3_l200", x, y, config.random_seed),
        }
    else:
        model = _fit(candidate, x, y, config.random_seed)
    binary = pickle.dumps({"preprocessor": state, "input_names": input_names, "model": model}, protocol=5)
    payload: dict[str, object] = {
        "experiment_id": config.experiment_id,
        "candidate": candidate,
        "input_names": list(input_names),
        "stock_features": list(config.stock_features),
        "regime_features": list(config.regime_features),
        "interactions": [list(value) for value in config.interactions],
        "fit_min_date": train["date"].min().date().isoformat(),
        "fit_max_date": train["date"].max().date().isoformat(),
        "fit_rows": len(train),
        "model_pickle_sha256": hashlib.sha256(binary).hexdigest(),
        "development_test_rows_used": 0,
        "final_oos_rows_used": 0,
    }
    if isinstance(model, (Ridge, ElasticNet)):
        payload["coefficients"] = {
            name: float(value) for name, value in zip(input_names, model.coef_, strict=True)
        }
        payload["intercept"] = float(model.intercept_)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    payload["model_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload, binary


def feature_score_relationships(
    frame: pd.DataFrame,
    predictions: pd.DataFrame,
    candidate: str,
    config: MultifactorConfig,
) -> pd.DataFrame:
    selected = predictions.loc[predictions["candidate"].eq(candidate), ["date", "security_id", "score"]]
    merged = selected.merge(frame, on=["date", "security_id"], how="left", validate="one_to_one")
    rows: list[dict[str, object]] = []
    for feature in config.stock_features:
        column = f"rank__{feature}"
        daily = merged[["date", column, "score", "target_rank"]].dropna().groupby("date", sort=True)
        score_relation = daily.apply(
            lambda group: group[column].corr(group["score"], method="spearman"), include_groups=False
        ).dropna()
        target_relation = daily.apply(
            lambda group: group[column].corr(group["target_rank"], method="spearman"), include_groups=False
        ).dropna()
        rows.append(
            {
                "feature_id": feature,
                "mean_daily_spearman_to_model_score": float(score_relation.mean()) if not score_relation.empty else None,
                "mean_daily_spearman_to_target": float(target_relation.mean()) if not target_relation.empty else None,
                "days": len(score_relation),
            }
        )
    return pd.DataFrame(rows).sort_values(
        "mean_daily_spearman_to_model_score", key=lambda values: values.abs(), ascending=False, kind="mergesort"
    )
