"""XGBRanker를 사용하는 Agent B3 학습·점수화 실행기.

이 모듈은 2004~2014 저커버리지 legacy 재무자료를 열지 않고, 기존 표준
펀더멘털 패널과 KRX 2004~2023 가격·지수만 사용한다. 산출물은 소비된
개발기간의 학습/진단 결과이며 독립 OOS나 포트폴리오 결과가 아니다.
"""

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


def _make_model(config: dict, seed: int) -> XGBRanker:
    parameters = dict(config["model"])
    parameters.update(
        objective="rank:ndcg",
        eval_metric="ndcg@30",
        ndcg_exp_gain=False,
        random_state=seed,
        seed=seed,
        verbosity=0,
    )
    return XGBRanker(**parameters)


def _fit_ranker(model: XGBRanker, frame: pd.DataFrame) -> XGBRanker:
    ordered = frame.sort_values(["date", "ticker"], kind="mergesort")
    groups = ordered.groupby("date", sort=False).size().to_numpy(dtype=np.uint32)
    # XGBoost의 rank:ndcg는 각 query 안의 0 이상 정수 relevance를 요구한다.
    # 경제적 target 자체를 바꾸지 않고 날짜별 순위만 relevance로 전달한다.
    relevance = ordered.groupby("date", sort=False)["target_quality_63"].rank(method="first", ascending=True).astype(np.int32) - 1
    model.fit(ordered[feature_columns()], relevance, group=groups)
    return model


def _validate_config(config: dict) -> None:
    if config.get("schema_version") != "v2-phase6-agent-b-xgbranker-v1":
        raise ValueError("지원하지 않는 Agent B3 설정 버전입니다.")
    if config.get("portfolio_backtest") is not False or config.get("final_oos_access") is not False:
        raise ValueError("Agent B3는 포트폴리오·Final OOS를 허용하지 않습니다.")
    if config.get("legacy_fundamental_panel") is not False:
        raise ValueError("legacy 저커버리지 재무 패널은 Agent B3에 사용할 수 없습니다.")
    model = config.get("model", {})
    if model.get("objective") != "rank:ndcg":
        raise ValueError("Agent B3 objective는 rank:ndcg여야 합니다.")
    if int(config.get("report_top_size", 0)) != 30:
        raise ValueError("Agent B3 Top N은 30으로 고정됩니다.")
    if int(config.get("purge_sessions", 0)) != 63 or int(config.get("embargo_sessions", 0)) != 63:
        raise ValueError("Agent B3 purge/embargo는 63세션으로 고정됩니다.")


