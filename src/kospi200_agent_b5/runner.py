"""분기 PIT 재무 시계열을 사용하는 Agent B5 XGBRanker."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import XGBRanker

from kospi200_agent_b.runner import (
    compute_dilution,
    eligible_daily_panel,
    feature_columns,
    guard_path,
    load_market,
    month_end_rows,
    sha256,
)
from kospi200_agent_b2.runner import attach_quality_target, daily_ic, load_official_index, ndcg


def temporal_feature_columns(available_columns: set[str] | None = None) -> list[str]:
    base = feature_columns()
    robust = [name.replace("__percentile", "__robust_z") for name in base if name.endswith("__percentile")]
    if available_columns is not None:
        robust = [name for name in robust if name in available_columns]
    changes = [f"{name}__delta_{lag}" for name in base for lag in (63, 252)]
    return [*base, *robust, *changes]


def add_temporal_features(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.sort_values(["ticker", "date"], kind="mergesort").copy()
    for column in feature_columns():
        values = pd.to_numeric(output[column], errors="coerce")
        for lag in (63, 252):
            output[f"{column}__delta_{lag}"] = values - output.groupby("ticker", sort=False)[column].shift(lag)
    return output


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _write_gzip(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0}, float_format="%.12g", lineterminator="\n")


def _tree_hash(paths: list[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(sha256(path).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _model(config: dict) -> XGBRanker:
    params = dict(config["model"])
    params.update(objective="rank:ndcg", eval_metric="ndcg@30", ndcg_exp_gain=False, random_state=int(config["seed"]), seed=int(config["seed"]), verbosity=0)
    return XGBRanker(**params)


def _fit(config: dict, frame: pd.DataFrame, columns: list[str]) -> XGBRanker:
    ordered = frame.sort_values(["date", "ticker"], kind="mergesort")
    groups = ordered.groupby("date", sort=False).size().to_numpy(dtype=np.uint32)
    relevance = ordered.groupby("date", sort=False)["target_quality_63"].rank(method="first", ascending=True).astype(np.int32) - 1
    model = _model(config)
    model.fit(ordered[columns], relevance, group=groups)
    return model


def _validate(config: dict) -> None:
    if config.get("schema_version") != "v2-agent-b5-temporal-xgbranker-v1":
        raise ValueError("Agent B5 설정 버전이 일치하지 않습니다.")
    if config.get("final_oos_access") is not False or config.get("portfolio_backtest") is not False:
        raise ValueError("Agent B5는 Final OOS와 포트폴리오 백테스트를 허용하지 않습니다.")
    if config.get("legacy_fundamental_panel") is not False:
        raise ValueError("저커버리지 legacy 재무 패널은 사용할 수 없습니다.")
    if config.get("report_top_size") != 30 or config.get("market_cap_universe_size") != 200:
        raise ValueError("Agent B5 유니버스/Top30 계약이 일치하지 않습니다.")
    if config.get("purge_sessions") != 63 or config.get("embargo_sessions") != 63:
        raise ValueError("Agent B5는 63세션 purge/embargo를 사용합니다.")


def run(config_path: Path, output_root: Path) -> dict[str, object]:
    guard_path(config_path); guard_path(output_root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    _validate(config)
    panel_path = Path(config["factor_panel"])
    market_root = Path(config["market_root"])
    index_path = Path(config["index_file"])
    for path in (panel_path, market_root, index_path):
        guard_path(path)
    panel = pd.read_csv(panel_path, dtype={"ticker": str})
    panel["ticker"] = panel["ticker"].str.zfill(6)
    panel = panel[(panel["date"] >= config["data_start"]) & (panel["date"] <= config["data_end"])].copy()
    index = load_official_index(index_path)
    market, sessions, market_paths = load_market(market_root, int(config["data_start"][:4]), int(config["data_end"][:4]))
    sessions = [day for day in sessions if config["data_start"] <= day <= config["data_end"]]
    dilution = compute_dilution(market, int(config["dilution_lookback_sessions"]))
    daily = add_temporal_features(eligible_daily_panel(panel, dilution, int(config["market_cap_universe_size"])))
    monthly = month_end_rows(daily)
    labeled = attach_quality_target(monthly, market, index, sessions, int(config["target_horizon_sessions"]), float(config["downside_penalty"])).dropna(subset=["target_quality_63"])
    columns = temporal_feature_columns(set(labeled.columns))
    missing = [column for column in columns if column not in labeled.columns]
    if missing:
        raise ValueError(f"Agent B5 feature 누락: {missing[:3]}")
    session_index = {day: i for i, day in enumerate(sessions)}
    folds: list[dict[str, object]] = []
    cutoffs: dict[int, str] = {}
    for year in config["validation_years"]:
        validation = labeled[labeled["date"].str[:4].astype(int).eq(int(year))].copy()
        if validation.empty:
            continue
        first = str(validation["date"].min())
        cutoff_position = session_index[first] - int(config["purge_sessions"]) - int(config["embargo_sessions"]) - 1
        if cutoff_position < 0:
            continue
        cutoff = sessions[cutoff_position]
        train = labeled[labeled["date"] <= cutoff].copy()
        if train["date"].nunique() < int(config["minimum_train_months"]):
            continue
        model = _fit(config, train, columns)
        part = validation[["date", "ticker", "target_quality_63", "target_excess_63", "target_mae_63"]].copy()
        part["score"] = model.predict(validation[columns])
        folds.append({
            "validation_year": int(year), "train_cutoff": cutoff, "train_rows": len(train), "validation_rows": len(validation),
            "quality_rank_ic": daily_ic(part), "ndcg_at_30": ndcg(part, 30),
            "selected_mean_excess": float(part.nlargest(30, "score")["target_excess_63"].mean()),
            "selected_mean_mae": float(part.nlargest(30, "score")["target_mae_63"].mean()),
        })
        cutoffs[int(year)] = cutoff
    fold_frame = pd.DataFrame(folds)
    if fold_frame.empty:
        raise RuntimeError("Agent B5 anchored fold가 없습니다.")
    daily_parts: list[pd.DataFrame] = []
    for year, cutoff in sorted(cutoffs.items()):
        model = _fit(config, labeled[labeled["date"] <= cutoff].copy(), columns)
        scope = daily[daily["date"].str[:4].astype(int).eq(year)][["date", "ticker"]].copy()
        snapshots = month_end_rows(daily[(daily["date"] >= f"{year - 1}-12-01") & (daily["date"] <= f"{year}-12-31")].copy())
        snapshots["agent_b5_score"] = model.predict(snapshots[columns])
        snapshots = snapshots.rename(columns={"date": "score_date"})
        scope["date"] = pd.to_datetime(scope["date"], errors="raise")
        snapshots["score_date"] = pd.to_datetime(snapshots["score_date"], errors="raise")
        expanded = pd.merge_asof(
            scope.sort_values(["date", "ticker"]),
            snapshots[["score_date", "ticker", "agent_b5_score", "statement_year", "statement_quarter"]].sort_values(["score_date", "ticker"]),
            left_on="date", right_on="score_date", by="ticker", direction="backward", allow_exact_matches=False,
        ).dropna(subset=["agent_b5_score"])
        expanded["date"] = expanded["date"].dt.date.astype(str)
        expanded["score_date"] = expanded["score_date"].dt.date.astype(str)
        expanded["agent_b5_percentile"] = expanded.groupby("date")["agent_b5_score"].rank(pct=True, method="average")
        expanded["agent_b5_rank"] = expanded.groupby("date")["agent_b5_score"].rank(method="first", ascending=False)
        expanded["report_top30"] = expanded["agent_b5_rank"] <= 30
        daily_parts.append(expanded)
    scored = pd.concat(daily_parts, ignore_index=True).sort_values(["date", "agent_b5_rank", "ticker"], kind="mergesort")
    output_root.mkdir(parents=True, exist_ok=False)
    fold_frame.to_csv(output_root / "fold_metrics.csv", index=False, float_format="%.12g", lineterminator="\n")
    _write_gzip(scored[["date", "score_date", "ticker", "agent_b5_score", "agent_b5_percentile", "agent_b5_rank", "report_top30", "statement_year", "statement_quarter"]], output_root / "daily_agent_b5_scores.csv.gz")
    _write_json(output_root / "selected_model.json", {"model": "XGBRanker(rank:ndcg)", "features": columns, "temporal_lookbacks": [63, 252], "target": "excess_63_minus_0.5_mae", "fit_policy": "expanding_walk_forward", "xgboost_version": __import__("xgboost").__version__})
    audit = {"factor_rows_loaded": len(panel), "factor_min_date": str(panel["date"].min()), "factor_max_date": str(panel["date"].max()), "market_files_loaded": len(market_paths), "monthly_label_rows": len(labeled), "daily_score_rows": len(scored), "feature_count": len(columns), "legacy_fundamental_rows_loaded": 0, "v2_consumed_development_2022_2023_loaded": True, "portfolio_backtest_run": False, "final_oos_accessed": False}
    _write_json(output_root / "data_audit.json", audit)
    manifest = {"schema_version": "kospi200-agent-b5-temporal-xgbranker-v1", "experiment_id": config["experiment_id"], "status": "CONSUMED_DEVELOPMENT_DIAGNOSTIC_ONLY", "input_sha256": {"config": sha256(config_path), "factor_panel": sha256(panel_path), "official_index": sha256(index_path), "market_tree": _tree_hash(market_paths, market_root)}, "final_oos_accessed": False, "portfolio_backtest_run": False}
    for name in ("fold_metrics.csv", "daily_agent_b5_scores.csv.gz", "selected_model.json", "data_audit.json"):
        manifest.setdefault("output_sha256", {})[name] = sha256(output_root / name)
    _write_json(output_root / "manifest.json", manifest)
    return manifest
