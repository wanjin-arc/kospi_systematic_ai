from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from kospi100_features.labels import LABEL_COLUMN
from kospi100_multifactor.modeling import (
    _daily_rank,
    _fit,
    _predict,
    _preprocessor_state,
    _rank_metrics,
    _transform,
)
from kospi100_ranking.modeling import fold_dates

from .config import SelectiveConfig


@dataclass(frozen=True)
class SelectiveModelResult:
    predictions: pd.DataFrame
    rank_metrics: pd.DataFrame
    fold_audit: pd.DataFrame


def evaluate_model(frame: pd.DataFrame, index: pd.DataFrame, config: SelectiveConfig) -> SelectiveModelResult:
    predictions: list[pd.DataFrame] = []
    metrics: list[dict[str, object]] = []
    audits: list[dict[str, object]] = []
    base = config.base
    for fold in base.folds:
        train_dates, validation_dates = fold_dates(index, fold, base.purge_sessions, base.embargo_sessions)
        train = frame.loc[frame["date"].isin(train_dates)].copy()
        validation = frame.loc[frame["date"].isin(validation_dates)].copy()
        if train.empty or validation.empty or train["date"].max() >= validation["date"].min():
            raise ValueError(f"안전한 Train/Validation fold가 아닙니다: {fold.name}")
        state = _preprocessor_state(train, base)
        x_train, input_names = _transform(train, state, base)
        x_validation, validation_names = _transform(validation, state, base)
        if input_names != validation_names:
            raise AssertionError("Train/Validation 입력 순서가 다릅니다")
        model = _fit(
            config.model_candidate,
            x_train,
            train["target_rank"].to_numpy(dtype=float),
            base.random_seed,
        )
        raw = _predict(config.model_candidate, model, x_validation, len(base.stock_features))
        columns = [
            "date",
            "security_id",
            "membership_spell_id",
            "close",
            LABEL_COLUMN,
            "target_rank",
            "index_trend_200",
            "breadth_above_sma200",
        ]
        output = validation[columns].copy()
        output["raw_prediction"] = raw
        output["score"] = _daily_rank(raw, validation).to_numpy(dtype=float)
        output["candidate"] = config.model_candidate
        output["fold"] = fold.name
        predictions.append(output)
        metrics.append(_rank_metrics(output, config.model_candidate, fold.name))
        audits.append(
            {
                "candidate": config.model_candidate,
                "fold": fold.name,
                "train_min_date": state["fit_min_date"],
                "train_max_date": state["fit_max_date"],
                "train_rows": len(train),
                "validation_min_date": validation["date"].min().date().isoformat(),
                "validation_max_date": validation["date"].max().date().isoformat(),
                "validation_rows": len(validation),
                "input_columns": len(input_names),
                "purge_sessions": base.purge_sessions,
                "embargo_sessions": base.embargo_sessions,
                "preprocessing_fit_used_validation": False,
                "model_fit_used_validation": False,
                "reused_validation_not_oos": True,
            }
        )
    result = pd.concat(predictions, ignore_index=True).sort_values(
        ["fold", "date", "security_id"], kind="mergesort"
    )
    return SelectiveModelResult(result, pd.DataFrame(metrics), pd.DataFrame(audits))