def run(config_path: Path, output_root: Path) -> dict[str, object]:
    guard_path(config_path)
    guard_path(output_root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    _validate_config(config)

    panel_path = Path(config["factor_panel"])
    market_root = Path(config["market_root"])
    index_path = Path(config["index_file"])
    for path in (panel_path, market_root, index_path):
        guard_path(path)
    panel = pd.read_csv(panel_path, dtype={"ticker": str})
    panel["ticker"] = panel["ticker"].str.zfill(6)
    panel = panel[(panel["date"] >= config["data_start"]) & (panel["date"] <= config["data_end"])].copy()
    if panel.empty:
        raise RuntimeError("Agent B3 표준 Factor 패널이 비어 있습니다.")
    index = load_official_index(index_path)
    market, sessions, market_paths = load_market(market_root, int(config["data_start"][:4]), int(config["data_end"][:4]))
    sessions = [day for day in sessions if config["data_start"] <= day <= config["data_end"]]
    dilution = compute_dilution(market, int(config["dilution_lookback_sessions"]))
    daily = eligible_daily_panel(panel, dilution, int(config["market_cap_universe_size"]))
    monthly = month_end_rows(daily)
    labeled = attach_quality_target(
        monthly, market, index, sessions, int(config["target_horizon_sessions"]), float(config["downside_penalty"])
    ).dropna(subset=["target_quality_63"])
    session_i = {day: i for i, day in enumerate(sessions)}
    folds: list[dict[str, object]] = []
    cutoffs: dict[int, str] = {}
    for year in config["validation_years"]:
        validation = labeled[labeled["date"].str[:4].astype(int) == int(year)].copy()
        if validation.empty:
            continue
        first = validation["date"].min()
        cutoff_i = session_i[first] - int(config["purge_sessions"]) - int(config["embargo_sessions"]) - 1
        if cutoff_i < 0:
            continue
        cutoff = sessions[cutoff_i]
        train = labeled[labeled["date"] <= cutoff].copy()
        if train["date"].nunique() < int(config["minimum_train_months"]):
            continue
        model = _fit_ranker(_make_model(config, int(config["seed"])), train)
        part = validation[["date", "ticker", "target_quality_63", "target_excess_63", "target_mae_63"]].copy()
        part["score"] = model.predict(validation[feature_columns()])
        folds.append(
            {
                "validation_year": int(year),
                "train_cutoff": cutoff,
                "train_rows": len(train),
                "validation_rows": len(validation),
                "quality_rank_ic": daily_ic(part),
                "ndcg_at_30": ndcg(part, 30),
                "selected_mean_excess": float(part.nlargest(30, "score")["target_excess_63"].mean()),
                "selected_mean_mae": float(part.nlargest(30, "score")["target_mae_63"].mean()),
            }
        )
        cutoffs[int(year)] = cutoff
    fold_frame = pd.DataFrame(folds)
    if fold_frame.empty:
        raise RuntimeError("Agent B3 유효한 anchored walk-forward fold가 없습니다.")

    daily_parts: list[pd.DataFrame] = []
    for year, cutoff in sorted(cutoffs.items()):
        train = labeled[labeled["date"] <= cutoff].copy()
        model = _fit_ranker(_make_model(config, int(config["seed"])), train)
        scope = daily[daily["date"].str[:4].astype(int) == year].copy()
        snapshots = month_end_rows(daily[(daily["date"] >= f"{year - 1}-12-01") & (daily["date"] <= f"{year}-12-31")].copy())
        snapshots["agent_b3_score"] = model.predict(snapshots[feature_columns()])
        snapshots = snapshots.rename(columns={"date": "score_date"})
        left = scope[["date", "ticker"]].copy()
        right = snapshots[["score_date", "ticker", "agent_b3_score", "statement_year", "statement_quarter"]].copy()
        left["date"] = pd.to_datetime(left["date"], errors="raise")
        right["score_date"] = pd.to_datetime(right["score_date"], errors="raise")
        expanded = pd.merge_asof(
            left.sort_values(["date", "ticker"]),
            right.sort_values(["score_date", "ticker"]),
            left_on="date", right_on="score_date", by="ticker", direction="backward", allow_exact_matches=False,
        ).dropna(subset=["agent_b3_score"])
        expanded["date"] = expanded["date"].dt.date.astype(str)
        expanded["score_date"] = expanded["score_date"].dt.date.astype(str)
        expanded["agent_b3_percentile"] = expanded.groupby("date")["agent_b3_score"].rank(pct=True, method="average")
        expanded["agent_b3_rank"] = expanded.groupby("date")["agent_b3_score"].rank(method="first", ascending=False)
        expanded["report_top30"] = expanded["agent_b3_rank"] <= 30
        daily_parts.append(expanded)
    scored = pd.concat(daily_parts, ignore_index=True).sort_values(["date", "agent_b3_rank", "ticker"], kind="mergesort")
    output_root.mkdir(parents=True, exist_ok=False)
    fold_frame.to_csv(output_root / "fold_metrics.csv", index=False, float_format="%.12g", lineterminator="\n")
    _write_gzip(scored[["date", "score_date", "ticker", "agent_b3_score", "agent_b3_percentile", "agent_b3_rank", "report_top30", "statement_year", "statement_quarter"]], output_root / "daily_agent_b3_scores.csv.gz")
    _write_json(output_root / "selected_model.json", {"model": "xgb_ranker_ndcg", "features": feature_columns(), "target": "excess_63_minus_0.5_mae", "fit_policy": "expanding_walk_forward", "xgboost_version": __import__("xgboost").__version__})
    audit = {
        "factor_rows_loaded": len(panel), "factor_min_date": str(panel["date"].min()), "factor_max_date": str(panel["date"].max()),
        "index_rows_loaded": len(index), "index_code": "1028", "market_files_loaded": len(market_paths),
        "monthly_label_rows": len(labeled), "daily_score_rows": len(scored), "legacy_fundamental_rows_loaded": 0,
        "v2_consumed_development_2022_2023_loaded": True, "portfolio_backtest_run": False, "final_oos_accessed": False,
    }
    _write_json(output_root / "data_audit.json", audit)
    manifest = {
        "schema_version": "kospi200-agent-b3-xgbranker-v1", "experiment_id": config["experiment_id"],
        "status": "CONSUMED_DEVELOPMENT_TRAINING_ONLY", "model_family": "XGBRanker", "objective": "rank:ndcg",
        "input_sha256": {"config": sha256(config_path), "factor_panel": sha256(panel_path), "official_index": sha256(index_path), "market_tree": _tree_hash(market_paths, market_root)},
        "final_oos_accessed": False, "portfolio_backtest_run": False,
    }
    for name in ("fold_metrics.csv", "daily_agent_b3_scores.csv.gz", "selected_model.json", "data_audit.json"):
        manifest.setdefault("output_sha256", {})[name] = sha256(output_root / name)
    _write_json(output_root / "manifest.json", manifest)
    return manifest
