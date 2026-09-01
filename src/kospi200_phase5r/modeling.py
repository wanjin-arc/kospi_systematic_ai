"""Phase 5R B/C 독립 모델과 train-only soft-fusion 계약.

이 모듈은 데이터 로딩이나 포트폴리오 결정을 하지 않는다. 호출자가 제공한
시간순 학습표와 점수표에 대해 고정 모델을 적합하고, 날짜별 횡단면 점수를
만드는 순수 계산 계층만 제공한다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import math
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from kospi200_fundamental import FACTOR_IDS


TARGET_COLUMN = "target_quality_20"
AGENT_B_PREDICTION_COLUMN = "agent_b_prediction"
AGENT_B_PERCENTILE_COLUMN = "agent_b_percentile"
AGENT_C_PREDICTION_COLUMN = "agent_c_prediction"
AGENT_C_PERCENTILE_COLUMN = "agent_c_percentile"
FUNDAMENTAL_AVAILABLE_COLUMN = "fundamental_available"
AGENT_D_PREDICTION_COLUMN = "agent_d_prediction"
AGENT_D_PERCENTILE_COLUMN = "agent_d_percentile"
OOF_FLAG_COLUMN = "is_oof"

AGENT_D_FEATURE_COLUMNS = (
    AGENT_B_PERCENTILE_COLUMN,
    AGENT_C_PERCENTILE_COLUMN,
    FUNDAMENTAL_AVAILABLE_COLUMN,
)
AGENT_C_FEATURE_COLUMNS = (
    "return_1",
    "return_5",
    "return_20",
    "return_60",
    "volatility_5",
    "volatility_20",
    "downside_volatility_20",
    "close_to_ma20",
    "close_to_ma60",
    "drawdown_20",
    "drawdown_60",
    "intraday_range",
    "volume_ratio_20",
    "gap_1",
    "index_return_20",
    "index_trend_60",
    "index_volatility_20",
)

_B_DEFAULTS: dict[str, Any] = {
    "model": "RIDGE_FIXED",
    "alpha": 10.0,
    "imputer_strategy": "median",
    "keep_empty_features": True,
    "all_missing_fold_policy": "KEEP_FEATURE_ZERO_AFTER_IMPUTE",
}
_C_DEFAULTS: dict[str, Any] = {
    "model": "HIST_GRADIENT_BOOSTING_FIXED",
    "learning_rate": 0.05,
    "max_depth": 3,
    "max_iter": 100,
    "min_samples_leaf": 100,
    "l2_regularization": 10.0,
}
_D_DEFAULTS: dict[str, Any] = {
    "model": "POSITIVE_RIDGE_OOF",
    "alpha": 10.0,
    "hard_fundamental_gate": False,
}


@dataclass(frozen=True)
class FittedAgent:
    """적합 estimator와 JSON 직렬화 가능한 감사 정보를 함께 보관한다."""

    estimator: Pipeline
    audit: dict[str, Any]

    @property
    def model(self) -> Pipeline:
        """runner에서 읽기 쉬운 estimator 별칭."""

        return self.estimator


@dataclass(frozen=True)
class PurgedEmbargoFold:
    """세션 목록과 원래 행 index에 정렬된 시간 경계 mask."""

    train_mask: pd.Series
    evaluation_mask: pd.Series
    purged_mask: pd.Series
    embargoed_mask: pd.Series
    train_dates: tuple[str, ...]
    evaluation_dates: tuple[str, ...]
    purged_dates: tuple[str, ...]
    embargoed_dates: tuple[str, ...]

    @property
    def audit(self) -> dict[str, Any]:
        return {
            "train_dates": list(self.train_dates),
            "evaluation_dates": list(self.evaluation_dates),
            "purged_dates": list(self.purged_dates),
            "embargoed_dates": list(self.embargoed_dates),
            "train_rows": int(self.train_mask.sum()),
            "evaluation_rows": int(self.evaluation_mask.sum()),
            "purged_rows": int(self.purged_mask.sum()),
            "embargoed_rows": int(self.embargoed_mask.sum()),
        }


def _mapping(value: Mapping[str, Any] | object | None) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    raise TypeError("config는 mapping 또는 dataclass여야 합니다.")


def _agent_config(
    config: Mapping[str, Any] | object | None,
    agent: str,
    expected: Mapping[str, Any],
) -> tuple[dict[str, Any], int]:
    outer = _mapping(config)
    payload = _mapping(outer.get("payload", outer))
    section_value = payload.get(agent, payload)
    section = _mapping(section_value)
    resolved = dict(expected)
    resolved.update(section)
    for key, frozen_value in expected.items():
        actual = resolved[key]
        equal = (
            math.isclose(float(actual), float(frozen_value), rel_tol=0.0, abs_tol=1e-12)
            if isinstance(frozen_value, float)
            else actual == frozen_value
        )
        if not equal:
            raise ValueError(f"{agent}.{key}는 {frozen_value!r}로 고정됩니다: {actual!r}")
    seed = int(outer.get("seed", payload.get("seed", section.get("seed", 20260831))))
    return resolved, seed


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], context: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"{context} 필수 열 누락: {missing}")


def _feature_columns(feature_columns: Sequence[str]) -> tuple[str, ...]:
    columns = tuple(str(value) for value in feature_columns)
    if not columns or len(columns) != len(set(columns)):
        raise ValueError("feature_columns는 중복 없는 하나 이상의 열이어야 합니다.")
    return columns


def _numeric_features(
    frame: pd.DataFrame,
    feature_columns: Sequence[str],
    context: str,
    *,
    allow_missing: bool,
    allow_all_missing: bool = False,
) -> pd.DataFrame:
    _require_columns(frame, feature_columns, context)
    values = frame.loc[:, list(feature_columns)].apply(pd.to_numeric, errors="raise")
    if np.isinf(values.to_numpy(dtype=float, na_value=np.nan)).any():
        raise ValueError(f"{context} Feature에 무한대가 있습니다.")
    if not allow_missing and values.isna().any(axis=None):
        raise ValueError(f"{context} Feature에 결측치가 있습니다.")
    if allow_missing and not allow_all_missing:
        all_missing = [name for name in feature_columns if values[name].notna().sum() == 0]
        if all_missing:
            raise ValueError(f"{context}에서 전부 결측인 Feature가 있습니다: {all_missing}")
    return values


def _training_rows(train_df: pd.DataFrame, target_column: str) -> tuple[pd.DataFrame, pd.Series]:
    _require_columns(train_df, [target_column], "학습표")
    target = pd.to_numeric(train_df[target_column], errors="raise")
    valid = target.notna() & np.isfinite(target)
    if "label_valid" in train_df.columns:
        valid &= train_df["label_valid"].eq(True)  # noqa: E712 - 엄격한 참값 계약
    selected = train_df.loc[valid].copy()
    if selected.empty:
        raise ValueError("유효한 학습 target 행이 없습니다.")
    return selected, target.loc[valid]


def _date_bounds(frame: pd.DataFrame) -> tuple[str | None, str | None]:
    if "date" not in frame.columns or frame.empty:
        return None, None
    dates = frame["date"].astype(str)
    return str(dates.min()), str(dates.max())


def _ridge_state(model: Pipeline) -> dict[str, Any]:
    ridge = model.named_steps["model"]
    return {
        "coefficient": np.asarray(ridge.coef_, dtype=float).reshape(-1).tolist(),
        "intercept": float(np.asarray(ridge.intercept_, dtype=float).reshape(-1)[0]),
    }


def _audit(
    agent: str,
    estimator: Pipeline,
    feature_columns: Sequence[str],
    target_column: str,
    train_rows: pd.DataFrame,
    score_df: pd.DataFrame,
    params: Mapping[str, Any],
) -> dict[str, Any]:
    minimum, maximum = _date_bounds(train_rows)
    payload: dict[str, Any] = {
        "agent": agent,
        "estimator": estimator.named_steps["model"].__class__.__name__,
        "feature_columns": list(feature_columns),
        "target_column": target_column,
        "training_rows": int(len(train_rows)),
        "score_rows": int(len(score_df)),
        "training_min_date": minimum,
        "training_max_date": maximum,
        "fixed_parameters": dict(params),
        "hard_fundamental_gate": False,
    }
    if agent in {"B", "D"}:
        payload["fitted_state"] = _ridge_state(estimator)
    else:
        hist = estimator.named_steps["model"]
        payload["fitted_state"] = {"n_iter": int(hist.n_iter_)}
    return payload


def daily_percentile(
    frame: pd.DataFrame,
    value_column: str,
    output_column: str,
    *,
    date_column: str = "date",
) -> pd.DataFrame:
    """원래 행을 보존하며 날짜별 average-tie percentile을 붙인다."""

    _require_columns(frame, [date_column, value_column], "날짜별 percentile 입력")
    output = frame.copy()
    values = pd.to_numeric(output[value_column], errors="raise")
    output[output_column] = values.groupby(output[date_column], sort=False).rank(
        pct=True, method="average"
    )
    return output


def agent_b_feature_columns() -> tuple[str, ...]:
    """제외종목 제거 뒤 다시 계산한 20개 PIT Fundamental percentile 열."""

    return tuple(f"{factor}__phase4e_percentile" for factor in FACTOR_IDS)


def agent_c_feature_columns() -> tuple[str, ...]:
    """사전등록된 OHLCV·거래대금·공식지수 상태 열."""

    return AGENT_C_FEATURE_COLUMNS


def make_agent_b_model(config: Mapping[str, Any] | object | None = None) -> Pipeline:
    params, _ = _agent_config(config, "agent_b", _B_DEFAULTS)
    return Pipeline(
        [
            (
                "imputer",
                SimpleImputer(
                    strategy=str(params["imputer_strategy"]),
                    keep_empty_features=bool(params["keep_empty_features"]),
                ),
            ),
            ("scale", StandardScaler()),
            ("model", Ridge(alpha=float(params["alpha"]))),
        ]
    )


def make_agent_c_model(config: Mapping[str, Any] | object | None = None) -> Pipeline:
    params, seed = _agent_config(config, "agent_c", _C_DEFAULTS)
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                HistGradientBoostingRegressor(
                    learning_rate=float(params["learning_rate"]),
                    max_depth=int(params["max_depth"]),
                    max_iter=int(params["max_iter"]),
                    min_samples_leaf=int(params["min_samples_leaf"]),
                    l2_regularization=float(params["l2_regularization"]),
                    random_state=seed,
                ),
            ),
        ]
    )


def make_agent_d_model(config: Mapping[str, Any] | object | None = None) -> Pipeline:
    params, _ = _agent_config(config, "agent_d", _D_DEFAULTS)
    if params["hard_fundamental_gate"] is not False:
        raise ValueError("Agent D는 Fundamental hard gate를 사용할 수 없습니다.")
    return Pipeline(
        [
            ("scale", StandardScaler()),
            ("model", Ridge(alpha=float(params["alpha"]), positive=True)),
        ]
    )


def fit_predict_agent_b(
    train_df: pd.DataFrame,
    score_df: pd.DataFrame,
    feature_columns: Sequence[str],
    config: Mapping[str, Any] | object | None = None,
    *,
    target_column: str = TARGET_COLUMN,
) -> tuple[pd.DataFrame, FittedAgent]:
    columns = _feature_columns(feature_columns)
    selected, target = _training_rows(train_df, target_column)
    x_train = _numeric_features(
        selected,
        columns,
        "Agent B 학습표",
        allow_missing=True,
        allow_all_missing=True,
    )
    x_score = _numeric_features(
        score_df,
        columns,
        "Agent B 점수표",
        allow_missing=True,
        allow_all_missing=True,
    )
    estimator = make_agent_b_model(config)
    estimator.fit(x_train, target)
    output = score_df.copy()
    output[AGENT_B_PREDICTION_COLUMN] = estimator.predict(x_score)
    output = daily_percentile(output, AGENT_B_PREDICTION_COLUMN, AGENT_B_PERCENTILE_COLUMN)
    params, _ = _agent_config(config, "agent_b", _B_DEFAULTS)
    audit = _audit("B", estimator, columns, target_column, selected, score_df, params)
    return output, FittedAgent(estimator, audit)


def fit_predict_agent_c(
    train_df: pd.DataFrame,
    score_df: pd.DataFrame,
    feature_columns: Sequence[str],
    config: Mapping[str, Any] | object | None = None,
    *,
    target_column: str = TARGET_COLUMN,
) -> tuple[pd.DataFrame, FittedAgent]:
    columns = _feature_columns(feature_columns)
    selected, target = _training_rows(train_df, target_column)
    x_train = _numeric_features(selected, columns, "Agent C 학습표", allow_missing=True)
    x_score = _numeric_features(score_df, columns, "Agent C 점수표", allow_missing=True)
    estimator = make_agent_c_model(config)
    estimator.fit(x_train, target)
    output = score_df.copy()
    output[AGENT_C_PREDICTION_COLUMN] = estimator.predict(x_score)
    output = daily_percentile(output, AGENT_C_PREDICTION_COLUMN, AGENT_C_PERCENTILE_COLUMN)
    params, _ = _agent_config(config, "agent_c", _C_DEFAULTS)
    audit = _audit("C", estimator, columns, target_column, selected, score_df, params)
    return output, FittedAgent(estimator, audit)


def attach_neutral_agent_b_scores(
    score_universe: pd.DataFrame,
    agent_b_scores: pd.DataFrame,
    *,
    key_columns: Sequence[str] = ("date", "ticker"),
    missing_percentile: float = 0.5,
) -> pd.DataFrame:
    """B가 없는 종목을 제거하지 않고 중립점수와 availability를 붙인다."""

    keys = tuple(key_columns)
    _require_columns(score_universe, keys, "전체 점수 universe")
    _require_columns(
        agent_b_scores,
        [*keys, AGENT_B_PREDICTION_COLUMN, AGENT_B_PERCENTILE_COLUMN],
        "Agent B 점수",
    )
    if not 0.0 <= float(missing_percentile) <= 1.0:
        raise ValueError("missing_percentile은 [0, 1] 범위여야 합니다.")
    if score_universe.duplicated(list(keys)).any():
        raise ValueError("전체 점수 universe key가 중복됩니다.")
    if agent_b_scores.duplicated(list(keys)).any():
        raise ValueError("Agent B 점수 key가 중복됩니다.")
    collisions = {
        AGENT_B_PREDICTION_COLUMN,
        AGENT_B_PERCENTILE_COLUMN,
        FUNDAMENTAL_AVAILABLE_COLUMN,
    } & set(score_universe.columns)
    if collisions:
        raise ValueError(f"전체 점수 universe에 B 결합 열이 이미 있습니다: {sorted(collisions)}")

    right = agent_b_scores.loc[
        :, [*keys, AGENT_B_PREDICTION_COLUMN, AGENT_B_PERCENTILE_COLUMN]
    ].copy()
    output = score_universe.copy()
    output["__phase5r_row_order"] = np.arange(len(output), dtype=np.int64)
    output = output.merge(right, on=list(keys), how="left", validate="one_to_one", sort=False)
    available = output[AGENT_B_PERCENTILE_COLUMN].notna()
    output[FUNDAMENTAL_AVAILABLE_COLUMN] = available.astype(np.int8)
    output[AGENT_B_PERCENTILE_COLUMN] = output[AGENT_B_PERCENTILE_COLUMN].fillna(
        float(missing_percentile)
    )
    output = output.sort_values("__phase5r_row_order", kind="stable").drop(
        columns="__phase5r_row_order"
    )
    output.index = score_universe.index
    if len(output) != len(score_universe):
        raise AssertionError("B soft attach가 전체 점수 universe 행 수를 바꿨습니다.")
    return output


def _validate_d_frame(frame: pd.DataFrame, context: str) -> pd.DataFrame:
    values = _numeric_features(frame, AGENT_D_FEATURE_COLUMNS, context, allow_missing=False)
    percentiles = values[[AGENT_B_PERCENTILE_COLUMN, AGENT_C_PERCENTILE_COLUMN]]
    if ((percentiles < 0.0) | (percentiles > 1.0)).any(axis=None):
        raise ValueError(f"{context} percentile은 [0, 1] 범위여야 합니다.")
    available = values[FUNDAMENTAL_AVAILABLE_COLUMN]
    if not available.isin([0.0, 1.0]).all():
        raise ValueError(f"{context} fundamental_available은 0 또는 1이어야 합니다.")
    neutral_error = available.eq(0.0) & ~np.isclose(
        values[AGENT_B_PERCENTILE_COLUMN], 0.5, rtol=0.0, atol=1e-12
    )
    if neutral_error.any():
        raise ValueError(f"{context} B 결측행은 percentile 0.5여야 합니다.")
    return values


def fit_predict_agent_d(
    oof_train_df: pd.DataFrame,
    score_df: pd.DataFrame,
    config: Mapping[str, Any] | object | None = None,
    *,
    target_column: str = TARGET_COLUMN,
    oof_flag_column: str = OOF_FLAG_COLUMN,
) -> tuple[pd.DataFrame, FittedAgent]:
    """B/C inner-OOF 점수만으로 양의 Ridge late fusion을 적합한다."""

    _require_columns(oof_train_df, [oof_flag_column], "Agent D OOF 학습표")
    selected, target = _training_rows(oof_train_df, target_column)
    flags = selected[oof_flag_column]
    if flags.isna().any() or not flags.eq(True).all():  # noqa: E712 - OOF 참값 강제
        raise ValueError("Agent D 학습에는 inner OOF 예측행만 허용합니다.")
    x_train = _validate_d_frame(selected, "Agent D OOF 학습표")
    x_score = _validate_d_frame(score_df, "Agent D 점수표")
    estimator = make_agent_d_model(config)
    estimator.fit(x_train, target)
    output = score_df.copy()
    output[AGENT_D_PREDICTION_COLUMN] = estimator.predict(x_score)
    output = daily_percentile(output, AGENT_D_PREDICTION_COLUMN, AGENT_D_PERCENTILE_COLUMN)
    params, _ = _agent_config(config, "agent_d", _D_DEFAULTS)
    audit = _audit("D", estimator, AGENT_D_FEATURE_COLUMNS, target_column, selected, score_df, params)
    audit["oof_only"] = True
    return output, FittedAgent(estimator, audit)


def per_date_top_n_rows(
    frame: pd.DataFrame,
    score_column: str,
    n: int,
    *,
    date_column: str = "date",
    ticker_column: str = "ticker",
) -> pd.DataFrame:
    """연도 전체가 아니라 각 날짜 안에서 Top N을 선택한다."""

    if int(n) <= 0:
        raise ValueError("n은 양수여야 합니다.")
    _require_columns(frame, [date_column, ticker_column, score_column], "Top N 입력")
    eligible = frame.loc[frame[score_column].notna()].copy()
    eligible[score_column] = pd.to_numeric(eligible[score_column], errors="raise")
    eligible[ticker_column] = eligible[ticker_column].astype(str)
    selected = (
        eligible.sort_values(
            [date_column, score_column, ticker_column],
            ascending=[True, False, True],
            kind="stable",
        )
        .groupby(date_column, sort=False, group_keys=False)
        .head(int(n))
    )
    return selected.copy()


def per_date_top_n_metric(
    frame: pd.DataFrame,
    score_column: str,
    metric_column: str,
    n: int,
    *,
    date_column: str = "date",
    ticker_column: str = "ticker",
) -> float:
    """각 날짜 Top N의 일별 평균을 계산한 뒤 날짜를 동일 가중 평균한다."""

    _require_columns(frame, [metric_column], "Top N metric 입력")
    selected = per_date_top_n_rows(
        frame,
        score_column,
        n,
        date_column=date_column,
        ticker_column=ticker_column,
    )
    if selected.empty:
        return float("nan")
    values = pd.to_numeric(selected[metric_column], errors="raise")
    daily = values.groupby(selected[date_column], sort=False).mean()
    return float(daily.mean())


def build_purged_embargo_fold(
    frame: pd.DataFrame,
    sessions: Sequence[object],
    evaluation_start: object,
    evaluation_end: object,
    *,
    purge_sessions: int,
    embargo_sessions: int,
    candidate_training_dates: Iterable[object] | None = None,
    date_column: str = "date",
) -> PurgedEmbargoFold:
    """단일 purge와 조건부 사후 embargo를 적용한 날짜·행 mask를 만든다.

    ``candidate_training_dates``를 생략하면 anchored forward fold로 간주하여
    평가 시작 전 세션만 학습 후보가 된다. 평가 뒤 세션을 이후 학습에 다시
    넣는 blocked-CV에서는 후보 날짜를 명시해야 하며, 그때에만 평가 종료 뒤
    첫 ``embargo_sessions``가 실제 제거된다.
    """

    if int(purge_sessions) < 0 or int(embargo_sessions) < 0:
        raise ValueError("purge_sessions와 embargo_sessions는 음수일 수 없습니다.")
    _require_columns(frame, [date_column], "시간 fold 입력")
    ordered = tuple(str(value) for value in sessions)
    if not ordered or len(ordered) != len(set(ordered)):
        raise ValueError("sessions는 중복 없는 시간순 목록이어야 합니다.")
    start, end = str(evaluation_start), str(evaluation_end)
    positions = {value: index for index, value in enumerate(ordered)}
    if start not in positions or end not in positions or positions[start] > positions[end]:
        raise ValueError("evaluation_start/end가 sessions 안의 올바른 순서여야 합니다.")
    start_i, end_i = positions[start], positions[end]
    evaluation_dates = ordered[start_i : end_i + 1]

    if candidate_training_dates is None:
        candidate_dates = set(ordered[:start_i])
    else:
        candidate_dates = {str(value) for value in candidate_training_dates}
        unknown = sorted(candidate_dates - set(ordered))
        if unknown:
            raise ValueError(f"sessions에 없는 학습 후보 날짜가 있습니다: {unknown}")
    overlap = candidate_dates & set(evaluation_dates)
    if overlap:
        raise ValueError(f"학습 후보와 평가 날짜가 겹칩니다: {sorted(overlap)}")

    purge_window = set(ordered[max(0, start_i - int(purge_sessions)) : start_i])
    embargo_window = set(ordered[end_i + 1 : end_i + 1 + int(embargo_sessions)])
    purged_dates = tuple(value for value in ordered if value in candidate_dates & purge_window)
    embargoed_dates = tuple(value for value in ordered if value in candidate_dates & embargo_window)
    train_dates = tuple(
        value
        for value in ordered
        if value in candidate_dates
        and value not in purge_window
        and value not in embargo_window
    )

    row_dates = frame[date_column].astype(str)
    train_mask = row_dates.isin(train_dates)
    evaluation_mask = row_dates.isin(evaluation_dates)
    purged_mask = row_dates.isin(purged_dates)
    embargoed_mask = row_dates.isin(embargoed_dates)
    return PurgedEmbargoFold(
        train_mask=train_mask,
        evaluation_mask=evaluation_mask,
        purged_mask=purged_mask,
        embargoed_mask=embargoed_mask,
        train_dates=train_dates,
        evaluation_dates=tuple(evaluation_dates),
        purged_dates=purged_dates,
        embargoed_dates=embargoed_dates,
    )


def _available_fundamental_mask(frame: pd.DataFrame, b_features: Sequence[str]) -> pd.Series:
    if FUNDAMENTAL_AVAILABLE_COLUMN in frame.columns:
        values = pd.to_numeric(frame[FUNDAMENTAL_AVAILABLE_COLUMN], errors="raise")
        if not values.isin([0.0, 1.0]).all():
            raise ValueError("fundamental_available은 0 또는 1이어야 합니다.")
        return values.eq(1.0)
    return frame.loc[:, list(b_features)].notna().any(axis=1)


def _agent_b_scope(frame: pd.DataFrame, b_features: Sequence[str]) -> pd.DataFrame:
    mask = _available_fundamental_mask(frame, b_features)
    columns = ["date", "ticker", *b_features]
    if TARGET_COLUMN in frame.columns:
        columns.append(TARGET_COLUMN)
    if "label_valid" in frame.columns:
        columns.append("label_valid")
    return frame.loc[mask, list(dict.fromkeys(columns))].copy()


def _agent_c_scope(frame: pd.DataFrame, c_features: Sequence[str]) -> pd.DataFrame:
    columns = ["date", "ticker", *c_features]
    if TARGET_COLUMN in frame.columns:
        columns.append(TARGET_COLUMN)
    if "label_valid" in frame.columns:
        columns.append("label_valid")
    return frame.loc[:, list(dict.fromkeys(columns))].copy()


def _fit_bc_scores(
    train_df: pd.DataFrame,
    score_df: pd.DataFrame,
    b_features: Sequence[str],
    c_features: Sequence[str],
    config: Mapping[str, Any] | object,
) -> tuple[pd.DataFrame, FittedAgent, FittedAgent]:
    b_train = _agent_b_scope(train_df, b_features)
    b_scope = _agent_b_scope(score_df, b_features)
    if b_train.empty or b_scope.empty:
        raise ValueError("Agent B 학습 또는 점수 기간에 Fundamental 가용 행이 없습니다.")
    b_scored, b_fit = fit_predict_agent_b(b_train, b_scope, b_features, config)

    c_train = _agent_c_scope(train_df, c_features)
    c_scope = _agent_c_scope(score_df, c_features)
    c_scored, c_fit = fit_predict_agent_c(c_train, c_scope, c_features, config)
    combined = attach_neutral_agent_b_scores(c_scored, b_scored)
    return combined, b_fit, c_fit


def _mean_daily_rank_ic(
    frame: pd.DataFrame,
    score_column: str,
    target_column: str = TARGET_COLUMN,
) -> float:
    values: list[float] = []
    valid = frame.dropna(subset=[score_column, target_column])
    for _, group in valid.groupby("date", sort=False):
        if len(group) < 2 or group[score_column].nunique() < 2 or group[target_column].nunique() < 2:
            continue
        score_rank = group[score_column].rank(method="average")
        target_rank = group[target_column].rank(method="average")
        values.append(float(score_rank.corr(target_rank)))
    return float(np.mean(values)) if values else float("nan")


def _year_dates(frame: pd.DataFrame, year: int) -> tuple[str, str] | None:
    dates = frame.loc[frame["date"].astype(str).str[:4].eq(str(int(year))), "date"].astype(str)
    if dates.empty:
        return None
    return str(dates.min()), str(dates.max())


def _walk_forward_config(config: Mapping[str, Any] | object) -> dict[str, Any]:
    outer = _mapping(config)
    payload = _mapping(outer.get("payload", outer))
    required = {
        "outer_evaluation_years",
        "inner_oof_start_year",
        "purge_sessions",
        "embargo_sessions",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"walk-forward config 필수 항목 누락: {missing}")
    if int(payload["purge_sessions"]) != 20 or int(payload["embargo_sessions"]) != 20:
        raise ValueError("Phase 5R purge와 embargo는 각각 20세션으로 고정됩니다.")
    return payload


def generate_walk_forward_scores(
    panel: pd.DataFrame,
    sessions: Sequence[object],
    config: Mapping[str, Any] | object,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """B/C inner OOF와 positive-Ridge D의 anchored outer 점수를 생성한다.

    반환 ``model_state``의 ``outer_models``에는 실제 fitted estimator가,
    ``outer_audit``와 ``inner_audit``에는 JSON 직렬화 가능한 상태 설명이 있다.
    이 함수는 파일을 읽거나 쓰지 않으며 주어진 panel 밖의 자료에 접근하지 않는다.
    """

    payload = _walk_forward_config(config)
    b_features = agent_b_feature_columns()
    c_features = agent_c_feature_columns()
    _require_columns(
        panel,
        ["date", "ticker", TARGET_COLUMN, *b_features, *c_features],
        "Phase 5R model panel",
    )
    if panel.duplicated(["date", "ticker"]).any():
        raise ValueError("Phase 5R model panel의 date/ticker가 중복됩니다.")
    working = panel.copy()
    working["date"] = working["date"].astype(str)
    ordered_sessions = tuple(str(value) for value in sessions)
    session_set = set(ordered_sessions)
    unknown_dates = sorted(set(working["date"]) - session_set)
    if unknown_dates:
        raise ValueError(f"panel 날짜가 sessions에 없습니다: {unknown_dates[:5]}")

    purge = int(payload["purge_sessions"])
    embargo = int(payload["embargo_sessions"])
    inner_start = int(payload["inner_oof_start_year"])
    outer_years = tuple(int(value) for value in payload["outer_evaluation_years"])
    top_n = int(_mapping(payload.get("portfolio", {})).get("alpha_size", 10))

    score_parts: list[pd.DataFrame] = []
    metric_rows: list[dict[str, Any]] = []
    outer_models: dict[str, dict[str, Pipeline]] = {}
    outer_audit: dict[str, dict[str, Any]] = {}
    inner_audit: dict[str, list[dict[str, Any]]] = {}

    for outer_year in outer_years:
        outer_bounds = _year_dates(working, outer_year)
        if outer_bounds is None:
            raise ValueError(f"outer 평가 연도 행이 없습니다: {outer_year}")
        outer_fold = build_purged_embargo_fold(
            working,
            ordered_sessions,
            outer_bounds[0],
            outer_bounds[1],
            purge_sessions=purge,
            embargo_sessions=embargo,
        )
        outer_train = working.loc[outer_fold.train_mask].copy()
        outer_scope = working.loc[outer_fold.evaluation_mask].copy()
        if outer_train.empty or outer_scope.empty:
            raise ValueError(f"outer fold 학습 또는 평가 행이 없습니다: {outer_year}")

        oof_parts: list[pd.DataFrame] = []
        fold_inner_audit: list[dict[str, Any]] = []
        for inner_year in range(inner_start, outer_year):
            inner_bounds = _year_dates(outer_train, inner_year)
            if inner_bounds is None:
                continue
            inner_fold = build_purged_embargo_fold(
                outer_train,
                ordered_sessions,
                inner_bounds[0],
                inner_bounds[1],
                purge_sessions=purge,
                embargo_sessions=embargo,
            )
            inner_train = outer_train.loc[inner_fold.train_mask].copy()
            inner_scope = outer_train.loc[inner_fold.evaluation_mask].copy()
            if inner_train.empty or inner_scope.empty:
                continue
            combined, b_inner, c_inner = _fit_bc_scores(
                inner_train,
                inner_scope,
                b_features,
                c_features,
                payload,
            )
            combined[OOF_FLAG_COLUMN] = True
            combined["inner_year"] = inner_year
            oof_parts.append(combined)
            fold_inner_audit.append(
                {
                    "inner_year": inner_year,
                    "boundary": inner_fold.audit,
                    "agent_b": b_inner.audit,
                    "agent_c": c_inner.audit,
                }
            )
        if not oof_parts:
            raise ValueError(f"Agent D inner OOF 행이 없습니다: outer_year={outer_year}")
        oof_train = pd.concat(oof_parts, ignore_index=True)

        outer_combined, b_outer, c_outer = _fit_bc_scores(
            outer_train,
            outer_scope,
            b_features,
            c_features,
            payload,
        )
        outer_scored, d_outer = fit_predict_agent_d(oof_train, outer_combined, payload)
        outer_scored["outer_year"] = outer_year
        output_columns = [
            "date",
            "ticker",
            TARGET_COLUMN,
            AGENT_B_PREDICTION_COLUMN,
            AGENT_B_PERCENTILE_COLUMN,
            AGENT_C_PREDICTION_COLUMN,
            AGENT_C_PERCENTILE_COLUMN,
            FUNDAMENTAL_AVAILABLE_COLUMN,
            AGENT_D_PREDICTION_COLUMN,
            AGENT_D_PERCENTILE_COLUMN,
            "outer_year",
        ]
        score_parts.append(outer_scored.loc[:, output_columns])

        valid_metric = outer_scored.dropna(subset=[TARGET_COLUMN]).copy()
        if "label_valid" in valid_metric.columns:
            valid_metric = valid_metric.loc[valid_metric["label_valid"].eq(True)].copy()  # noqa: E712
        for agent, score_column in (
            ("B_ONLY", AGENT_B_PERCENTILE_COLUMN),
            ("C_ONLY", AGENT_C_PERCENTILE_COLUMN),
            ("D_SOFT_FUSION", AGENT_D_PERCENTILE_COLUMN),
        ):
            metric_rows.append(
                {
                    "outer_year": outer_year,
                    "agent": agent,
                    "train_cutoff": outer_fold.train_dates[-1] if outer_fold.train_dates else None,
                    "training_rows": int(len(outer_train)),
                    "evaluation_rows": int(len(valid_metric)),
                    "inner_oof_rows": int(len(oof_train)),
                    "rank_ic": _mean_daily_rank_ic(valid_metric, score_column),
                    "per_date_top_n_target_mean": per_date_top_n_metric(
                        valid_metric,
                        score_column,
                        TARGET_COLUMN,
                        top_n,
                    ),
                    "top_n": top_n,
                    "purged_dates": len(outer_fold.purged_dates),
                    "embargoed_dates": len(outer_fold.embargoed_dates),
                }
            )
        outer_models[str(outer_year)] = {
            "agent_b": b_outer.estimator,
            "agent_c": c_outer.estimator,
            "agent_d": d_outer.estimator,
        }
        outer_audit[str(outer_year)] = {
            "boundary": outer_fold.audit,
            "agent_b": b_outer.audit,
            "agent_c": c_outer.audit,
            "agent_d": d_outer.audit,
        }
        inner_audit[str(outer_year)] = fold_inner_audit

    if not score_parts:
        raise ValueError("생성된 outer walk-forward 점수가 없습니다.")
    scores = pd.concat(score_parts, ignore_index=True).sort_values(
        ["date", "ticker"], kind="stable"
    ).reset_index(drop=True)
    fold_metrics = pd.DataFrame(metric_rows).sort_values(
        ["outer_year", "agent"], kind="stable"
    ).reset_index(drop=True)
    model_state: dict[str, Any] = {
        "feature_contract": {
            "agent_b": list(b_features),
            "agent_c": list(c_features),
            "agent_d": list(AGENT_D_FEATURE_COLUMNS),
        },
        "outer_models": outer_models,
        "outer_audit": outer_audit,
        "inner_audit": inner_audit,
        "oof_only_fusion": True,
        "hard_fundamental_gate": False,
    }
    return scores, fold_metrics, model_state


__all__ = [
    "AGENT_B_PERCENTILE_COLUMN",
    "AGENT_B_PREDICTION_COLUMN",
    "AGENT_C_PERCENTILE_COLUMN",
    "AGENT_C_PREDICTION_COLUMN",
    "AGENT_C_FEATURE_COLUMNS",
    "AGENT_D_FEATURE_COLUMNS",
    "AGENT_D_PERCENTILE_COLUMN",
    "AGENT_D_PREDICTION_COLUMN",
    "FUNDAMENTAL_AVAILABLE_COLUMN",
    "FittedAgent",
    "OOF_FLAG_COLUMN",
    "PurgedEmbargoFold",
    "TARGET_COLUMN",
    "attach_neutral_agent_b_scores",
    "agent_b_feature_columns",
    "agent_c_feature_columns",
    "build_purged_embargo_fold",
    "daily_percentile",
    "fit_predict_agent_b",
    "fit_predict_agent_c",
    "fit_predict_agent_d",
    "generate_walk_forward_scores",
    "make_agent_b_model",
    "make_agent_c_model",
    "make_agent_d_model",
    "per_date_top_n_metric",
    "per_date_top_n_rows",
]
