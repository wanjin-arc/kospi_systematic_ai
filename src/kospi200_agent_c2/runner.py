"""장기 OHLCV와 공식 KOSPI 200 지수를 사용하는 독립 Agent C2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from kospi200_agent_b2.runner import load_official_index
from kospi200_agent_c.runner import FEATURES as STOCK_FEATURES
from kospi200_agent_c.runner import compute_technical_features, guard_path, load_market, sha256
from kospi200_agent_c_independent.runner import load_membership, trade_outcomes


INDEX_FEATURES = ("index_return_20", "index_trend_60", "index_volatility_20")
ALL_FEATURES = (*STOCK_FEATURES, *INDEX_FEATURES)


def load_market_roots(roots: list[Path], tickers: set[str], start_year: int, end_year: int):
    frames, sessions, paths = [], [], []
    for root in roots:
        guard_path(root)
        years = [int(path.name) for path in root.iterdir() if path.is_dir() and path.name.isdigit()]
        selected = [year for year in years if start_year <= year <= end_year]
        if not selected: continue
        frame, local_sessions, local_paths = load_market(root, tickers, min(selected), max(selected))
        frames.append(frame); sessions.extend(local_sessions); paths.extend(local_paths)
    if not frames: raise FileNotFoundError("Agent C2 시장 입력이 없습니다.")
    market = pd.concat(frames, ignore_index=True).drop_duplicates(["date", "ticker"]).sort_values(["ticker", "date"])
    return market, sorted(set(sessions)), paths


def index_features(index: pd.DataFrame) -> pd.DataFrame:
    frame = index.sort_values("date").copy()
    log_return = np.log(frame["close"] / frame["close"].shift(1))
    frame["index_return_20"] = frame["close"].pct_change(20, fill_method=None)
    frame["index_trend_60"] = frame["close"] / frame["close"].rolling(60, min_periods=60).mean() - 1.0
    frame["index_volatility_20"] = log_return.rolling(20, min_periods=20).std() * np.sqrt(252.0)
    return frame[["date", *INDEX_FEATURES]]


def attach_excess_target(frame: pd.DataFrame, market: pd.DataFrame, index: pd.DataFrame,
                         sessions: list[str], horizon: int, cost: float) -> pd.DataFrame:
    session_i = {day: i for i, day in enumerate(sessions)}
    boundaries = {day: (sessions[i + 1], sessions[i + horizon + 1])
                  for day, i in session_i.items() if i + horizon + 1 < len(sessions)}
    stock_open = market.set_index(["date", "ticker"])["open"]
    index_open = index.set_index("date")["open"]
    targets = []
    for row in frame[["date", "ticker"]].itertuples(index=False):
        pair = boundaries.get(str(row.date))
        if pair is None:
            targets.append(np.nan); continue
        entry_day, exit_day = pair
        se, sx = stock_open.get((entry_day, str(row.ticker)), np.nan), stock_open.get((exit_day, str(row.ticker)), np.nan)
        ie, ix = index_open.get(entry_day, np.nan), index_open.get(exit_day, np.nan)
        if not (se > 0 and sx > 0 and ie > 0 and ix > 0): targets.append(np.nan); continue
        targets.append((sx / se - 1.0) - (ix / ie - 1.0) - cost)
    output = frame.copy()
    output["target_net_excess_10"] = targets
    output["target_positive_excess"] = (output["target_net_excess_10"] > 0).astype(float).where(output["target_net_excess_10"].notna())
    return output


def _linear(model):
    return Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler()), ("model", model)])


def _hist(model):
    return Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", model)])


def make_models(name: str, seed: int):
    if name == "linear_excess_dual":
        return _linear(Ridge(alpha=10.0)), _linear(LogisticRegression(C=1.0, max_iter=1000, random_state=seed))
    if name == "hist_excess_dual":
        return _hist(HistGradientBoostingRegressor(learning_rate=0.05, max_depth=3, max_iter=100, min_samples_leaf=100, l2_regularization=5.0, random_state=seed)), _hist(HistGradientBoostingClassifier(learning_rate=0.05, max_depth=3, max_iter=100, min_samples_leaf=100, l2_regularization=5.0, random_state=seed))
    if name == "hist_event_dual_v1":
        return _hist(HistGradientBoostingRegressor(learning_rate=0.05, max_depth=3, max_iter=100, min_samples_leaf=100, l2_regularization=1.0, random_state=seed)), _hist(HistGradientBoostingClassifier(learning_rate=0.05, max_depth=3, max_iter=100, min_samples_leaf=100, l2_regularization=1.0, random_state=seed))
    raise ValueError(name)


def fit_score(train: pd.DataFrame, scope: pd.DataFrame, name: str, seed: int, risk_weight: float) -> pd.DataFrame:
    reg, clf = make_models(name, seed)
    if name == "hist_event_dual_v1":
        reg.fit(train[list(ALL_FEATURES)], train["target_mae_10"])
        clf.fit(train[list(ALL_FEATURES)], train["target_success_2to1"].astype(int))
        predicted_risk = np.maximum(0.0, reg.predict(scope[list(ALL_FEATURES)]))
        probability = clf.predict_proba(scope[list(ALL_FEATURES)])[:, 1]
        output = scope[["date", "ticker", "target_net_excess_10", "target_positive_excess", "target_success_2to1"]].copy()
        output["predicted_value"] = probability
        output["positive_probability"] = probability
        output["predicted_risk"] = predicted_risk
        risk_rank = output.groupby("date")["predicted_risk"].rank(pct=True, method="average")
        output["agent_c2_score"] = probability - risk_weight * risk_rank
        return output
    reg.fit(train[list(ALL_FEATURES)], train["target_net_excess_10"])
    clf.fit(train[list(ALL_FEATURES)], train["target_positive_excess"].astype(int))
    output = scope[["date", "ticker", "target_net_excess_10", "target_positive_excess", "target_success_2to1"]].copy()
    output["predicted_value"] = reg.predict(scope[list(ALL_FEATURES)])
    output["positive_probability"] = clf.predict_proba(scope[list(ALL_FEATURES)])[:, 1]
    output["predicted_risk"] = np.nan
    value_rank = output.groupby("date")["predicted_value"].rank(pct=True, method="average")
    output["agent_c2_score"] = value_rank * output["positive_probability"]
    return output


def evaluate(scored: pd.DataFrame) -> tuple[float, float]:
    correlations = [g["agent_c2_score"].corr(g["target_net_excess_10"], method="spearman") for _, g in scored.groupby("date")]
    ic = float(np.nanmean(correlations))
    auc = float(roc_auc_score(scored["target_positive_excess"], scored["positive_probability"])) if scored["target_positive_excess"].nunique() == 2 else float("nan")
    return ic, auc


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _gzip(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0}, float_format="%.12g", lineterminator="\n")


def _tree_hash(paths: list[Path], roots: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        root = next(root for root in roots if path.is_relative_to(root))
        digest.update(f"{root.name}/{path.relative_to(root).as_posix()}".encode()); digest.update(b"\0"); digest.update(sha256(path).encode()); digest.update(b"\n")
    return digest.hexdigest()


def run(config_path: Path, output_root: Path) -> dict[str, object]:
    guard_path(config_path); guard_path(output_root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("agent_b_access") is not False or config.get("portfolio_backtest") is not False or config.get("final_oos_access") is not False:
        raise ValueError("Agent C2는 Agent B·포트폴리오·Final OOS 접근을 금지합니다.")
    membership_root = Path(config["membership_root"]); roots = [Path(value) for value in config["market_roots"]]; index_path = Path(config["index_file"])
    membership, membership_paths = load_membership(membership_root, config["market_start"], config["data_end"])
    market, sessions, market_paths = load_market_roots(roots, set(membership["ticker"]), int(config["market_start"][:4]), int(config["data_end"][:4]))
    index = load_official_index(index_path); technical = compute_technical_features(market)
    outcomes = trade_outcomes(market, sessions, int(config["target_horizon_sessions"]), float(config["stop_loss_rate"]), float(config["take_profit_rate"]), float(config["roundtrip_cost_rate"]))
    panel = membership.merge(technical[["date", "ticker", "mechanical_reset", *STOCK_FEATURES]], on=["date", "ticker"], how="left", validate="one_to_one")
    panel = panel.merge(index_features(index), on="date", how="left", validate="many_to_one")
    panel = panel.merge(outcomes[["date", "ticker", "target_success_2to1", "target_mae_10"]], on=["date", "ticker"], how="left", validate="one_to_one")
    panel = attach_excess_target(panel, market, index, sessions, int(config["target_horizon_sessions"]), float(config["roundtrip_cost_rate"]))
    panel = panel[(panel["date"] >= config["data_start"]) & (panel["date"] <= config["data_end"])].copy()
    session_i = {day: i for i, day in enumerate(sessions)}
    sampled = panel[panel["date"].map(session_i).mod(int(config["sample_every_sessions"])) == 0]
    sampled = sampled.dropna(subset=[*ALL_FEATURES, "target_net_excess_10", "target_mae_10"])
    folds, cutoffs = [], {}
    for year in config["validation_years"]:
        validation = sampled[sampled["date"].str[:4].astype(int) == int(year)].copy()
        if validation.empty: continue
        cutoff_i = session_i[validation["date"].min()] - int(config["purge_sessions"]) - int(config["embargo_sessions"]) - 1
        cutoff = sessions[cutoff_i]; cutoffs[int(year)] = cutoff
        train = sampled[sampled["date"] <= cutoff].copy()
        if len(train) < int(config["minimum_train_rows"]): continue
        for name in config["models"]:
            scored = fit_score(train, validation, name, int(config["seed"]), float(config["risk_penalty_weight"]))
            ic, auc = evaluate(scored)
            folds.append({"model": name, "validation_year": year, "train_cutoff": cutoff, "train_rows": len(train), "validation_rows": len(validation), "excess_rank_ic": ic, "positive_excess_auc": auc})
    fold_frame = pd.DataFrame(folds)
    if fold_frame.empty: raise RuntimeError("Agent C2 유효 fold가 없습니다.")
    summary = fold_frame.groupby("model", as_index=False).agg(mean_excess_rank_ic=("excess_rank_ic", "mean"), mean_positive_excess_auc=("positive_excess_auc", "mean"), folds=("validation_year", "count"))
    summary["simplicity"] = summary["model"].map({"linear_excess_dual": 0, "hist_event_dual_v1": 1, "hist_excess_dual": 2})
    summary = summary.sort_values(["mean_excess_rank_ic", "mean_positive_excess_auc", "simplicity"], ascending=[False, False, True])
    selected = str(summary.iloc[0]["model"])
    daily_parts = []
    for year, cutoff in sorted(cutoffs.items()):
        train = sampled[sampled["date"] <= cutoff].copy()
        scope = panel[panel["date"].str[:4].astype(int) == year].dropna(subset=list(ALL_FEATURES)).copy()
        scored = fit_score(train, scope, selected, int(config["seed"]), float(config["risk_penalty_weight"]))
        scored["agent_c2_rank"] = scored.groupby("date")["agent_c2_score"].rank(method="first", ascending=False)
        daily_parts.append(scored)
    daily = pd.concat(daily_parts, ignore_index=True).sort_values(["date", "agent_c2_rank", "ticker"])
    output_root.mkdir(parents=True, exist_ok=False)
    fold_frame.to_csv(output_root / "fold_metrics.csv", index=False, float_format="%.12g", lineterminator="\n")
    summary.to_csv(output_root / "model_summary.csv", index=False, float_format="%.12g", lineterminator="\n")
    columns = ["date", "ticker", "agent_c2_score", "agent_c2_rank", "predicted_value", "positive_probability", "predicted_risk"]
    _gzip(daily[columns], output_root / "daily_agent_c2_scores.csv.gz")
    _json(output_root / "selected_model.json", {"model": selected, "features": list(ALL_FEATURES), "target": "official_kospi200_net_excess_10", "fit_policy": "expanding_walk_forward"})
    audit = {"membership_rows_loaded": len(membership), "membership_min_date": str(membership["date"].min()), "membership_max_date": str(membership["date"].max()),
             "market_files_loaded": len(market_paths), "market_min_date": min(sessions), "market_max_date": max(sessions), "index_rows_loaded": len(index), "index_code": "1028",
             "sample_rows": len(sampled), "daily_score_rows": len(daily), "stock_feature_count": len(STOCK_FEATURES), "index_feature_count": len(INDEX_FEATURES),
             "agent_b_accessed": False, "fundamental_data_accessed": False, "v2_consumed_development_2022_2023_loaded": True,
             "legacy_v1_development_test_partition_accessed": False, "final_oos_accessed": False, "portfolio_backtest_run": False}
    _json(output_root / "data_audit.json", audit)
    manifest = {"schema_version": "kospi200-agent-c2-excess-v1", "experiment_id": config["experiment_id"], "status": "CONSUMED_DEVELOPMENT_DIAGNOSTIC_ONLY", "selected_model": selected,
                "input_sha256": {"config": sha256(config_path), "official_index": sha256(index_path), "membership_tree": _tree_hash(membership_paths, [membership_root]), "market_tree": _tree_hash(market_paths, roots)},
                "final_oos_accessed": False, "portfolio_backtest_run": False}
    for name in ("fold_metrics.csv", "model_summary.csv", "daily_agent_c2_scores.csv.gz", "selected_model.json", "data_audit.json"):
        manifest.setdefault("output_sha256", {})[name] = sha256(output_root / name)
    _json(output_root / "manifest.json", manifest)
    return manifest
