"""Agent B4: sector-relative and temporal fundamental quality model."""

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

from kospi200_agent_b.runner import compute_dilution, eligible_daily_panel, guard_path, load_market, month_end_rows, sha256
from kospi200_agent_b2.runner import attach_quality_target, daily_ic, load_official_index, ndcg
from kospi200_fundamental import FACTOR_IDS


def feature_columns() -> list[str]:
    columns: list[str] = []
    for factor in FACTOR_IDS:
        columns.extend([
            f"{factor}__market_percentile", f"{factor}__market_robust_z",
            f"{factor}__percentile", f"{factor}__robust_z",
            f"{factor}__sector_z_delta_1m", f"{factor}__sector_z_delta_3m",
        ])
    return columns + ["dilution_252__percentile"]


def add_temporal_features(monthly: pd.DataFrame) -> pd.DataFrame:
    output = monthly.sort_values(["ticker", "date"], kind="mergesort").copy()
    for factor in FACTOR_IDS:
        source = pd.to_numeric(output[f"{factor}__robust_z"], errors="coerce")
        grouped = source.groupby(output["ticker"], sort=False)
        output[f"{factor}__sector_z_delta_1m"] = source - grouped.shift(1)
        output[f"{factor}__sector_z_delta_3m"] = source - grouped.shift(3)
    return output


def make_model(name: str, config: dict):
    if name == "ridge_sector_temporal":
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", Ridge(alpha=float(config["ridge_alpha"]))),
        ])
    if name == "hist_sector_temporal":
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", HistGradientBoostingRegressor(
                learning_rate=0.05, max_depth=3, max_iter=100, min_samples_leaf=100,
                l2_regularization=5.0, random_state=int(config["seed"]),
            )),
        ])
    raise ValueError(name)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _write_gzip(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0}, float_format="%.12g", lineterminator="\n")


