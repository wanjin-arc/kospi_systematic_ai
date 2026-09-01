"""공식 KOSPI 200 초과수익과 하방위험을 학습하는 Agent B2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from kospi200_agent_b.runner import (
    compute_dilution, eligible_daily_panel, feature_columns, guard_path, load_market,
    month_end_rows, sha256,
)


def load_official_index(path: Path) -> pd.DataFrame:
    guard_path(path)
    frame = pd.read_csv(path)
    required = {"date", "open", "high", "low", "close", "index_code"}
    if not required.issubset(frame.columns):
        raise ValueError(f"공식 KOSPI 200 지수 열 누락: {sorted(required - set(frame.columns))}")
    if set(frame["index_code"].astype(str)) != {"1028"}:
        raise ValueError("Agent B2 benchmark는 KRX 1028만 허용합니다.")
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.date.astype(str)
    return frame.sort_values("date").drop_duplicates("date")


def attach_quality_target(frame: pd.DataFrame, market: pd.DataFrame, index: pd.DataFrame,
                          sessions: list[str], horizon: int, downside_penalty: float) -> pd.DataFrame:
    session_i = {day: i for i, day in enumerate(sessions)}
    boundaries = {day: (sessions[i + 1], sessions[i + horizon + 1])
                  for day, i in session_i.items() if i + horizon + 1 < len(sessions)}
    market_open = market.set_index(["date", "ticker"])["open"]
    market_close = market.set_index(["date", "ticker"])["close"]
    index_open = index.set_index("date")["open"]
    values: list[tuple[float, float, float]] = []
    for row in frame[["date", "ticker"]].itertuples(index=False):
        pair = boundaries.get(str(row.date))
        if pair is None:
            values.append((np.nan, np.nan, np.nan)); continue
        entry_day, exit_day = pair
        entry = market_open.get((entry_day, str(row.ticker)), np.nan)
        exit_ = market_open.get((exit_day, str(row.ticker)), np.nan)
        index_entry, index_exit = index_open.get(entry_day, np.nan), index_open.get(exit_day, np.nan)
        start = session_i[str(row.date)] + 1
        future_days = sessions[start:start + horizon]
        future = np.asarray([market_close.get((day, str(row.ticker)), np.nan) for day in future_days], dtype=float)
        if not (entry > 0 and exit_ > 0 and index_entry > 0 and index_exit > 0) or np.isnan(future).all():
            values.append((np.nan, np.nan, np.nan)); continue
        stock_return = exit_ / entry - 1.0
        index_return = index_exit / index_entry - 1.0
        mae = max(0.0, 1.0 - float(np.nanmin(future)) / entry)
        values.append((stock_return - index_return, mae, stock_return - index_return - downside_penalty * mae))
    output = frame.copy()
    output[["target_excess_63", "target_mae_63", "target_quality_63"]] = np.asarray(values)
    return output


def make_model(name: str, seed: int):
    if name == "ridge_quality":
        return Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler()), ("model", Ridge(alpha=10.0))])
    if name == "hist_quality":
        return Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", HistGradientBoostingRegressor(
            learning_rate=0.05, max_depth=3, max_iter=100, min_samples_leaf=100,
            l2_regularization=5.0, random_state=seed,
        ))])
    raise ValueError(name)


def daily_ic(frame: pd.DataFrame) -> float:
    values = [group["score"].corr(group["target_quality_63"], method="spearman") for _, group in frame.groupby("date")]
    return float(np.nanmean(values))


def ndcg(frame: pd.DataFrame, n: int) -> float:
    values = []
    for _, group in frame.groupby("date"):
        group = group.copy()
        group["relevance"] = group["target_quality_63"].rank(pct=True, method="average")
        ranked = group.sort_values(["score", "ticker"], ascending=[False, True]).head(n)
        ideal = group.sort_values(["relevance", "ticker"], ascending=[False, True]).head(n)
        discount = 1.0 / np.log2(np.arange(2, len(ranked) + 2))
        denominator = float(np.sum(ideal["relevance"].to_numpy() * discount))
        numerator = float(np.sum(ranked["relevance"].to_numpy() * discount))
        if denominator > 0: values.append(numerator / denominator)
    return float(np.mean(values)) if values else float("nan")


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _write_gzip(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0}, float_format="%.12g", lineterminator="\n")


def _tree_hash(paths: list[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode()); digest.update(b"\0"); digest.update(sha256(path).encode()); digest.update(b"\n")
    return digest.hexdigest()


def run(config_path: Path, output_root: Path) -> dict[str, object]:
    guard_path(config_path); guard_path(output_root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("portfolio_backtest") is not False or config.get("final_oos_access") is not False:
        raise ValueError("Agent B2는 포트폴리오 및 Final OOS를 허용하지 않습니다.")
    panel_path, market_root, index_path = Path(config["factor_panel"]), Path(config["market_root"]), Path(config["index_file"])
    for path in (panel_path, market_root, index_path): guard_path(path)
    panel = pd.read_csv(panel_path, dtype={"ticker": str}); panel["ticker"] = panel["ticker"].str.zfill(6)
    panel = panel[(panel["date"] >= config["data_start"]) & (panel["date"] <= config["data_end"])].copy()
    index = load_official_index(index_path)
    market, sessions, market_paths = load_market(market_root, int(config["data_start"][:4]), int(config["data_end"][:4]))
    sessions = [day for day in sessions if config["data_start"] <= day <= config["data_end"]]
    dilution = compute_dilution(market, int(config["dilution_lookback_sessions"]))
    daily = eligible_daily_panel(panel, dilution, int(config["market_cap_universe_size"]))
    monthly = month_end_rows(daily)
    labeled = attach_quality_target(monthly, market, index, sessions, int(config["target_horizon_sessions"]), float(config["downside_penalty"])).dropna(subset=["target_quality_63"])
    session_i = {day: i for i, day in enumerate(sessions)}
    folds, cutoffs, model_scores = [], {}, {name: [] for name in config["models"]}
    for year in config["validation_years"]:
        validation = labeled[labeled["date"].str[:4].astype(int) == int(year)].copy()
        if validation.empty: continue
        first = validation["date"].min()
        cutoff_i = session_i[first] - int(config["purge_sessions"]) - int(config["embargo_sessions"]) - 1
        if cutoff_i < 0: continue
        cutoff = sessions[cutoff_i]; cutoffs[int(year)] = cutoff
        train = labeled[labeled["date"] <= cutoff].copy()
        if train["date"].nunique() < int(config["minimum_train_months"]): continue
        for name in config["models"]:
            model = make_model(name, int(config["seed"])); model.fit(train[feature_columns()], train["target_quality_63"])
            part = validation[["date", "ticker", "target_quality_63", "target_excess_63", "target_mae_63"]].copy()
            part["score"] = model.predict(validation[feature_columns()]); part["model"] = name; part["validation_year"] = year
            model_scores[name].append(part)
            folds.append({"model": name, "validation_year": year, "train_cutoff": cutoff, "train_rows": len(train), "validation_rows": len(validation),
                          "quality_rank_ic": daily_ic(part), "ndcg_at_80": ndcg(part, int(config["broad_quality_size"])),
                          "selected_mean_excess": float(part.nlargest(int(config["broad_quality_size"]), "score")["target_excess_63"].mean()),
                          "selected_mean_mae": float(part.nlargest(int(config["broad_quality_size"]), "score")["target_mae_63"].mean())})
    fold_frame = pd.DataFrame(folds)
    if fold_frame.empty: raise RuntimeError("Agent B2 유효 fold가 없습니다.")
    summary = fold_frame.groupby("model", as_index=False).agg(mean_quality_rank_ic=("quality_rank_ic", "mean"), mean_ndcg_at_80=("ndcg_at_80", "mean"), folds=("validation_year", "count"))
    summary["simplicity"] = summary["model"].map({"ridge_quality": 0, "hist_quality": 1})
    summary = summary.sort_values(["mean_quality_rank_ic", "mean_ndcg_at_80", "simplicity"], ascending=[False, False, True])
    selected = str(summary.iloc[0]["model"])
    daily_parts = []
    for year, cutoff in sorted(cutoffs.items()):
        train = labeled[labeled["date"] <= cutoff].copy()
        model = make_model(selected, int(config["seed"])); model.fit(train[feature_columns()], train["target_quality_63"])
        scope = daily[daily["date"].str[:4].astype(int) == year].copy()
        snapshot_scope = daily[(daily["date"] >= f"{year - 1}-12-01") & (daily["date"] <= f"{year}-12-31")].copy()
        snapshots = month_end_rows(snapshot_scope)
        snapshots["agent_b2_score"] = model.predict(snapshots[feature_columns()])
        snapshots = snapshots.rename(columns={"date": "score_date"})
        left = scope[["date", "ticker"]].copy()
        right = snapshots[["score_date", "ticker", "agent_b2_score", "statement_year", "statement_quarter"]].copy()
        left["date"] = pd.to_datetime(left["date"], errors="raise")
        right["score_date"] = pd.to_datetime(right["score_date"], errors="raise")
        left = left.sort_values(["date", "ticker"])
        right = right.sort_values(["score_date", "ticker"])
        expanded = pd.merge_asof(left, right, left_on="date", right_on="score_date", by="ticker", direction="backward", allow_exact_matches=False)
        expanded = expanded.dropna(subset=["agent_b2_score"]).copy()
        expanded["date"] = expanded["date"].dt.date.astype(str)
        expanded["score_date"] = expanded["score_date"].dt.date.astype(str)
        expanded["agent_b2_percentile"] = expanded.groupby("date")["agent_b2_score"].rank(pct=True, method="average")
        expanded["agent_b2_rank"] = expanded.groupby("date")["agent_b2_score"].rank(method="first", ascending=False)
        expanded["broad_quality_eligible"] = expanded["agent_b2_rank"] <= int(config["broad_quality_size"])
        expanded["report_top30"] = expanded["agent_b2_rank"] <= int(config["report_top_size"])
        daily_parts.append(expanded)
    scored = pd.concat(daily_parts, ignore_index=True).sort_values(["date", "agent_b2_rank", "ticker"])
    output_root.mkdir(parents=True, exist_ok=False)
    fold_frame.to_csv(output_root / "fold_metrics.csv", index=False, float_format="%.12g", lineterminator="\n")
    summary.to_csv(output_root / "model_summary.csv", index=False, float_format="%.12g", lineterminator="\n")
    columns = ["date", "score_date", "ticker", "agent_b2_score", "agent_b2_percentile", "agent_b2_rank", "broad_quality_eligible", "report_top30", "statement_year", "statement_quarter"]
    _write_gzip(scored[columns], output_root / "daily_agent_b2_scores.csv.gz")
    _write_json(output_root / "selected_model.json", {"model": selected, "features": feature_columns(), "target": "excess_63_minus_0.5_mae", "fit_policy": "expanding_walk_forward"})
    audit = {"factor_rows_loaded": len(panel), "factor_min_date": str(panel["date"].min()), "factor_max_date": str(panel["date"].max()),
             "index_rows_loaded": len(index), "index_code": "1028", "index_min_date": str(index["date"].min()), "index_max_date": str(index["date"].max()),
             "market_files_loaded": len(market_paths), "monthly_label_rows": len(labeled), "daily_score_rows": len(scored),
             "v2_consumed_development_2022_2023_loaded": True, "legacy_v1_development_test_partition_accessed": False,
             "final_oos_accessed": False, "portfolio_backtest_run": False}
    _write_json(output_root / "data_audit.json", audit)
    manifest = {"schema_version": "kospi200-agent-b2-quality-v1", "experiment_id": config["experiment_id"], "status": "CONSUMED_DEVELOPMENT_DIAGNOSTIC_ONLY",
                "selected_model": selected, "input_sha256": {"config": sha256(config_path), "factor_panel": sha256(panel_path), "official_index": sha256(index_path), "market_tree": _tree_hash(market_paths, market_root)},
                "final_oos_accessed": False, "portfolio_backtest_run": False}
    for name in ("fold_metrics.csv", "model_summary.csv", "daily_agent_b2_scores.csv.gz", "selected_model.json", "data_audit.json"):
        manifest.setdefault("output_sha256", {})[name] = sha256(output_root / name)
    _write_json(output_root / "manifest.json", manifest)
    return manifest
