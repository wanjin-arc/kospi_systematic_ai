"""전체 PIT KOSPI 200을 OHLCV만으로 점수화하는 독립 Agent C."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import mean_absolute_error, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from kospi200_agent_c.runner import FEATURES, compute_technical_features, guard_path, load_market, sha256


def load_membership(root: Path, start: str, end: str) -> tuple[pd.DataFrame, list[Path]]:
    guard_path(root)
    paths = sorted(path for path in root.rglob("*.csv") if start[:4] <= path.stem[:4] <= end[:4])
    pieces = []
    for path in paths:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        if not {"date", "ticker"}.issubset(frame.columns):
            raise ValueError(f"membership 필수 열 누락: {path}")
        frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.date.astype(str)
        frame["ticker"] = frame["ticker"].str.replace(r"\D", "", regex=True).str.zfill(6)
        pieces.append(frame[["date", "ticker"]])
    if not pieces: raise FileNotFoundError("PIT KOSPI 200 membership가 없습니다.")
    result = pd.concat(pieces, ignore_index=True).drop_duplicates(["date", "ticker"])
    result = result[(result["date"] >= start) & (result["date"] <= end)]
    return result.sort_values(["date", "ticker"]), paths


def trade_outcomes(market: pd.DataFrame, sessions: list[str], horizon: int, stop: float, take: float, cost: float) -> pd.DataFrame:
    rows = []
    for ticker, group in market.groupby("ticker", sort=True):
        indexed = group.set_index("date").reindex(sessions)
        entry = indexed["open"].shift(-1)
        stop_price, take_price = entry * (1.0 - stop), entry * (1.0 + take)
        first_stop = np.full(len(indexed), horizon + 1, dtype=int)
        first_take = np.full(len(indexed), horizon + 1, dtype=int)
        future_lows = []
        for offset in range(1, horizon + 1):
            low = indexed["low"].shift(-offset); high = indexed["high"].shift(-offset)
            future_lows.append(low.to_numpy(float))
            stop_hit = low.to_numpy(float) <= stop_price.to_numpy(float)
            take_hit = high.to_numpy(float) >= take_price.to_numpy(float)
            first_stop[(first_stop == horizon + 1) & stop_hit] = offset
            first_take[(first_take == horizon + 1) & take_hit] = offset
        minimum_low = np.fmin.reduce(np.vstack(future_lows))
        valid_entry = entry.to_numpy(float) > 0
        success = (first_take < first_stop) & (first_take <= horizon) & valid_entry
        mae = np.full(len(indexed), np.nan); mae[valid_entry] = np.maximum(0.0, 1.0 - minimum_low[valid_entry] / entry.to_numpy(float)[valid_entry])
        terminal = indexed["open"].shift(-(horizon + 1)).to_numpy(float)
        terminal_return = np.full(len(indexed), np.nan)
        valid_terminal = valid_entry & (terminal > 0)
        terminal_return[valid_terminal] = terminal[valid_terminal] / entry.to_numpy(float)[valid_terminal] - 1.0 - cost
        current_close = indexed["close"].to_numpy(float)
        entry_gap = np.full(len(indexed), np.nan)
        valid_gap = valid_entry & (current_close > 0)
        entry_gap[valid_gap] = entry.to_numpy(float)[valid_gap] / current_close[valid_gap] - 1.0
        rows.append(pd.DataFrame({"date": sessions, "ticker": ticker, "target_success_2to1": success.astype(float),
                                  "target_mae_10": mae, "target_terminal_net_return_10": terminal_return, "realized_entry_gap": entry_gap,
                                  "first_stop_offset": first_stop, "first_take_offset": first_take}))
    return pd.concat(rows, ignore_index=True)


def make_models(name: str, seed: int):
    if name == "linear_event_dual":
        def pipeline(model): return Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler()), ("model", model)])
        return pipeline(Ridge(alpha=10.0)), pipeline(LogisticRegression(C=1.0, max_iter=1000, random_state=seed))
    if name == "hist_event_dual":
        risk = Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", HistGradientBoostingRegressor(
            learning_rate=0.05, max_depth=3, max_iter=100, l2_regularization=1.0, random_state=seed))])
        bottom = Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", HistGradientBoostingClassifier(
            learning_rate=0.05, max_depth=3, max_iter=100, l2_regularization=1.0, random_state=seed))])
        return risk, bottom
    raise ValueError(name)


def fit_score(train: pd.DataFrame, validation: pd.DataFrame, name: str, seed: int, risk_weight: float):
    risk, bottom = make_models(name, seed)
    risk.fit(train[list(FEATURES)], train["target_mae_10"])
    bottom.fit(train[list(FEATURES)], train["target_success_2to1"].astype(int))
    scored = validation[["date", "ticker", "target_success_2to1", "target_mae_10", "target_terminal_net_return_10", "realized_entry_gap"]].copy()
    scored["predicted_mae"] = np.maximum(0.0, risk.predict(validation[list(FEATURES)]))
    scored["bottom_probability"] = bottom.predict_proba(validation[list(FEATURES)])[:, 1]
    risk_rank = scored.groupby("date")["predicted_mae"].rank(pct=True, method="average")
    scored["agent_c_score"] = scored["bottom_probability"] - risk_weight * risk_rank
    return scored, risk, bottom


def evaluate(scored: pd.DataFrame) -> tuple[float, float, float]:
    correlations = [g["agent_c_score"].corr(g["target_terminal_net_return_10"], method="spearman") for _, g in scored.groupby("date")]
    ic = float(np.nanmean(correlations))
    auc = float(roc_auc_score(scored["target_success_2to1"], scored["bottom_probability"])) if scored["target_success_2to1"].nunique() == 2 else float("nan")
    mae = float(mean_absolute_error(scored["target_mae_10"], scored["predicted_mae"]))
    return ic, auc, mae


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _gzip(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0}, float_format="%.12g", lineterminator="\n")


def tree_hash(paths: list[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode()); digest.update(b"\0"); digest.update(sha256(path).encode()); digest.update(b"\n")
    return digest.hexdigest()


def run(config_path: Path, output_root: Path) -> dict[str, object]:
    guard_path(config_path); guard_path(output_root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("agent_b_access") is not False: raise ValueError("독립 Agent C는 Agent B 접근을 금지합니다.")
    membership_root, market_root = Path(config["membership_root"]), Path(config["market_root"])
    membership, membership_paths = load_membership(membership_root, config["data_start"], config["data_end"])
    market, sessions, market_paths = load_market(market_root, set(membership["ticker"]), int(config["market_start"][:4]), int(config["data_end"][:4]))
    technical = compute_technical_features(market)
    outcomes = trade_outcomes(market, sessions, int(config["target_horizon_sessions"]), float(config["stop_loss_rate"]),
                              float(config["take_profit_rate"]), float(config["roundtrip_cost_rate"]))
    panel = membership.merge(technical[["date", "ticker", "mechanical_reset", *FEATURES]], on=["date", "ticker"], how="left", validate="one_to_one")
    panel = panel.merge(outcomes, on=["date", "ticker"], how="left", validate="one_to_one")
    session_index = {date: i for i, date in enumerate(sessions)}
    sampled = panel[panel["date"].map(session_index).mod(int(config["sample_every_sessions"])) == 0]
    sampled = sampled.dropna(subset=["target_mae_10", "target_terminal_net_return_10"])
    folds, score_parts, cutoffs = [], {name: [] for name in config["models"]}, {}
    for year in config["validation_years"]:
        validation = sampled[sampled["date"].str[:4].astype(int) == int(year)].copy()
        if validation.empty: continue
        first = validation["date"].min()
        cutoff_i = session_index[first] - int(config["purge_sessions"]) - int(config["embargo_sessions"]) - 1
        cutoff = sessions[cutoff_i]; cutoffs[int(year)] = cutoff
        train = sampled[sampled["date"] <= cutoff].copy()
        if len(train) < int(config["minimum_train_rows"]): continue
        for name in config["models"]:
            scored, _, _ = fit_score(train, validation, name, int(config["seed"]), float(config["risk_penalty_weight"]))
            ic, auc, risk_mae = evaluate(scored); scored["model"] = name; scored["validation_year"] = year
            score_parts[name].append(scored)
            folds.append({"model": name, "validation_year": year, "train_cutoff": cutoff, "train_rows": len(train), "validation_rows": len(validation),
                          "composite_rank_ic": ic, "bottom_auc": auc, "risk_mae": risk_mae,
                          "success_rate": float(validation["target_success_2to1"].mean())})
    fold_frame = pd.DataFrame(folds)
    if fold_frame.empty: raise RuntimeError("유효 독립 Agent C fold가 없습니다.")
    summary = fold_frame.groupby("model", as_index=False).agg(mean_composite_rank_ic=("composite_rank_ic", "mean"), mean_bottom_auc=("bottom_auc", "mean"), mean_risk_mae=("risk_mae", "mean"), folds=("validation_year", "count"))
    summary["simplicity"] = summary["model"].map({"linear_event_dual": 0, "hist_event_dual": 1})
    summary = summary.sort_values(["mean_composite_rank_ic", "mean_bottom_auc", "simplicity"], ascending=[False, False, True])
    selected = str(summary.iloc[0]["model"])
    daily_parts = []
    for year in sorted(cutoffs):
        train = sampled[sampled["date"] <= cutoffs[year]].copy()
        scope = panel[panel["date"].str[:4].astype(int) == year].dropna(subset=["target_mae_10", "target_terminal_net_return_10"]).copy()
        scored, _, _ = fit_score(train, scope, selected, int(config["seed"]), float(config["risk_penalty_weight"]))
        scored["agent_c_rank"] = scored.groupby("date")["agent_c_score"].rank(method="first", ascending=False)
        scored["historical_gap_vetoed"] = scored["realized_entry_gap"].abs() > float(config["gap_veto_rate"])
        daily_parts.append(scored)
    daily = pd.concat(daily_parts, ignore_index=True).sort_values(["date", "agent_c_rank", "ticker"])
    output_root.mkdir(parents=True, exist_ok=False)
    fold_frame.to_csv(output_root / "fold_metrics.csv", index=False, float_format="%.12g", lineterminator="\n")
    summary.to_csv(output_root / "model_summary.csv", index=False, float_format="%.12g", lineterminator="\n")
    output_columns = ["date", "ticker", "agent_c_score", "agent_c_rank", "bottom_probability", "predicted_mae", "historical_gap_vetoed"]
    _gzip(daily[output_columns], output_root / "daily_independent_agent_c_scores.csv.gz")
    final_risk, final_bottom = make_models(selected, int(config["seed"])); final_risk.fit(sampled[list(FEATURES)], sampled["target_mae_10"]); final_bottom.fit(sampled[list(FEATURES)], sampled["target_success_2to1"].astype(int))
    state = {"model": selected, "features": list(FEATURES), "fit_rows": len(sampled), "fit_max_signal_date": str(sampled["date"].max()),
             "stop_loss_rate": config["stop_loss_rate"], "take_profit_rate": config["take_profit_rate"], "risk_penalty_weight": config["risk_penalty_weight"]}
    if selected == "linear_event_dual":
        state.update({"risk_coefficient": final_risk.named_steps["model"].coef_.tolist(), "bottom_coefficient": final_bottom.named_steps["model"].coef_[0].tolist()})
    else: state["deterministic_refit_from_config_required"] = True
    _json(output_root / "selected_model.json", state)
    audit = {"membership_rows_loaded": len(membership), "membership_dates": int(membership["date"].nunique()), "membership_min_daily": int(membership.groupby("date").size().min()),
             "membership_max_daily": int(membership.groupby("date").size().max()), "market_files_loaded": len(market_paths), "technical_feature_count": len(FEATURES),
             "mechanical_resets": int(technical["mechanical_reset"].sum()), "sample_rows": len(sampled), "daily_score_rows": len(daily),
             "agent_b_accessed": False, "fundamental_data_accessed": False, "v2_consumed_development_2022_2023_loaded": True,
             "legacy_v1_development_test_partition_accessed": False, "final_oos_accessed": False, "portfolio_backtest_run": False}
    _json(output_root / "data_audit.json", audit)
    manifest = {"schema_version": "kospi200-independent-agent-c-phase3b-v1", "experiment_id": config["experiment_id"], "status": "CONSUMED_DEVELOPMENT_DIAGNOSTIC_ONLY",
                "selected_model": selected, "input_sha256": {"config": sha256(config_path), "membership_tree": tree_hash(membership_paths, membership_root), "market_tree": tree_hash(market_paths, market_root)},
                "daily_score_rows": len(daily), "agent_b_accessed": False, "fundamental_data_accessed": False, "final_oos_accessed": False, "portfolio_backtest_run": False}
    for name in ("fold_metrics.csv", "model_summary.csv", "daily_independent_agent_c_scores.csv.gz", "selected_model.json", "data_audit.json"):
        manifest.setdefault("output_sha256", {})[name] = sha256(output_root / name)
    _json(output_root / "manifest.json", manifest)
    return manifest