def _tree_hash(paths: list[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode()); digest.update(b"\0")
        digest.update(sha256(path).encode()); digest.update(b"\n")
    return digest.hexdigest()


def _validate_config(config: dict) -> None:
    if config.get("schema_version") != "v2-agent-b4-sector-temporal-v1":
        raise ValueError("지원하지 않는 Agent B4 설정입니다.")
    if config.get("portfolio_backtest") is not False or config.get("final_oos_access") is not False:
        raise ValueError("Agent B4는 포트폴리오 backtest와 Final OOS 접근을 금지합니다.")
    if config.get("models") != ["ridge_sector_temporal", "hist_sector_temporal"]:
        raise ValueError("Agent B4 모델 후보가 사전등록과 다릅니다.")
    if int(config.get("purge_sessions", 0)) != 63 or int(config.get("embargo_sessions", 0)) != 63:
        raise ValueError("Agent B4 purge/embargo는 각각 63세션이어야 합니다.")


def run(config_path: Path, output_root: Path) -> dict[str, object]:
    guard_path(config_path); guard_path(output_root)
    config = json.loads(config_path.read_text(encoding="utf-8")); _validate_config(config)
    panel_path, market_root, index_path = Path(config["factor_panel"]), Path(config["market_root"]), Path(config["index_file"])
    for path in (panel_path, market_root, index_path): guard_path(path)
    panel = pd.read_csv(panel_path, dtype={"ticker": str}); panel["ticker"] = panel["ticker"].str.zfill(6)
    panel = panel[(panel["date"] >= config["data_start"]) & (panel["date"] <= config["data_end"])].copy()
    required = {
        "sector", "sector_code_source",
        *(column for column in feature_columns()[:-1] if "__sector_z_delta_" not in column),
    }
    missing = sorted(required - set(panel.columns))
    if missing: raise ValueError(f"Agent B4 섹터 패널 열 누락: {missing[:10]}")
    index = load_official_index(index_path)
    market, sessions, market_paths = load_market(market_root, int(config["data_start"][:4]), int(config["data_end"][:4]))
    sessions = [day for day in sessions if config["data_start"] <= day <= config["data_end"]]
    dilution = compute_dilution(market, int(config["dilution_lookback_sessions"]))
    daily = eligible_daily_panel(panel, dilution, int(config["market_cap_universe_size"]))
    monthly = add_temporal_features(month_end_rows(daily))
    labeled = attach_quality_target(monthly, market, index, sessions, 63, float(config["downside_penalty"])).dropna(subset=["target_quality_63"])
    session_i = {day: i for i, day in enumerate(sessions)}
    folds: list[dict[str, object]] = []; cutoffs: dict[int, str] = {}
    for year in config["validation_years"]:
        validation = labeled[labeled["date"].str[:4].astype(int) == int(year)].copy()
        if validation.empty: continue
        first = validation["date"].min(); cutoff_i = session_i[first] - 127
        if cutoff_i < 0: continue
        cutoff = sessions[cutoff_i]; train = labeled[labeled["date"] <= cutoff].copy()
        if train["date"].nunique() < int(config["minimum_train_months"]): continue
        cutoffs[int(year)] = cutoff
        for name in config["models"]:
            model = make_model(name, config); model.fit(train[feature_columns()], train["target_quality_63"])
            part = validation[["date", "ticker", "target_quality_63", "target_excess_63", "target_mae_63"]].copy()
            part["score"] = model.predict(validation[feature_columns()])
            folds.append({
                "model": name, "validation_year": int(year), "train_cutoff": cutoff,
                "train_rows": len(train), "validation_rows": len(validation),
                "quality_rank_ic": daily_ic(part), "ndcg_at_80": ndcg(part, 80),
                "selected_mean_excess": float(part.nlargest(80, "score")["target_excess_63"].mean()),
                "selected_mean_mae": float(part.nlargest(80, "score")["target_mae_63"].mean()),
            })
    fold_frame = pd.DataFrame(folds)
    if fold_frame.empty: raise RuntimeError("Agent B4 유효 walk-forward fold가 없습니다.")
    summary = fold_frame.groupby("model", as_index=False).agg(
        mean_quality_rank_ic=("quality_rank_ic", "mean"), mean_ndcg_at_80=("ndcg_at_80", "mean"),
        positive_ic_years=("quality_rank_ic", lambda x: int((x > 0).sum())), folds=("validation_year", "count"),
    )
    summary["simplicity"] = summary["model"].map({"ridge_sector_temporal": 0, "hist_sector_temporal": 1})
    summary = summary.sort_values(["mean_quality_rank_ic", "mean_ndcg_at_80", "simplicity"], ascending=[False, False, True])
    selected = str(summary.iloc[0]["model"])
    daily_parts: list[pd.DataFrame] = []
    for year, cutoff in sorted(cutoffs.items()):
        train = labeled[labeled["date"] <= cutoff].copy(); model = make_model(selected, config)
        model.fit(train[feature_columns()], train["target_quality_63"])
        snapshots = monthly[monthly["date"].str[:4].astype(int) == year].copy()
        snapshots["agent_b4_score"] = model.predict(snapshots[feature_columns()]); snapshots = snapshots.rename(columns={"date": "score_date"})
        scope = daily[daily["date"].str[:4].astype(int) == year][["date", "ticker"]].copy()
        scope["date"] = pd.to_datetime(scope["date"]); snapshots["score_date"] = pd.to_datetime(snapshots["score_date"])
        expanded = pd.merge_asof(
            scope.sort_values(["date", "ticker"]),
            snapshots[["score_date", "ticker", "agent_b4_score", "statement_year", "statement_quarter"]].sort_values(["score_date", "ticker"]),
            left_on="date", right_on="score_date", by="ticker", direction="backward", allow_exact_matches=False,
        ).dropna(subset=["agent_b4_score"])
        expanded["date"] = expanded["date"].dt.date.astype(str); expanded["score_date"] = expanded["score_date"].dt.date.astype(str)
        expanded["agent_b4_percentile"] = expanded.groupby("date")["agent_b4_score"].rank(pct=True, method="average")
        expanded["agent_b4_rank"] = expanded.groupby("date")["agent_b4_score"].rank(method="first", ascending=False)
        expanded["report_top30"] = expanded["agent_b4_rank"] <= 30
        daily_parts.append(expanded)
    scored = pd.concat(daily_parts, ignore_index=True).sort_values(["date", "agent_b4_rank", "ticker"], kind="mergesort")
    output_root.mkdir(parents=True, exist_ok=False)
    fold_frame.to_csv(output_root / "fold_metrics.csv", index=False, float_format="%.12g", lineterminator="\n")
    summary.to_csv(output_root / "model_summary.csv", index=False, float_format="%.12g", lineterminator="\n")
    _write_gzip(scored[["date", "score_date", "ticker", "agent_b4_score", "agent_b4_percentile", "agent_b4_rank", "report_top30", "statement_year", "statement_quarter"]], output_root / "daily_agent_b4_scores.csv.gz")
    _write_json(output_root / "selected_model.json", {"model": selected, "features": feature_columns(), "target": "excess_63_minus_0.5_mae", "fit_policy": "expanding_walk_forward"})
    audit = {
        "factor_rows_loaded": len(panel), "factor_min_date": str(panel["date"].min()), "factor_max_date": str(panel["date"].max()),
        "sector_missing_rows": int(panel["sector"].isna().sum()), "sector_count": int(panel["sector"].nunique()),
        "monthly_rows": len(monthly), "labeled_rows": len(labeled), "feature_count": len(feature_columns()),
        "market_files_loaded": len(market_paths), "index_code": "1028", "portfolio_backtest_run": False,
        "consumed_development_2022_2023_loaded": True, "final_oos_accessed": False,
    }
    _write_json(output_root / "data_audit.json", audit)
    manifest = {
        "schema_version": "kospi200-agent-b4-sector-temporal-v1", "experiment_id": config["experiment_id"],
        "status": "CONSUMED_DEVELOPMENT_DIAGNOSTIC_ONLY", "selected_model": selected,
        "input_sha256": {"config": sha256(config_path), "factor_panel": sha256(panel_path), "official_index": sha256(index_path), "market_tree": _tree_hash(market_paths, market_root)},
        "final_oos_accessed": False, "portfolio_backtest_run": False,
    }
    for name in ("fold_metrics.csv", "model_summary.csv", "daily_agent_b4_scores.csv.gz", "selected_model.json", "data_audit.json"):
        manifest.setdefault("output_sha256", {})[name] = sha256(output_root / name)
    _write_json(output_root / "manifest.json", manifest)
    return manifest
