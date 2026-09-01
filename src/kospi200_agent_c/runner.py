"""Agent B Top 30 안에서만 causal OHLCV 진입 후보를 생성한다."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


FORBIDDEN_PARTS = {"sealed", "final_oos_v24"}
FEATURES = (
    "return_1", "return_5", "return_20", "return_60", "volatility_5", "volatility_20",
    "downside_volatility_20", "close_to_ma20", "close_to_ma60", "drawdown_20", "drawdown_60",
    "intraday_range", "volume_ratio_20", "gap_1",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def guard_path(path: Path) -> None:
    if FORBIDDEN_PARTS.intersection(part.casefold() for part in path.parts):
        raise ValueError(f"금지된 OOS 경로입니다: {path}")


def _column(frame: pd.DataFrame, names: tuple[str, ...]) -> str:
    return next(name for name in names if name in frame.columns)


def load_market(root: Path, tickers: set[str], start_year: int, end_year: int) -> tuple[pd.DataFrame, list[str], list[Path]]:
    guard_path(root)
    paths = sorted(path for year in range(start_year, end_year + 1) for path in (root / str(year)).glob("*.csv.gz"))
    if not paths:
        raise FileNotFoundError("허용 기간 market_stk 입력이 없습니다.")
    pieces, sessions = [], []
    for path in paths:
        day = path.stem.split(".")[0]
        date = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
        raw = pd.read_csv(path, compression="gzip", encoding="cp949", dtype=str, keep_default_na=False)
        columns = [
            _column(raw, ("종목코드", "ISU_SRT_CD")), _column(raw, ("시가", "TDD_OPNPRC")),
            _column(raw, ("고가", "TDD_HGPRC")), _column(raw, ("저가", "TDD_LWPRC")),
            _column(raw, ("종가", "TDD_CLSPRC")), _column(raw, ("거래량", "ACC_TRDVOL")),
            _column(raw, ("상장주식수", "LIST_SHRS")),
        ]
        part = raw[columns].copy(); part.columns = ["ticker", "open", "high", "low", "close", "volume", "listed_shares"]
        part["ticker"] = part["ticker"].str.replace(r"\D", "", regex=True).str.zfill(6)
        part = part[part["ticker"].isin(tickers)]
        for column in ("open", "high", "low", "close", "volume", "listed_shares"):
            part[column] = pd.to_numeric(part[column].str.replace(",", "", regex=False), errors="coerce")
        part["date"] = date; pieces.append(part); sessions.append(date)
    return pd.concat(pieces, ignore_index=True).drop_duplicates(["date", "ticker"]), sessions, paths


def compute_technical_features(market: pd.DataFrame) -> pd.DataFrame:
    frame = market.sort_values(["ticker", "date"]).copy()
    ticker_group = frame.groupby("ticker", sort=False)
    share_ratio = frame["listed_shares"] / ticker_group["listed_shares"].shift(1)
    price_ratio = frame["close"] / ticker_group["close"].shift(1)
    mechanical = (share_ratio > 0) & (price_ratio > 0) & (np.abs(np.log(share_ratio)) >= math.log(1.20))
    mechanical &= np.abs(np.log(share_ratio) + np.log(price_ratio)) <= math.log(1.15)
    frame["mechanical_reset"] = mechanical.fillna(False)
    frame["segment"] = frame["mechanical_reset"].groupby(frame["ticker"]).cumsum()
    keys = [frame["ticker"], frame["segment"]]
    group = frame.groupby(keys, sort=False)
    daily_return = group["close"].pct_change(fill_method=None)
    frame["return_1"] = daily_return
    for horizon in (5, 20, 60):
        frame[f"return_{horizon}"] = group["close"].pct_change(horizon, fill_method=None)
    frame["volatility_5"] = daily_return.groupby(keys).rolling(5, min_periods=5).std().reset_index(level=[0, 1], drop=True)
    frame["volatility_20"] = daily_return.groupby(keys).rolling(20, min_periods=20).std().reset_index(level=[0, 1], drop=True)
    downside = daily_return.clip(upper=0)
    frame["downside_volatility_20"] = downside.groupby(keys).rolling(20, min_periods=20).std().reset_index(level=[0, 1], drop=True)
    for horizon in (20, 60):
        mean = group["close"].rolling(horizon, min_periods=horizon).mean().reset_index(level=[0, 1], drop=True)
        peak = group["close"].rolling(horizon, min_periods=horizon).max().reset_index(level=[0, 1], drop=True)
        frame[f"close_to_ma{horizon}"] = frame["close"] / mean - 1.0
        frame[f"drawdown_{horizon}"] = frame["close"] / peak - 1.0
    frame["intraday_range"] = (frame["high"] - frame["low"]) / frame["close"].replace(0, np.nan)
    volume_mean = group["volume"].rolling(20, min_periods=20).mean().reset_index(level=[0, 1], drop=True)
    frame["volume_ratio_20"] = frame["volume"] / volume_mean
    previous_close = group["close"].shift(1)
    frame["gap_1"] = frame["open"] / previous_close - 1.0
    frame.loc[frame["mechanical_reset"], list(FEATURES)] = np.nan
    return frame


def attach_target(frame: pd.DataFrame, market: pd.DataFrame, sessions: list[str], horizon: int, cost: float) -> pd.DataFrame:
    session_index = {date: i for i, date in enumerate(sessions)}
    boundaries = {date: (sessions[i + 1], sessions[i + horizon + 1]) for date, i in session_index.items() if i + horizon + 1 < len(sessions)}
    opens = market.set_index(["date", "ticker"])["open"]
    entry, exit_ = [], []
    for row in frame[["date", "ticker"]].itertuples(index=False):
        pair = boundaries.get(str(row.date))
        if pair is None:
            entry.append(np.nan); exit_.append(np.nan); continue
        entry.append(opens.get((pair[0], str(row.ticker)), np.nan)); exit_.append(opens.get((pair[1], str(row.ticker)), np.nan))
    entry_values, exit_values = np.asarray(entry), np.asarray(exit_)
    output = frame.copy()
    ratio = np.full(len(output), np.nan, dtype=float)
    valid = (entry_values > 0) & (exit_values > 0)
    np.divide(exit_values, entry_values, out=ratio, where=valid)
    output["target_net_return_10"] = ratio - 1.0 - cost
    output["target_positive"] = (output["target_net_return_10"] > 0).astype(float).where(output["target_net_return_10"].notna())
    return output


def make_dual(name: str, seed: int):
    if name == "linear_dual":
        common = lambda model: Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler()), ("model", model)])
        return common(Ridge(alpha=10.0)), common(LogisticRegression(C=1.0, max_iter=1000, random_state=seed))
    if name == "hist_dual":
        reg = Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", HistGradientBoostingRegressor(
            learning_rate=0.05, max_depth=3, max_iter=100, l2_regularization=1.0, random_state=seed))])
        clf = Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", HistGradientBoostingClassifier(
            learning_rate=0.05, max_depth=3, max_iter=100, l2_regularization=1.0, random_state=seed))])
        return reg, clf
    raise ValueError(name)


def score_models(train: pd.DataFrame, validation: pd.DataFrame, name: str, seed: int) -> tuple[pd.DataFrame, object, object]:
    reg, clf = make_dual(name, seed)
    reg.fit(train[list(FEATURES)], train["target_net_return_10"])
    clf.fit(train[list(FEATURES)], train["target_positive"].astype(int))
    output = validation[["date", "ticker", "target_net_return_10", "target_positive"]].copy()
    output["predicted_net_return"] = reg.predict(validation[list(FEATURES)])
    output["positive_probability"] = clf.predict_proba(validation[list(FEATURES)])[:, 1]
    return output, reg, clf


def metrics(scored: pd.DataFrame) -> tuple[float, float, float]:
    correlations = [g["predicted_net_return"].corr(g["target_net_return_10"], method="spearman") for _, g in scored.groupby("date")]
    ic = float(np.nanmean(correlations))
    brier = float(brier_score_loss(scored["target_positive"], scored["positive_probability"]))
    auc = float(roc_auc_score(scored["target_positive"], scored["positive_probability"])) if scored["target_positive"].nunique() == 2 else float("nan")
    return ic, brier, auc


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _gzip(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0}, float_format="%.12g", lineterminator="\n")


def run(config_path: Path, output_root: Path) -> dict[str, object]:
    guard_path(config_path); guard_path(output_root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    candidate_path, manifest_path, market_root = Path(config["agent_b_candidates"]), Path(config["agent_b_manifest"]), Path(config["market_root"])
    for path in (candidate_path, manifest_path, market_root): guard_path(path)
    agent_b_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if sha256(candidate_path) != agent_b_manifest["output_sha256"]["daily_top30.csv.gz"]:
        raise ValueError("Agent B Top 30 hash 불일치")
    candidates = pd.read_csv(candidate_path, dtype={"ticker": str}); candidates["ticker"] = candidates["ticker"].str.zfill(6)
    if candidates["date"].max() > config["data_end"]:
        raise ValueError("Agent C 허용 날짜 이후 입력입니다.")
    market, sessions, market_paths = load_market(market_root, set(candidates["ticker"]), int(config["market_start"][:4]), int(config["data_end"][:4]))
    technical = compute_technical_features(market)
    panel = candidates[["date", "ticker", "agent_b_score", "agent_b_rank"]].merge(
        technical[["date", "ticker", "mechanical_reset", *FEATURES]], on=["date", "ticker"], how="left", validate="one_to_one")
    panel = attach_target(panel, market, sessions, int(config["target_horizon_sessions"]), float(config["roundtrip_cost_rate"]))
    panel = panel[(panel["date"] >= config["data_start"]) & (panel["date"] <= config["data_end"])].copy()
    session_index = {date: i for i, date in enumerate(sessions)}
    sampled = panel[panel["date"].map(session_index).mod(int(config["sample_every_sessions"])) == 0].dropna(subset=["target_net_return_10"])
    fold_rows, fold_scores, cutoffs = [], {name: [] for name in config["models"]}, {}
    for year in config["validation_years"]:
        validation = sampled[sampled["date"].str[:4].astype(int) == int(year)].copy()
        if validation.empty: continue
        first = validation["date"].min()
        cutoff_i = session_index[first] - int(config["purge_sessions"]) - int(config["embargo_sessions"]) - 1
        if cutoff_i < 0: continue
        cutoff = sessions[cutoff_i]; cutoffs[int(year)] = cutoff
        train = sampled[sampled["date"] <= cutoff].copy()
        if len(train) < int(config["minimum_train_rows"]): continue
        for name in config["models"]:
            scored, _, _ = score_models(train, validation, name, int(config["seed"]))
            ic, brier, auc = metrics(scored); scored["model"] = name; scored["validation_year"] = year
            fold_scores[name].append(scored)
            fold_rows.append({"model": name, "validation_year": year, "train_cutoff": cutoff, "train_rows": len(train),
                              "validation_rows": len(validation), "rank_ic": ic, "brier": brier, "auc": auc})
    folds = pd.DataFrame(fold_rows)
    if folds.empty: raise RuntimeError("유효 Agent C fold가 없습니다.")
    summary = folds.groupby("model", as_index=False).agg(mean_rank_ic=("rank_ic", "mean"), mean_brier=("brier", "mean"), mean_auc=("auc", "mean"), folds=("validation_year", "count"))
    summary["simplicity"] = summary["model"].map({"linear_dual": 0, "hist_dual": 1})
    summary = summary.sort_values(["mean_rank_ic", "mean_brier", "simplicity"], ascending=[False, True, True])
    selected = str(summary.iloc[0]["model"])
    daily_parts, daily_count_rows = [], []
    for year in sorted(cutoffs):
        train = sampled[sampled["date"] <= cutoffs[year]].copy()
        score_scope = panel[panel["date"].str[:4].astype(int) == year].copy()
        scored, reg, clf = score_models(train, score_scope.assign(target_net_return_10=0.0, target_positive=0.0), selected, int(config["seed"]))
        score_scope["predicted_net_return"] = scored["predicted_net_return"].to_numpy()
        score_scope["positive_probability"] = scored["positive_probability"].to_numpy()
        score_scope["agent_c_score"] = score_scope["predicted_net_return"] * score_scope["positive_probability"]
        eligible = score_scope[(score_scope["predicted_net_return"] > 0) & (score_scope["positive_probability"] >= float(config["positive_probability_threshold"]))].copy()
        eligible["agent_c_rank"] = eligible.groupby("date")["agent_c_score"].rank(method="first", ascending=False)
        eligible = eligible[eligible["agent_c_rank"] <= int(config["maximum_daily_candidates"])]
        daily_parts.append(eligible)
        counts = eligible.groupby("date").size()
        for date in sorted(score_scope["date"].unique()): daily_count_rows.append({"date": date, "candidate_count": int(counts.get(date, 0))})
    daily = pd.concat(daily_parts, ignore_index=True).sort_values(["date", "agent_c_rank", "ticker"])
    counts = pd.DataFrame(daily_count_rows).drop_duplicates("date").sort_values("date")
    output_root.mkdir(parents=True, exist_ok=False)
    folds.to_csv(output_root / "fold_metrics.csv", index=False, float_format="%.12g", lineterminator="\n")
    summary.to_csv(output_root / "model_summary.csv", index=False, float_format="%.12g", lineterminator="\n")
    columns = ["date", "ticker", "agent_b_rank", "predicted_net_return", "positive_probability", "agent_c_score", "agent_c_rank"]
    _gzip(daily[columns], output_root / "daily_agent_c_candidates.csv.gz")
    counts.to_csv(output_root / "daily_candidate_counts.csv", index=False, lineterminator="\n")
    final_reg, final_clf = make_dual(selected, int(config["seed"])); final_reg.fit(sampled[list(FEATURES)], sampled["target_net_return_10"]); final_clf.fit(sampled[list(FEATURES)], sampled["target_positive"].astype(int))
    state = {"model": selected, "features": list(FEATURES), "fit_rows": len(sampled), "fit_max_signal_date": str(sampled["date"].max()),
             "positive_probability_threshold": config["positive_probability_threshold"], "maximum_daily_candidates": config["maximum_daily_candidates"]}
    if selected == "linear_dual":
        state.update({"regression_coefficient": final_reg.named_steps["model"].coef_.tolist(), "regression_intercept": float(final_reg.named_steps["model"].intercept_),
                      "classification_coefficient": final_clf.named_steps["model"].coef_[0].tolist(), "classification_intercept": float(final_clf.named_steps["model"].intercept_[0])})
    else: state["deterministic_refit_from_config_required"] = True
    _json(output_root / "selected_model.json", state)
    audit = {"agent_b_rows_loaded": len(candidates), "agent_b_sha256": sha256(candidate_path), "market_files_loaded": len(market_paths),
             "market_min_date": min(sessions), "market_max_date": max(sessions), "technical_feature_count": len(FEATURES),
             "mechanical_resets": int(technical["mechanical_reset"].sum()), "sample_rows": len(sampled), "scored_dates": len(counts),
             "zero_candidate_dates": int((counts["candidate_count"] == 0).sum()), "maximum_candidates_observed": int(counts["candidate_count"].max()),
             "v2_consumed_development_2022_2023_loaded": True, "legacy_v1_development_test_partition_accessed": False,
             "final_oos_accessed": False, "portfolio_backtest_run": False}
    _json(output_root / "data_audit.json", audit)
    market_hash = hashlib.sha256("\n".join(f"{p.relative_to(market_root).as_posix()}:{sha256(p)}" for p in market_paths).encode()).hexdigest()
    manifest = {"schema_version": "kospi200-agent-c-phase3-v1", "experiment_id": config["experiment_id"], "status": "CONSUMED_DEVELOPMENT_DIAGNOSTIC_ONLY",
                "selected_model": selected, "input_sha256": {"config": sha256(config_path), "agent_b_candidates": sha256(candidate_path), "agent_b_manifest": sha256(manifest_path), "market_tree": market_hash},
                "daily_candidate_rows": len(daily), "scored_dates": len(counts), "legacy_v1_development_test_partition_accessed": False,
                "v2_consumed_development_2022_2023_loaded": True, "final_oos_accessed": False, "portfolio_backtest_run": False}
    for name in ("fold_metrics.csv", "model_summary.csv", "daily_agent_c_candidates.csv.gz", "daily_candidate_counts.csv", "selected_model.json", "data_audit.json"):
        manifest.setdefault("output_sha256", {})[name] = sha256(output_root / name)
    _json(output_root / "manifest.json", manifest)
    return manifest
