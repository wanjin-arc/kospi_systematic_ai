from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from kospi100_backtest.costs import CostSchedule
from kospi100_baseline.features import _feature_segments
from kospi100_features.features import build_feature_matrix
from kospi100_features.labels import _adjusted_open
from kospi100_multifactor.modeling import _preprocessor_state, _transform
from kospi100_ranking.data import SelectionBundle
from kospi100_ranking.modeling import fold_dates

from .config import MODEL_CONTRACT, MultiHorizonConfig


def target_name(horizon: int) -> str:
    return f"forward_cost_adjusted_excess_log_return_{horizon}"


@dataclass(frozen=True)
class PreparedMultiHorizonResearch:
    frame: pd.DataFrame
    audit: dict[str, object]


@dataclass(frozen=True)
class MultiHorizonModelResult:
    predictions: pd.DataFrame
    metrics: pd.DataFrame
    fold_audit: pd.DataFrame


def _tax_rates(exit_dates: pd.Series, schedule: CostSchedule) -> pd.Series:
    cache: dict[object, float] = {}
    values: list[float] = []
    for value in exit_dates:
        session = pd.Timestamp(value).date()
        if session not in cache:
            transaction, rural = schedule.rates_on(session)
            cache[session] = float(transaction + rural)
        values.append(cache[session])
    return pd.Series(values, index=exit_dates.index, dtype=float)


def attach_multihorizon_targets(
    feature_frame: pd.DataFrame,
    full_history: pd.DataFrame,
    index: pd.DataFrame,
    actions: pd.DataFrame,
    config: MultiHorizonConfig,
) -> tuple[pd.DataFrame, dict[str, object]]:
    calendar = index[["date", "open"]].copy().sort_values("date", kind="mergesort").reset_index(drop=True)
    calendar["entry_date"] = calendar["date"].shift(-1)
    signals = feature_frame.copy().merge(
        calendar.set_index("date")[["entry_date"]], left_on="date", right_index=True,
        how="left", validate="many_to_one",
    )
    history = full_history.copy().sort_values(["security_id", "date"], kind="mergesort").reset_index(drop=True)
    history["feature_segment"] = _feature_segments(history, actions)
    history["adjusted_open"] = _adjusted_open(history, actions)
    if history.duplicated(["security_id", "date"]).any():
        raise ValueError("일별 가격에 종목-날짜 중복이 있습니다")
    lookup = history[["security_id", "date", "adjusted_open", "tradable", "feature_segment"]]
    entry = lookup.rename(columns={
        "date": "entry_date", "adjusted_open": "entry_open",
        "tradable": "entry_tradable", "feature_segment": "entry_segment",
    })
    signals = signals.merge(entry, on=["security_id", "entry_date"], how="left", validate="many_to_one")
    index_open = calendar.set_index("date")["open"]
    signals["index_entry_open"] = signals["entry_date"].map(index_open)
    schedule = CostSchedule.from_csv(config.base.tax_schedule_path)
    target_rows: dict[str, int] = {}
    for horizon in config.horizons:
        exit_date = f"exit_date_{horizon}"
        exit_open = f"exit_open_{horizon}"
        exit_tradable = f"exit_tradable_{horizon}"
        exit_segment = f"exit_segment_{horizon}"
        index_exit_open = f"index_exit_open_{horizon}"
        calendar[exit_date] = calendar["date"].shift(-(horizon + 1))
        signals = signals.merge(
            calendar.set_index("date")[[exit_date]], left_on="date", right_index=True,
            how="left", validate="many_to_one",
        )
        exit_frame = lookup.rename(columns={
            "date": exit_date, "adjusted_open": exit_open,
            "tradable": exit_tradable, "feature_segment": exit_segment,
        })
        signals = signals.merge(exit_frame, on=["security_id", exit_date], how="left", validate="many_to_one")
        signals[index_exit_open] = signals[exit_date].map(index_open)
        same_segment = (
            signals["feature_segment"].eq(signals["entry_segment"])
            & signals["feature_segment"].eq(signals[exit_segment])
        )
        valid = (
            signals["phase4_eligible"]
            & signals["entry_tradable"].astype("boolean").fillna(False)
            & signals[exit_tradable].astype("boolean").fillna(False)
            & same_segment
            & signals[["entry_open", exit_open, "index_entry_open", index_exit_open]].notna().all(axis=1)
            & signals["date"].between(pd.Timestamp("2011-01-01"), pd.Timestamp("2018-12-31"))
        )
        gross = (
            np.log(signals.loc[valid, exit_open] / signals.loc[valid, "entry_open"])
            - np.log(signals.loc[valid, index_exit_open] / signals.loc[valid, "index_entry_open"])
        )
        tax = _tax_rates(signals.loc[valid, exit_date], schedule)
        commission = float(config.base.commission_rate)
        slippage = float(config.base.slippage_rate)
        factor = ((1.0 - slippage) * (1.0 - commission - tax)) / (
            (1.0 + slippage) * (1.0 + commission)
        )
        name = target_name(horizon)
        signals[name] = np.nan
        signals.loc[valid, name] = gross + np.log(factor)
        target_rows[name] = int(signals[name].notna().sum())
    complete = signals[[target_name(value) for value in config.horizons]].notna().all(axis=1)
    timing = signals.loc[complete, "date"].lt(signals.loc[complete, "entry_date"])
    for horizon in config.horizons:
        timing &= signals.loc[complete, "entry_date"].lt(signals.loc[complete, f"exit_date_{horizon}"])
    if not timing.all():
        raise AssertionError("다중 기간 label 시점 불변조건을 위반했습니다")
    return signals, {
        "horizons": list(config.horizons), "entry_offset_sessions": 1,
        "exit_offsets_sessions": [value + 1 for value in config.horizons],
        "target_rows": target_rows, "complete_all_horizons_rows": int(complete.sum()),
        "cost_adjusted": True, "same_day_execution": False,
        "corporate_action_reset_enforced": True,
    }


def prepare_frame(bundle: SelectionBundle, config: MultiHorizonConfig) -> PreparedMultiHorizonResearch:
    features = build_feature_matrix(bundle.feature_panel, bundle.index, bundle.corporate_actions)
    labeled, target_audit = attach_multihorizon_targets(
        features.cross_sectional, bundle.full_history, bundle.index, bundle.corporate_actions, config
    )
    targets = [target_name(value) for value in config.horizons]
    eligible = labeled.loc[labeled["phase4_eligible"] & labeled[targets].notna().all(axis=1)].copy()
    counts = eligible.groupby("date", sort=False)["security_id"].transform("size")
    eligible = eligible.loc[counts >= config.base.minimum_cross_section].copy()
    rank_columns: list[str] = []
    for name in config.base.stock_features:
        column = f"rank__{name}"
        eligible[column] = eligible.groupby("date", sort=False)[name].rank(method="average", pct=True)
        rank_columns.append(column)
    regime = features.regime[["date", *config.base.regime_features]].copy()
    eligible = eligible.merge(regime, on="date", how="left", validate="many_to_one")
    columns = [
        "date", "entry_date", "security_id", "membership_spell_id", "close",
        *targets, *rank_columns, *config.base.regime_features,
    ]
    result = eligible[columns].sort_values(["date", "security_id"], kind="mergesort").reset_index(drop=True)
    if result.empty or result["date"].max().date() > config.base.maximum_permitted_date:
        raise PermissionError("Phase 5G 연구 표본의 날짜 경계가 올바르지 않습니다")
    return PreparedMultiHorizonResearch(result, {
        "research_rows": len(result), "research_dates": int(result["date"].nunique()),
        "minimum_signal_date": result["date"].min().date().isoformat(),
        "maximum_signal_date": result["date"].max().date().isoformat(),
        "stock_feature_count": len(config.base.stock_features),
        "regime_feature_count": len(config.base.regime_features),
        "interaction_count": len(config.base.interactions),
        "future_bar_used_for_feature": False, "minute_data_used": False,
        "target_audit": target_audit, "feature_audit": features.audit,
    })


def _fold_metrics(frame: pd.DataFrame, fold: str, config: MultiHorizonConfig) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for horizon in config.horizons:
        actual = frame[target_name(horizon)].to_numpy(dtype=float)
        predicted = frame[f"predicted_net_excess_{horizon}"].to_numpy(dtype=float)
        spearman = pd.Series(predicted).corr(pd.Series(actual), method="spearman")
        rows.append({
            "model": MODEL_CONTRACT, "fold": fold, "validation_year": int(frame["date"].dt.year.iloc[0]),
            "horizon": horizon, "rows": len(frame), "dates": int(frame["date"].nunique()),
            "mae": float(mean_absolute_error(actual, predicted)),
            "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
            "r2": float(r2_score(actual, predicted)),
            "spearman": None if pd.isna(spearman) else float(spearman),
        })
    return rows


def evaluate_model(
    research: PreparedMultiHorizonResearch,
    index: pd.DataFrame,
    config: MultiHorizonConfig,
) -> MultiHorizonModelResult:
    predictions: list[pd.DataFrame] = []
    metrics: list[dict[str, object]] = []
    audits: list[dict[str, object]] = []
    targets = [target_name(value) for value in config.horizons]
    for fold in config.base.folds:
        train_dates, validation_dates = fold_dates(
            index, fold, config.base.purge_sessions, config.base.embargo_sessions
        )
        train = research.frame.loc[research.frame["date"].isin(train_dates)].copy()
        validation = research.frame.loc[research.frame["date"].isin(validation_dates)].copy()
        if train.empty or validation.empty or train["date"].max() >= validation["date"].min():
            raise ValueError(f"안전하지 않은 Phase 5G fold: {fold.name}")
        state = _preprocessor_state(train, config.base)
        x_train, names = _transform(train, state, config.base)
        x_validation, validation_names = _transform(validation, state, config.base)
        if names != validation_names:
            raise AssertionError("Train/Validation 입력 순서가 다릅니다")
        model = ExtraTreesRegressor(
            n_estimators=config.n_estimators, max_depth=config.max_depth,
            min_samples_leaf=config.min_samples_leaf, max_features=config.max_features,
            bootstrap=False, n_jobs=1, random_state=config.base.random_seed,
        ).fit(x_train, train[targets].to_numpy(dtype=float))
        output = validation[["date", "security_id", "membership_spell_id", "close", *targets]].copy()
        values = model.predict(x_validation)
        for position, horizon in enumerate(config.horizons):
            output[f"predicted_net_excess_{horizon}"] = values[:, position]
        output["fold"] = fold.name
        output["model"] = MODEL_CONTRACT
        predictions.append(output)
        metrics.extend(_fold_metrics(output, fold.name, config))
        audits.append({
            "fold": fold.name, "train_min_date": state["fit_min_date"],
            "train_max_date": state["fit_max_date"], "train_rows": len(train),
            "validation_min_date": validation["date"].min().date().isoformat(),
            "validation_max_date": validation["date"].max().date().isoformat(),
            "validation_rows": len(validation), "input_columns": len(names),
            "purge_sessions": config.base.purge_sessions,
            "embargo_sessions": config.base.embargo_sessions,
            "preprocessing_fit_used_validation": False,
            "model_fit_used_validation": False, "post_2018_rows_used": 0,
        })
    combined = pd.concat(predictions, ignore_index=True).sort_values(
        ["fold", "date", "security_id"], kind="mergesort"
    ).reset_index(drop=True)
    return MultiHorizonModelResult(combined, pd.DataFrame(metrics), pd.DataFrame(audits))
