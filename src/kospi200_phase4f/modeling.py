"""Phase 4F model-only OOF selection and immutable model bundle.

Phase 4F는 라벨이 완성된 2020년 이하 자료로 B/C/D를 적합하고 실제
estimator를 동결한다. 포트폴리오 규칙과 체결은 이 계층의 책임이 아니다.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import pickle
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from kospi200_phase5s.modeling import (
    AGENT_B_PERCENTILE_COLUMN,
    AGENT_B_PREDICTION_COLUMN,
    AGENT_C_PERCENTILE_COLUMN,
    AGENT_C_PREDICTION_COLUMN,
    AGENT_D_FEATURE_COLUMNS,
    AGENT_D_PERCENTILE_COLUMN,
    AGENT_D_PREDICTION_COLUMN,
    FUNDAMENTAL_AVAILABLE_COLUMN,
    OOF_FLAG_COLUMN,
    TARGET_COLUMN,
    agent_b_feature_columns,
    agent_c_feature_columns,
    attach_neutral_agent_b_scores,
    build_purged_embargo_fold,
    daily_percentile,
    fit_predict_agent_b,
    fit_predict_agent_c,
    fit_predict_agent_d,
    per_date_top_n_rows,
)


SCHEMA_VERSION = "v2-phase4f-share-change-safe-frozen-model-bundle-v1"
FREEZE_DATE = "2020-12-30"
OOF_YEARS = (2017, 2018, 2019, 2020)
SELECTION_YEARS = (2019, 2020)
PURGE_SESSIONS = 20

PRIMARY_B = "B_ONLY"
PRIMARY_C = "C_ONLY"
PRIMARY_D = "D_SOFT_FUSION"
PRIMARY_AGENTS = (PRIMARY_B, PRIMARY_C, PRIMARY_D)


@dataclass(frozen=True)
class FrozenModelBundle:
    """Phase 5가 pickle로 읽고 predict만 수행하는 실제 모델 상태."""

    schema_version: str
    freeze_date: str
    primary_agent: str
    agent_b_estimator: Pipeline
    agent_c_estimator: Pipeline
    agent_d_estimator: Pipeline
    agent_b_features: tuple[str, ...]
    agent_c_features: tuple[str, ...]
    agent_d_features: tuple[str, ...]
    selection_metrics: tuple[dict[str, Any], ...]
    audit: dict[str, Any]
    selection_oof_scores: tuple[dict[str, Any], ...] = ()


def _canonical_value(value: Any) -> Any:
    """numpy/pandas 값을 strict canonical JSON에 안전한 값으로 바꾼다."""

    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if np.isfinite(number) else None
    if value is None or pd.isna(value):
        return None
    return value


def bundle_state_hashes(bundle: FrozenModelBundle) -> dict[str, Any]:
    """실제 estimator bytes와 동결 모델 계약의 canonical hash를 반환한다."""

    components = {
        "agent_b": bundle.agent_b_estimator,
        "agent_c": bundle.agent_c_estimator,
        "agent_d": bundle.agent_d_estimator,
    }
    component_sha256 = {
        name: hashlib.sha256(pickle.dumps(estimator, protocol=5)).hexdigest()
        for name, estimator in components.items()
    }
    state = {
        "schema_version": bundle.schema_version,
        "freeze_date": bundle.freeze_date,
        "primary_agent": bundle.primary_agent,
        "feature_orders": {
            "agent_b": list(bundle.agent_b_features),
            "agent_c": list(bundle.agent_c_features),
            "agent_d": list(bundle.agent_d_features),
        },
        "selection_metrics": _canonical_value(bundle.selection_metrics),
        "component_sha256": component_sha256,
    }
    canonical = json.dumps(
        state,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return {
        "component_sha256": component_sha256,
        "model_state_hash": hashlib.sha256(canonical).hexdigest(),
    }


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], context: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"{context} 필수 열 누락: {missing}")


def _date_text(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="raise").dt.date.astype(str)


def validate_fit_boundary(
    frame: pd.DataFrame,
    *,
    maximum_signal_date: str = FREEZE_DATE,
    maximum_exit_date: str = FREEZE_DATE,
) -> dict[str, Any]:
    """모든 fit 직전에 신호일·라벨 완성일의 상한을 fail-closed 검증한다."""

    _require_columns(frame, ["date", "exit_date", "label_valid", TARGET_COLUMN], "fit 입력")
    if frame.empty:
        raise ValueError("fit 입력이 비었습니다.")
    dates = _date_text(frame["date"])
    exits = _date_text(frame["exit_date"])
    if not frame["label_valid"].eq(True).all():  # noqa: E712 - 명시적 유효 라벨
        raise ValueError("fit 입력에는 완성된 유효 라벨만 허용합니다.")
    target = pd.to_numeric(frame[TARGET_COLUMN], errors="raise")
    if target.isna().any() or not np.isfinite(target).all():
        raise ValueError("fit 입력 target이 완전하지 않습니다.")
    if dates.gt(str(maximum_signal_date)).any():
        raise ValueError(f"fit 입력에 {maximum_signal_date} 이후 신호행이 있습니다.")
    if exits.gt(str(maximum_exit_date)).any():
        raise ValueError(f"fit 입력에 {maximum_exit_date} 이후 완성 라벨이 있습니다.")
    return {
        "rows": int(len(frame)),
        "signal_min": str(dates.min()),
        "signal_max": str(dates.max()),
        "exit_max": str(exits.max()),
    }


def _fundamental_available(frame: pd.DataFrame, features: Sequence[str]) -> pd.Series:
    if FUNDAMENTAL_AVAILABLE_COLUMN in frame.columns:
        values = pd.to_numeric(frame[FUNDAMENTAL_AVAILABLE_COLUMN], errors="raise")
        if not values.isin([0.0, 1.0]).all():
            raise ValueError("fundamental_available은 0 또는 1이어야 합니다.")
        return values.eq(1.0)
    return frame.loc[:, list(features)].notna().any(axis=1)


def _b_frame(frame: pd.DataFrame, features: Sequence[str]) -> pd.DataFrame:
    mask = _fundamental_available(frame, features)
    columns = ["date", "ticker", "exit_date", "label_valid", TARGET_COLUMN, *features]
    return frame.loc[mask, columns].copy()


def _c_frame(frame: pd.DataFrame, features: Sequence[str]) -> pd.DataFrame:
    columns = ["date", "ticker", "exit_date", "label_valid", TARGET_COLUMN, *features]
    return frame.loc[:, columns].copy()


def _empty_b_scores(scope: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.Series(dtype=scope["date"].dtype),
            "ticker": pd.Series(dtype=scope["ticker"].dtype),
            AGENT_B_PREDICTION_COLUMN: pd.Series(dtype=float),
            AGENT_B_PERCENTILE_COLUMN: pd.Series(dtype=float),
        }
    )


def _fit_bc_oof(
    train: pd.DataFrame,
    scope: pd.DataFrame,
    b_features: Sequence[str],
    c_features: Sequence[str],
    config: Mapping[str, Any] | object | None,
    *,
    fit_signal_max: str,
    fit_exit_max: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    boundary = validate_fit_boundary(
        train,
        maximum_signal_date=fit_signal_max,
        maximum_exit_date=fit_exit_max,
    )
    b_train = _b_frame(train, b_features)
    b_scope = _b_frame(scope, b_features)
    if b_train.empty:
        raise ValueError("Agent B fit에 Fundamental 가용 행이 없습니다.")
    if b_scope.empty:
        b_scored = _empty_b_scores(scope)
        _, b_fit = fit_predict_agent_b(b_train, b_train.iloc[:1], b_features, config)
    else:
        b_scored, b_fit = fit_predict_agent_b(b_train, b_scope, b_features, config)

    c_train = _c_frame(train, c_features)
    c_scope = _c_frame(scope, c_features)
    c_scored, c_fit = fit_predict_agent_c(c_train, c_scope, c_features, config)
    combined = attach_neutral_agent_b_scores(c_scored, b_scored)
    return combined, {
        "fit_boundary": boundary,
        "agent_b": b_fit.audit,
        "agent_c": c_fit.audit,
        "agent_b_estimator": b_fit.estimator,
        "agent_c_estimator": c_fit.estimator,
    }


def _valid_complete_mask(frame: pd.DataFrame, maximum_exit_date: str) -> pd.Series:
    exits = _date_text(frame["exit_date"])
    target = pd.to_numeric(frame[TARGET_COLUMN], errors="coerce")
    return frame["label_valid"].eq(True) & exits.le(maximum_exit_date) & target.notna()  # noqa: E712


def _year_bounds(frame: pd.DataFrame, year: int) -> tuple[str, str]:
    dates = frame.loc[frame["date"].str[:4].eq(str(int(year))), "date"]
    if dates.empty:
        raise ValueError(f"OOF 평가 연도 행이 없습니다: {year}")
    return str(dates.min()), str(dates.max())


def _daily_rank_ic(frame: pd.DataFrame, score_column: str) -> pd.Series:
    values: dict[str, float] = {}
    for day, group in frame.dropna(subset=[score_column, TARGET_COLUMN]).groupby("date", sort=False):
        if len(group) < 2 or group[score_column].nunique() < 2 or group[TARGET_COLUMN].nunique() < 2:
            continue
        score_rank = group[score_column].rank(method="average")
        target_rank = group[TARGET_COLUMN].rank(method="average")
        values[str(day)] = float(score_rank.corr(target_rank))
    return pd.Series(values, dtype=float)


def _valid_metric_mask(frame: pd.DataFrame) -> pd.Series:
    _require_columns(frame, ["exit_date", "label_valid", TARGET_COLUMN], "metric 입력")
    target = pd.to_numeric(frame[TARGET_COLUMN], errors="coerce")
    exits = _date_text(frame["exit_date"])
    return (
        frame["label_valid"].eq(True)  # noqa: E712 - 명시적 유효 라벨
        & exits.le(FREEZE_DATE)
        & target.notna()
        & np.isfinite(target)
    )


def _mean_top_n_quality_without_label_leak(
    score_universe: pd.DataFrame,
    score_column: str,
    top_n: int,
) -> float:
    """전체 U_t에서 Top N을 먼저 고정한 뒤 유효 라벨만 metric에 쓴다."""

    selected = per_date_top_n_rows(score_universe, score_column, int(top_n))
    if selected.empty:
        return float("nan")
    valid = selected.loc[_valid_metric_mask(selected)].copy()
    if valid.empty:
        return float("nan")
    valid[TARGET_COLUMN] = pd.to_numeric(valid[TARGET_COLUMN], errors="raise")
    daily = valid.groupby("date", sort=False)[TARGET_COLUMN].mean()
    return float(daily.mean()) if not daily.empty else float("nan")


def selection_metric_table(
    scored: pd.DataFrame,
    *,
    selection_years: Sequence[int] = SELECTION_YEARS,
    top_n: int = 10,
) -> pd.DataFrame:
    """2019~2020의 예측지표만 계산하고 포트폴리오 결과는 읽지 않는다."""

    required = [
        "date",
        "ticker",
        "exit_date",
        "oof_year",
        "label_valid",
        OOF_FLAG_COLUMN,
        TARGET_COLUMN,
        AGENT_B_PERCENTILE_COLUMN,
        AGENT_C_PERCENTILE_COLUMN,
        AGENT_D_PERCENTILE_COLUMN,
    ]
    _require_columns(scored, required, "selection OOF 점수")
    scope = scored.loc[scored["oof_year"].isin([int(value) for value in selection_years])].copy()
    if scope.empty:
        raise ValueError("selection OOF 점수가 비었습니다.")
    if scope[OOF_FLAG_COLUMN].isna().any() or not scope[OOF_FLAG_COLUMN].eq(True).all():  # noqa: E712
        raise ValueError("selection metric에는 OOF 점수만 허용합니다.")
    metric_scope = scope.loc[_valid_metric_mask(scope)].copy()
    rows: list[dict[str, Any]] = []
    for agent, score_column in (
        (PRIMARY_B, AGENT_B_PERCENTILE_COLUMN),
        (PRIMARY_C, AGENT_C_PERCENTILE_COLUMN),
        (PRIMARY_D, AGENT_D_PERCENTILE_COLUMN),
    ):
        daily = _daily_rank_ic(metric_scope, score_column)
        yearly_values: list[float] = []
        for year in selection_years:
            prefix = str(int(year))
            year_ic = daily.loc[daily.index.str[:4] == prefix]
            yearly_values.append(float(year_ic.mean()) if not year_ic.empty else float("nan"))
        finite_years = [value for value in yearly_values if np.isfinite(value)]
        rows.append(
            {
                "agent": agent,
                "mean_rank_ic": float(daily.mean()) if not daily.empty else float("nan"),
                "nonnegative_years": int(sum(value >= 0 for value in finite_years)),
                "evaluated_years": int(len(finite_years)),
                "mean_top10_target_quality": _mean_top_n_quality_without_label_leak(
                    scope,
                    score_column,
                    int(top_n),
                ),
            }
        )
    return pd.DataFrame(rows)


def _metric_value(row: pd.Series, column: str) -> float:
    value = float(row[column])
    return value if np.isfinite(value) else float("-inf")


def select_primary_agent(metrics: pd.DataFrame) -> str:
    """최선 단독 후보를 정한 뒤 엄격한 D 개선 조건을 적용한다."""

    _require_columns(
        metrics,
        [
            "agent",
            "mean_rank_ic",
            "nonnegative_years",
            "mean_top10_target_quality",
            "evaluated_years",
        ],
        "모델 선택 metric",
    )
    if set(metrics["agent"]) != set(PRIMARY_AGENTS) or metrics["agent"].duplicated().any():
        raise ValueError("B_ONLY/C_ONLY/D_SOFT_FUSION metric이 각각 하나씩 필요합니다.")
    by_agent = metrics.set_index("agent")
    candidates = by_agent.loc[[PRIMARY_B, PRIMARY_C]].copy()
    candidates["fixed_tie_priority"] = [0, 1]  # 완전 동률이면 full-universe C 우선
    candidates = candidates.sort_values(
        ["mean_rank_ic", "nonnegative_years", "mean_top10_target_quality", "fixed_tie_priority"],
        ascending=[False, False, False, False],
        kind="stable",
        na_position="last",
    )
    best_single_name = str(candidates.index[0])
    best_single = by_agent.loc[best_single_name]
    d = by_agent.loc[PRIMARY_D]
    d_eligible = (
        int(d["evaluated_years"]) == len(SELECTION_YEARS)
        and int(best_single["evaluated_years"]) == len(SELECTION_YEARS)
        and np.isfinite(float(d["mean_rank_ic"]))
        and np.isfinite(float(best_single["mean_rank_ic"]))
        and np.isfinite(float(d["mean_top10_target_quality"]))
        and np.isfinite(float(best_single["mean_top10_target_quality"]))
        and _metric_value(d, "mean_rank_ic") > _metric_value(best_single, "mean_rank_ic")
        and int(d["nonnegative_years"]) >= int(best_single["nonnegative_years"])
        and _metric_value(d, "mean_top10_target_quality")
        >= _metric_value(best_single, "mean_top10_target_quality")
    )
    return PRIMARY_D if d_eligible else best_single_name


def _selection_oof_records(scored: pd.DataFrame) -> tuple[dict[str, Any], ...]:
    columns = (
        "date",
        "ticker",
        "exit_date",
        "label_valid",
        "oof_year",
        OOF_FLAG_COLUMN,
        TARGET_COLUMN,
        AGENT_B_PREDICTION_COLUMN,
        AGENT_B_PERCENTILE_COLUMN,
        AGENT_C_PREDICTION_COLUMN,
        AGENT_C_PERCENTILE_COLUMN,
        AGENT_D_PREDICTION_COLUMN,
        AGENT_D_PERCENTILE_COLUMN,
        FUNDAMENTAL_AVAILABLE_COLUMN,
    )
    _require_columns(scored, columns, "selection OOF 감사 점수")
    ordered = scored.loc[:, list(columns)].sort_values(
        ["date", "ticker"], kind="stable"
    )
    return tuple(
        {str(key): _canonical_value(value) for key, value in record.items()}
        for record in ordered.to_dict(orient="records")
    )


def _score_oof_bc(
    panel: pd.DataFrame,
    sessions: Sequence[str],
    year: int,
    b_features: Sequence[str],
    c_features: Sequence[str],
    config: Mapping[str, Any] | object | None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    start, end = _year_bounds(panel, year)
    fold = build_purged_embargo_fold(
        panel,
        sessions,
        start,
        end,
        purge_sessions=PURGE_SESSIONS,
        embargo_sessions=PURGE_SESSIONS,
    )
    train_mask = fold.train_mask & _valid_complete_mask(panel, start)
    train_mask &= _date_text(panel["exit_date"]).lt(start)
    # 미래 label availability가 현재 점수·percentile 모집단을 바꾸지 않도록
    # evaluation 시점의 전체 eligible U_t를 그대로 점수화한다.
    scope_mask = fold.evaluation_mask
    train = panel.loc[train_mask].copy()
    scope = panel.loc[scope_mask].copy()
    if train.empty or scope.empty:
        raise ValueError(f"OOF {year} 학습 또는 eligible 평가행이 없습니다.")
    scored, fit_audit = _fit_bc_oof(
        train,
        scope,
        b_features,
        c_features,
        config,
        fit_signal_max=fold.train_dates[-1],
        fit_exit_max=start,
    )
    scored[OOF_FLAG_COLUMN] = True
    scored["oof_year"] = int(year)
    return scored, {"year": int(year), "fold": fold.audit, **fit_audit}


def fit_frozen_model_bundle(
    panel: pd.DataFrame,
    sessions: Sequence[object],
    config: Mapping[str, Any] | object | None = None,
) -> FrozenModelBundle:
    """2017~2020 B/C OOF, nested D 선택 후 2020 cutoff bundle을 적합한다."""

    b_features = agent_b_feature_columns()
    c_features = agent_c_feature_columns()
    required = [
        "date",
        "ticker",
        "exit_date",
        "label_valid",
        TARGET_COLUMN,
        *b_features,
        *c_features,
    ]
    _require_columns(panel, required, "Phase 4F model panel")
    if panel.duplicated(["date", "ticker"]).any():
        raise ValueError("Phase 4F model panel date/ticker가 중복됩니다.")
    working = panel.copy()
    working["date"] = _date_text(working["date"])
    working["exit_date"] = _date_text(working["exit_date"])
    ordered_sessions = tuple(str(value) for value in sessions)
    if ordered_sessions != tuple(sorted(set(ordered_sessions))):
        raise ValueError("sessions는 중복 없는 오름차순이어야 합니다.")

    oof_parts: list[pd.DataFrame] = []
    oof_audits: list[dict[str, Any]] = []
    for year in OOF_YEARS:
        part, audit = _score_oof_bc(
            working,
            ordered_sessions,
            year,
            b_features,
            c_features,
            config,
        )
        oof_parts.append(part)
        oof_audits.append(audit)
    bc_oof = pd.concat(oof_parts, ignore_index=True)

    d_selection_parts: list[pd.DataFrame] = []
    d_selection_audits: list[dict[str, Any]] = []
    for year in SELECTION_YEARS:
        selection_start, _ = _year_bounds(bc_oof, year)
        d_train_pool = bc_oof.loc[bc_oof["oof_year"].lt(year)].copy()
        d_train_mask = _valid_complete_mask(d_train_pool, selection_start)
        d_train_mask &= _date_text(d_train_pool["exit_date"]).lt(selection_start)
        d_train = d_train_pool.loc[d_train_mask].copy()
        d_scope = bc_oof.loc[bc_oof["oof_year"].eq(year)].copy()
        if d_train.empty or d_scope.empty:
            raise ValueError(f"Agent D {year} OOF 학습 또는 평가행이 없습니다.")
        validate_fit_boundary(
            d_train,
            maximum_signal_date=selection_start,
            maximum_exit_date=selection_start,
        )
        d_scored, d_fit = fit_predict_agent_d(d_train, d_scope, config)
        d_scored["oof_year"] = year
        d_selection_parts.append(d_scored)
        d_selection_audits.append(
            {
                "year": year,
                "meta_training_oof_years": sorted(
                    int(value) for value in d_train["oof_year"].unique()
                ),
                **d_fit.audit,
            }
        )
    selection_scores = pd.concat(d_selection_parts, ignore_index=True)
    metrics = selection_metric_table(selection_scores)
    primary = select_primary_agent(metrics)

    final_mask = _valid_complete_mask(working, FREEZE_DATE)
    final_mask &= working["date"].le(FREEZE_DATE)
    final_train = working.loc[final_mask].copy()
    final_boundary = validate_fit_boundary(final_train)
    final_bc_scored, final_bc = _fit_bc_oof(
        final_train,
        final_train,
        b_features,
        c_features,
        config,
        fit_signal_max=FREEZE_DATE,
        fit_exit_max=FREEZE_DATE,
    )
    all_oof = bc_oof.copy()
    all_oof[OOF_FLAG_COLUMN] = True
    final_d_mask = _valid_complete_mask(all_oof, FREEZE_DATE)
    final_d_train = all_oof.loc[final_d_mask].copy()
    final_d_boundary = validate_fit_boundary(final_d_train)
    _, final_d = fit_predict_agent_d(final_d_train, final_bc_scored, config)

    metric_records = tuple(metrics.to_dict(orient="records"))
    selection_oof_records = _selection_oof_records(selection_scores)
    audit: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "model_only": True,
        "portfolio_accessed": False,
        "freeze_date": FREEZE_DATE,
        "oof_years": list(OOF_YEARS),
        "selection_years": list(SELECTION_YEARS),
        "oof_roles": {
            "d_meta_training": [2017, 2018],
            "model_selection": list(SELECTION_YEARS),
        },
        "selection_oof_score_rows": int(len(selection_oof_records)),
        "selection_oof_nonmetric_rows_retained": int(
            (~_valid_metric_mask(selection_scores)).sum()
        ),
        "selection_uses_portfolio_metrics": False,
        "primary_agent": primary,
        "final_fit_boundary": final_boundary,
        "oof_folds": [
            {
                key: value
                for key, value in item.items()
                if key not in {"agent_b_estimator", "agent_c_estimator"}
            }
            for item in oof_audits
        ],
        "d_selection_audit": d_selection_audits,
        "agent_b": final_bc["agent_b"],
        "agent_c": final_bc["agent_c"],
        "agent_d": final_d.audit,
        "agent_d_fit_boundary": final_d_boundary,
        "final_oos_accessed": False,
    }
    return FrozenModelBundle(
        schema_version=SCHEMA_VERSION,
        freeze_date=FREEZE_DATE,
        primary_agent=primary,
        agent_b_estimator=final_bc["agent_b_estimator"],
        agent_c_estimator=final_bc["agent_c_estimator"],
        agent_d_estimator=final_d.estimator,
        agent_b_features=tuple(b_features),
        agent_c_features=tuple(c_features),
        agent_d_features=tuple(AGENT_D_FEATURE_COLUMNS),
        selection_metrics=metric_records,
        audit=audit,
        selection_oof_scores=selection_oof_records,
    )


def _numeric(frame: pd.DataFrame, columns: Sequence[str], context: str) -> pd.DataFrame:
    _require_columns(frame, columns, context)
    values = frame.loc[:, list(columns)].apply(pd.to_numeric, errors="raise")
    if np.isinf(values.to_numpy(dtype=float, na_value=np.nan)).any():
        raise ValueError(f"{context} Feature에 무한대가 있습니다.")
    return values


def predict_frozen_bundle(
    bundle: FrozenModelBundle,
    score_panel: pd.DataFrame,
    *,
    include_controls: bool = True,
) -> pd.DataFrame:
    """동결 estimator의 predict만 호출하며 선택 모델만 계산할 수도 있다."""

    if bundle.schema_version != SCHEMA_VERSION:
        raise ValueError("Phase 4F FrozenModelBundle schema가 다릅니다.")
    if bundle.primary_agent not in PRIMARY_AGENTS:
        raise ValueError("FrozenModelBundle primary agent가 유효하지 않습니다.")
    if not isinstance(include_controls, bool):
        raise TypeError("include_controls는 bool이어야 합니다.")
    _require_columns(
        score_panel,
        ["date", "ticker", *bundle.agent_b_features, *bundle.agent_c_features],
        "frozen predict panel",
    )
    output_base = score_panel.copy()
    output_base["date"] = _date_text(output_base["date"])
    if output_base.duplicated(["date", "ticker"]).any():
        raise ValueError("frozen predict panel date/ticker가 중복됩니다.")

    need_b = bool(include_controls or bundle.primary_agent in {PRIMARY_B, PRIMARY_D})
    need_c = bool(include_controls or bundle.primary_agent in {PRIMARY_C, PRIMARY_D})
    need_d = bool(include_controls or bundle.primary_agent == PRIMARY_D)

    combined = output_base[["date", "ticker"]].copy()
    if need_c:
        combined[AGENT_C_PREDICTION_COLUMN] = bundle.agent_c_estimator.predict(
            _numeric(output_base, bundle.agent_c_features, "Agent C frozen predict")
        )
        combined = daily_percentile(
            combined,
            AGENT_C_PREDICTION_COLUMN,
            AGENT_C_PERCENTILE_COLUMN,
        )

    if need_b:
        b_available = _fundamental_available(output_base, bundle.agent_b_features)
        b_input = output_base.loc[b_available].copy()
        if b_input.empty:
            b_scored = _empty_b_scores(output_base)
        else:
            b_scored = b_input[["date", "ticker"]].copy()
            b_scored[AGENT_B_PREDICTION_COLUMN] = bundle.agent_b_estimator.predict(
                _numeric(b_input, bundle.agent_b_features, "Agent B frozen predict")
            )
            b_scored = daily_percentile(
                b_scored,
                AGENT_B_PREDICTION_COLUMN,
                AGENT_B_PERCENTILE_COLUMN,
            )
        combined = attach_neutral_agent_b_scores(combined, b_scored)

    if need_d:
        combined[AGENT_D_PREDICTION_COLUMN] = bundle.agent_d_estimator.predict(
            _numeric(combined, bundle.agent_d_features, "Agent D frozen predict")
        )
        combined = daily_percentile(
            combined,
            AGENT_D_PREDICTION_COLUMN,
            AGENT_D_PERCENTILE_COLUMN,
        )
    percentile_by_agent = {
        PRIMARY_B: AGENT_B_PERCENTILE_COLUMN,
        PRIMARY_C: AGENT_C_PERCENTILE_COLUMN,
        PRIMARY_D: AGENT_D_PERCENTILE_COLUMN,
    }
    combined["primary_agent"] = bundle.primary_agent
    combined["primary_percentile"] = combined[percentile_by_agent[bundle.primary_agent]]
    return combined


__all__ = [
    "FREEZE_DATE",
    "FrozenModelBundle",
    "OOF_YEARS",
    "PRIMARY_B",
    "PRIMARY_C",
    "PRIMARY_D",
    "SCHEMA_VERSION",
    "SELECTION_YEARS",
    "bundle_state_hashes",
    "fit_frozen_model_bundle",
    "predict_frozen_bundle",
    "select_primary_agent",
    "selection_metric_table",
    "validate_fit_boundary",
]
