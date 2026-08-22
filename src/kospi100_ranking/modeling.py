from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import ndcg_score
from sklearn.tree import DecisionTreeRegressor

from kospi100_features.features import build_feature_matrix
from kospi100_features.labels import LABEL_COLUMN, attach_forward_label

from .config import Fold, RankingConfig
from .data import SelectionBundle


@dataclass(frozen=True)
class CandidateResult:
    predictions: pd.DataFrame
    rank_metrics: pd.DataFrame
    fold_audit: pd.DataFrame
    fitted_models: dict[str, dict[str, object]]


def prepare_research_frame(
    bundle: SelectionBundle,
    minimum_cross_section: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    feature_result = build_feature_matrix(bundle.feature_panel, bundle.index, bundle.corporate_actions)
    labeled, label_audit = attach_forward_label(
        feature_result.cross_sectional,
        bundle.full_history,
        bundle.index,
        bundle.corporate_actions,
    )
    eligible = labeled.loc[
        labeled["phase4_eligible"] & labeled["reversal_5"].notna() & labeled[LABEL_COLUMN].notna()
    ].copy()
    counts = eligible.groupby("date")["security_id"].transform("size")
    eligible = eligible.loc[counts >= minimum_cross_section].copy()
    eligible["feature_rank"] = eligible.groupby("date", sort=False)["reversal_5"].rank(
        method="average", pct=True
    )
    eligible["target_rank"] = eligible.groupby("date", sort=False)[LABEL_COLUMN].rank(
        method="average", pct=True
    )
    result = eligible[
        [
            "date",
            "security_id",
            "membership_spell_id",
            "close",
            "feature_rank",
            "target_rank",
            LABEL_COLUMN,
        ]
    ].sort_values(["date", "security_id"], kind="mergesort").reset_index(drop=True)
    audit = {
        "feature": "reversal_5",
        "feature_formula": "-(Close_t / Close_t-5 - 1)",
        "target": "rank(log(Open_t+11/Open_t+1)-log(IndexOpen_t+11/IndexOpen_t+1))",
        "minimum_cross_section": minimum_cross_section,
        "feature_calculated_rows": int(feature_result.cross_sectional["reversal_5"].notna().sum()),
        "label_calculated_rows": int(label_audit["complete_label_rows"]),
        "research_rows": int(len(result)),
        "research_dates": int(result["date"].nunique()),
        "minimum_signal_date": result["date"].min().date().isoformat(),
        "maximum_signal_date": result["date"].max().date().isoformat(),
        "future_bar_used_for_feature": False,
        "label_entry_after_signal": label_audit["entry_is_after_signal"],
        "label_exit_after_entry": label_audit["exit_is_after_entry"],
        "feature_audit": feature_result.audit,
        "label_audit": label_audit,
    }
    return result, audit


def fold_dates(index: pd.DataFrame, fold: Fold, purge: int, embargo: int) -> tuple[set[pd.Timestamp], set[pd.Timestamp]]:
    sessions = index["date"].sort_values(kind="mergesort")
    train = sessions.loc[sessions.between(pd.Timestamp(fold.train.start), pd.Timestamp(fold.train.end))].tolist()
    validation = sessions.loc[
        sessions.between(pd.Timestamp(fold.validation.start), pd.Timestamp(fold.validation.end))
    ].tolist()
    if len(train) <= purge or len(validation) <= purge + embargo:
        raise ValueError(f"fold 길이가 purge/embargo보다 짧습니다: {fold.name}")
    return set(train[:-purge]), set(validation[embargo:-purge])


def _candidate_parameters(candidate: str) -> tuple[str, dict[str, object]]:
    if candidate == "raw_rank":
        return "raw_rank", {}
    if candidate == "ols":
        return "ols", {"fit_intercept": True}
    depth = int(candidate.split("_d", 1)[1].split("_", 1)[0])
    leaf_code = candidate.rsplit("l", 1)[1]
    leaf = {"002": 0.02, "005": 0.05}[leaf_code]
    return "tree", {"max_depth": depth, "min_samples_leaf": leaf}


def _fit(candidate: str, train: pd.DataFrame, seed: int) -> object | None:
    kind, parameters = _candidate_parameters(candidate)
    x = train[["feature_rank"]].to_numpy(dtype=float)
    y = train["target_rank"].to_numpy(dtype=float)
    if kind == "raw_rank":
        return None
    if kind == "ols":
        return LinearRegression(fit_intercept=True).fit(x, y)
    return DecisionTreeRegressor(
        criterion="squared_error",
        splitter="best",
        max_depth=int(parameters["max_depth"]),
        min_samples_leaf=float(parameters["min_samples_leaf"]),
        min_samples_split=2,
        max_features=None,
        max_leaf_nodes=None,
        min_impurity_decrease=0.0,
        ccp_alpha=0.0,
        random_state=seed,
    ).fit(x, y)


def _predict(model: object | None, frame: pd.DataFrame) -> np.ndarray:
    if model is None:
        return frame["feature_rank"].to_numpy(dtype=float)
    return np.asarray(model.predict(frame[["feature_rank"]].to_numpy(dtype=float)), dtype=float)


def _serialize(candidate: str, model: object | None) -> dict[str, object]:
    kind, parameters = _candidate_parameters(candidate)
    if kind == "raw_rank":
        payload: dict[str, Any] = {"candidate": candidate, "kind": kind, "mapping": "identity"}
    elif kind == "ols":
        assert isinstance(model, LinearRegression)
        payload = {
            "candidate": candidate,
            "kind": kind,
            "coefficient": float(model.coef_[0]),
            "intercept": float(model.intercept_),
            "n_features_in": int(model.n_features_in_),
        }
    else:
        assert isinstance(model, DecisionTreeRegressor)
        tree = model.tree_
        payload = {
            "candidate": candidate,
            "kind": kind,
            "parameters": parameters,
            "children_left": tree.children_left.tolist(),
            "children_right": tree.children_right.tolist(),
            "feature": tree.feature.tolist(),
            "threshold": [float(value) for value in tree.threshold],
            "value": [float(value[0][0]) for value in tree.value],
            "n_node_samples": tree.n_node_samples.tolist(),
        }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    payload["model_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def _rank_metrics(frame: pd.DataFrame, candidate: str, fold: str) -> dict[str, object]:
    daily_ic: list[float] = []
    daily_ndcg: list[float] = []
    daily_spread: list[float] = []
    for _, group in frame.groupby("date", sort=True):
        if group["score"].nunique() > 1 and group["target_rank"].nunique() > 1:
            daily_ic.append(float(group["score"].corr(group["target_rank"], method="spearman")))
        daily_ndcg.append(
            float(ndcg_score(group[["target_rank"]].to_numpy(dtype=float).T, group[["score"]].to_numpy(dtype=float).T, k=10))
        )
        ranked = group.sort_values(["score", "security_id"], ascending=[True, True], kind="mergesort").copy()
        ranked["score_rank"] = np.arange(1, len(ranked) + 1, dtype=float) / len(ranked)
        top = ranked.loc[ranked["score_rank"] > 0.9, "target_rank"].mean()
        bottom = ranked.loc[ranked["score_rank"] <= 0.1, "target_rank"].mean()
        daily_spread.append(float(top - bottom))
    annual_ic = (
        frame.assign(year=frame["date"].dt.year)
        .groupby("year", sort=True)
        .apply(lambda group: group["score"].corr(group["target_rank"], method="spearman"), include_groups=False)
    )
    return {
        "candidate": candidate,
        "fold": fold,
        "validation_year": int(frame["date"].dt.year.iloc[0]),
        "rows": len(frame),
        "dates": frame["date"].nunique(),
        "coverage": float(frame[["score", "target_rank"]].notna().all(axis=1).mean()),
        "mean_daily_spearman_ic": float(np.mean(daily_ic)) if daily_ic else None,
        "positive_ic_day_ratio": float(np.mean(np.asarray(daily_ic) > 0)) if daily_ic else None,
        "annual_spearman_ic": float(annual_ic.iloc[0]),
        "ndcg_at_10": float(np.mean(daily_ndcg)),
        "top_bottom_decile_target_spread": float(np.mean(daily_spread)),
    }


def evaluate_candidates(frame: pd.DataFrame, index: pd.DataFrame, config: RankingConfig) -> CandidateResult:
    prediction_frames: list[pd.DataFrame] = []
    metric_rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    models: dict[str, dict[str, object]] = {}
    for candidate in config.candidate_order:
        for fold in config.folds:
            train_dates, validation_dates = fold_dates(index, fold, config.purge_sessions, config.embargo_sessions)
            train = frame.loc[frame["date"].isin(train_dates)].copy()
            validation = frame.loc[frame["date"].isin(validation_dates)].copy()
            if train.empty or validation.empty:
                raise ValueError(f"빈 fold입니다: {candidate} {fold.name}")
            if train["date"].max() >= validation["date"].min():
                raise AssertionError("Train이 Validation보다 앞서지 않습니다")
            model = _fit(candidate, train, config.random_seed)
            validation["score"] = _predict(model, validation)
            validation["candidate"] = candidate
            validation["fold"] = fold.name
            prediction_frames.append(validation)
            metric_rows.append(_rank_metrics(validation, candidate, fold.name))
            models[f"{candidate}:{fold.name}"] = _serialize(candidate, model)
            audit_rows.append(
                {
                    "candidate": candidate,
                    "fold": fold.name,
                    "train_min_date": train["date"].min().date().isoformat(),
                    "train_max_date": train["date"].max().date().isoformat(),
                    "train_rows": len(train),
                    "validation_min_date": validation["date"].min().date().isoformat(),
                    "validation_max_date": validation["date"].max().date().isoformat(),
                    "validation_rows": len(validation),
                    "purge_sessions": config.purge_sessions,
                    "embargo_sessions": config.embargo_sessions,
                    "fit_used_validation": False,
                }
            )
    predictions = pd.concat(prediction_frames, ignore_index=True).sort_values(
        ["candidate", "date", "security_id"], kind="mergesort"
    )
    return CandidateResult(
        predictions=predictions,
        rank_metrics=pd.DataFrame(metric_rows),
        fold_audit=pd.DataFrame(audit_rows),
        fitted_models=models,
    )


def refit_selected(candidate: str, frame: pd.DataFrame, index: pd.DataFrame, config: RankingConfig) -> dict[str, object]:
    sessions = index.loc[index["date"].between("2011-01-01", "2021-12-31"), "date"].sort_values().tolist()
    allowed_dates = set(sessions[:-config.purge_sessions])
    train = frame.loc[frame["date"].isin(allowed_dates)].copy()
    model = _fit(candidate, train, config.random_seed)
    payload = _serialize(candidate, model)
    payload.update(
        {
            "experiment_id": config.experiment_id,
            "feature": "reversal_5 cross-sectional percentile rank",
            "target": "forward 10-session excess open-to-open return percentile rank",
            "fit_min_date": train["date"].min().date().isoformat(),
            "fit_max_date": train["date"].max().date().isoformat(),
            "fit_rows": len(train),
            "development_test_rows_used": 0,
        }
    )
    canonical = json.dumps({k: v for k, v in payload.items() if k != "model_hash"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    payload["model_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload
