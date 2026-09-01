"""B2 Top30 안에서 C3와 메타 초과수익 순위를 비교하는 Agent D6."""

from __future__ import annotations

import json
import pickle
from datetime import date
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from kospi100_backtest.config import engine_from_files
from kospi100_backtest.engine import BacktestEngine, EngineConfig
from kospi100_backtest.io import write_result
from kospi100_backtest.types import Order, Side
from kospi200_agent_b2.runner import load_official_index
from kospi200_agent_c.runner import guard_path, sha256
from kospi200_agent_c3.runner import target_frame
from kospi200_agent_c_independent.runner import load_membership, tree_hash
from kospi200_agent_d.runner import annual_excess, bars_from_market, load_market, mechanical_actions
from kospi200_agent_d2.runner import _official_benchmark, _read_upstream


METHODS = ("C3_TOP3_CONTROL", "B2_TOP30_META_RANK")
META_FEATURES = (
    "agent_b2_percentile",
    "c3_percentile",
    "bottom_probability",
    "volatility_percentile",
    "b_c_product",
    "b_bottom_product",
    "c_bottom_product",
    "agent_agreement",
    "c_risk_adjusted",
)


def build_meta_frame(agent_b: pd.DataFrame, agent_c: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    required_b = {"date", "ticker", "agent_b2_percentile", "report_top30"}
    required_c = {"date", "ticker", "agent_c3_score", "bottom_probability", "predicted_volatility"}
    if not required_b.issubset(agent_b.columns) or not required_c.issubset(agent_c.columns):
        raise ValueError("Agent B2/C3 점수 계약 열이 누락되었습니다.")
    b = agent_b[["date", "ticker", "agent_b2_percentile", "report_top30"]].copy()
    c = agent_c[["date", "ticker", "agent_c3_score", "bottom_probability", "predicted_volatility"]].copy()
    t = targets[["date", "ticker", "target_net_excess_10"]].copy()
    for frame in (b, c, t):
        frame["ticker"] = frame["ticker"].astype(str).str.zfill(6)
    c["c3_percentile"] = c.groupby("date")["agent_c3_score"].rank(pct=True, method="average")
    c["volatility_percentile"] = c.groupby("date")["predicted_volatility"].rank(pct=True, method="average")
    output = c.merge(b, on=["date", "ticker"], how="inner", validate="one_to_one")
    output = output.merge(t, on=["date", "ticker"], how="left", validate="one_to_one")
    output["report_top30"] = output["report_top30"].eq(True)
    output["b_c_product"] = output["agent_b2_percentile"] * output["c3_percentile"]
    output["b_bottom_product"] = output["agent_b2_percentile"] * output["bottom_probability"]
    output["c_bottom_product"] = output["c3_percentile"] * output["bottom_probability"]
    output["agent_agreement"] = 1.0 - (output["agent_b2_percentile"] - output["c3_percentile"]).abs()
    output["c_risk_adjusted"] = output["c3_percentile"] * (1.0 - output["volatility_percentile"])
    return output.sort_values(["date", "ticker"]).reset_index(drop=True)


def fit_meta_rank(frame: pd.DataFrame, config: dict) -> HistGradientBoostingRegressor:
    usable = frame.dropna(subset=[*META_FEATURES, "target_net_excess_10"])
    if len(usable) < int(config["minimum_meta_rows"]):
        raise RuntimeError("Agent D6 메타 회귀 학습행이 부족합니다.")
    params = config["meta_model"]
    model = HistGradientBoostingRegressor(
        learning_rate=float(params["learning_rate"]),
        max_iter=int(params["max_iter"]),
        max_depth=int(params["max_depth"]),
        min_samples_leaf=int(params["min_samples_leaf"]),
        l2_regularization=float(params["l2_regularization"]),
        early_stopping=False,
        random_state=int(config["seed"]),
    )
    model.fit(usable[list(META_FEATURES)], usable["target_net_excess_10"])
    return model


def walk_forward_scores(frame: pd.DataFrame, sessions: list[str], config: dict) -> tuple[pd.DataFrame, dict[str, object]]:
    scored_parts: list[pd.DataFrame] = []
    models: dict[str, HistGradientBoostingRegressor] = {}
    folds: list[dict[str, object]] = []
    purge = int(config["purge_sessions"])
    for year in config["evaluation_years"]:
        eval_rows = frame[frame["date"].str[:4].astype(int).eq(int(year))].copy()
        if eval_rows.empty:
            raise RuntimeError(f"Agent D6 평가행이 없습니다: {year}")
        first_eval = str(eval_rows["date"].min())
        prior_sessions = [day for day in sessions if day < first_eval]
        if len(prior_sessions) <= purge:
            raise RuntimeError(f"Agent D6 purge 적용 후 학습기간이 없습니다: {year}")
        train_end = prior_sessions[-purge - 1]
        train_rows = frame[(frame["date"] >= config["training_start"]) & (frame["date"] <= train_end)].copy()
        model = fit_meta_rank(train_rows, config)
        valid = eval_rows[list(META_FEATURES)].notna().all(axis=1)
        eval_rows["meta_expected_net_excess"] = np.nan
        eval_rows.loc[valid, "meta_expected_net_excess"] = model.predict(eval_rows.loc[valid, list(META_FEATURES)])
        scored_parts.append(eval_rows)
        models[str(year)] = model
        folds.append({
            "evaluation_year": int(year),
            "train_start": str(train_rows["date"].min()),
            "train_end_after_purge": train_end,
            "train_rows": int(train_rows.dropna(subset=[*META_FEATURES, "target_net_excess_10"]).shape[0]),
            "evaluation_start": first_eval,
            "evaluation_end": str(eval_rows["date"].max()),
            "evaluation_rows": int(len(eval_rows)),
            "purge_sessions": purge,
        })
    return pd.concat(scored_parts, ignore_index=True), {"folds": folds, "models": models}


def apply_method(scored: pd.DataFrame, method: str, daily_limit: int) -> pd.DataFrame:
    if method not in METHODS:
        raise ValueError(method)
    output = scored.copy()
    if method == "B2_TOP30_META_RANK":
        output = output[output["report_top30"] & output["meta_expected_net_excess"].notna()].copy()
        output["decision_score"] = output["meta_expected_net_excess"]
    else:
        output["decision_score"] = output["agent_c3_score"]
    output["decision_rank"] = output.groupby("date")["decision_score"].rank(method="first", ascending=False)
    output["entry_eligible"] = output["decision_rank"] <= int(daily_limit)
    output["method"] = method
    return output.sort_values(["date", "decision_rank", "ticker"]).reset_index(drop=True)


def create_orders(scored: pd.DataFrame, market: pd.DataFrame, sessions: list[str], config: dict, method: str):
    market_index = market.set_index(["date", "ticker"])
    positions = {day: index for index, day in enumerate(sessions)}
    orders: list[Order] = []
    vetoes = 0
    interval = int(config["rebalance_interval_sessions"])
    for signal_day, group in scored.groupby("date", sort=True):
        session_number = positions.get(str(signal_day))
        if session_number is None or session_number + 1 >= len(sessions) or session_number % interval != 0:
            continue
        execute_day = sessions[session_number + 1]
        eligible = group[group["entry_eligible"]].sort_values(["decision_rank", "ticker"])
        for priority, row in enumerate(eligible.itertuples(index=False)):
            signal_key = (str(signal_day), row.ticker)
            execute_key = (execute_day, row.ticker)
            if signal_key not in market_index.index or execute_key not in market_index.index:
                continue
            signal_bar = market_index.loc[signal_key]
            execution_bar = market_index.loc[execute_key]
            if signal_bar["close"] <= 0 or execution_bar["open"] <= 0 or execution_bar["volume"] <= 0:
                continue
            if abs(execution_bar["open"] / signal_bar["close"] - 1.0) > float(config["gap_veto_rate"]):
                vetoes += 1
                continue
            fill = Decimal(str(float(execution_bar["open"]))) * Decimal("1.001")
            orders.append(Order(
                order_id=f"D6:{method}:{signal_day}:{row.ticker}",
                signal_date=date.fromisoformat(str(signal_day)),
                execute_date=date.fromisoformat(execute_day),
                security_id=row.ticker,
                side=Side.BUY,
                target_weight=Decimal(str(config["target_weight"])),
                priority=priority,
                stop_price=fill * (Decimal("1") - Decimal(str(config["stop_loss_rate"]))),
                target_price=fill * (Decimal("1") + Decimal(str(config["take_profit_rate"]))),
                max_holding_sessions=int(config["maximum_holding_sessions"]),
                reason=f"AGENT_D6_{method}",
            ))
    return tuple(orders), vetoes


def _backtest(scored: pd.DataFrame, market: pd.DataFrame, sessions: list[str], index: pd.DataFrame, config: dict, base_engine, method: str):
    orders, vetoes = create_orders(scored, market, sessions, config, method)
    benchmark = _official_benchmark(index, sessions)
    bars = bars_from_market(market, sessions[0], sessions[-1])
    actions = tuple(a for a in mechanical_actions(market) if sessions[0] <= a.effective_date.isoformat() <= sessions[-1])
    engine = BacktestEngine(EngineConfig(initial_cash=Decimal(config["initial_cash_krw"]), max_positions=int(config["maximum_positions"])), base_engine.cost_model)
    result = engine.run(tuple(date.fromisoformat(day) for day in sessions), bars, orders, corporate_actions=actions, benchmark_close=benchmark)
    metrics = result.metrics
    annual, positive_years = annual_excess(result)
    row = {
        "candidate": method,
        "total_return": float(metrics["total_return"]),
        "benchmark_return": float(metrics["benchmark_total_return"]),
        "net_excess_return": float(metrics["total_return"]) - float(metrics["benchmark_total_return"]),
        "sharpe": float(metrics["sharpe_zero_rf"]) if metrics["sharpe_zero_rf"] is not None else np.nan,
        "mdd": float(metrics["max_drawdown"]),
        "positive_annual_excess_years": positive_years,
        "annual_excess_json": json.dumps(annual, sort_keys=True, separators=(",", ":")),
        "closed_trades": int(metrics["closed_trades"]),
        "turnover": float(metrics["turnover_on_average_equity"]),
        "average_cash_weight": float(metrics["average_cash_weight"]),
        "orders_created": len(orders),
        "gap_vetoes": vetoes,
        "reconciliation": metrics["reconciliation"],
    }
    return result, row


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def run(config_path: Path, output_root: Path) -> dict[str, object]:
    guard_path(config_path)
    guard_path(output_root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if tuple(config["methods"]) != METHODS or config.get("final_oos_access") is not False:
        raise ValueError("Agent D6 사전등록 방법 또는 OOS 경계가 일치하지 않습니다.")
    if config.get("evidence_status") != "CONSUMED_DEVELOPMENT_DIAGNOSTIC_ONLY":
        raise ValueError("Agent D6는 소비된 개발자료 진단으로만 실행할 수 있습니다.")
    if max(config["evaluation_years"]) > 2023 or config["data_end"] > "2023-12-31":
        raise ValueError("Agent D6는 2023년 이후 자료를 읽을 수 없습니다.")
    paths = {key: Path(config[key]) for key in (
        "agent_b2_scores", "agent_b2_manifest", "agent_c3_scores", "agent_c3_manifest",
        "membership_root", "market_root", "index_file", "engine_config", "cost_schedule",
    )}
    for path in paths.values():
        guard_path(path)
    agent_b, b_manifest = _read_upstream(paths["agent_b2_scores"], paths["agent_b2_manifest"], "daily_agent_b2_scores.csv.gz")
    agent_c, c_manifest = _read_upstream(paths["agent_c3_scores"], paths["agent_c3_manifest"], "daily_agent_c3_scores.csv.gz")
    membership, membership_paths = load_membership(paths["membership_root"], config["data_start"], config["data_end"])
    market, all_sessions, market_paths = load_market(paths["market_root"], set(membership["ticker"]), int(config["data_start"][:4]), int(config["data_end"][:4]))
    sessions = [day for day in all_sessions if config["data_start"] <= day <= config["data_end"]]
    index = load_official_index(paths["index_file"])
    targets = target_frame(market, index, sessions, int(config["target_horizon_sessions"]), float(config["stop_loss_rate"]), float(config["take_profit_rate"]), float(config["roundtrip_target_cost_rate"]))
    frame = build_meta_frame(agent_b, agent_c, targets)
    frame = frame[(frame["date"] >= config["data_start"]) & (frame["date"] <= config["data_end"])].copy()
    scored, walk_forward = walk_forward_scores(frame, sessions, config)
    evaluation_start = f"{min(config['evaluation_years'])}-01-01"
    evaluation_sessions = [day for day in sessions if evaluation_start <= day <= config["data_end"]]
    evaluation_market = market[(market["date"] >= evaluation_sessions[0]) & (market["date"] <= evaluation_sessions[-1])].copy()
    base_engine = engine_from_files(paths["engine_config"], paths["cost_schedule"])
    rows: list[dict[str, object]] = []
    results = {}
    method_audit = {}
    score_outputs = []
    for method in METHODS:
        method_scores = apply_method(scored, method, int(config["daily_candidate_limit"]))
        result, row = _backtest(method_scores, evaluation_market, evaluation_sessions, index, config, base_engine, method)
        rows.append(row)
        results[method] = result
        method_audit[method] = {"scored_rows": len(method_scores), "orders_created": row["orders_created"], "gap_vetoes": row["gap_vetoes"]}
        score_outputs.append(method_scores[["date", "ticker", "method", "decision_score", "decision_rank", "entry_eligible"]])
    metrics = pd.DataFrame(rows).sort_values("candidate").reset_index(drop=True)
    serial = metrics.loc[metrics["candidate"].eq("B2_TOP30_META_RANK")].iloc[0]
    control = metrics.loc[metrics["candidate"].eq("C3_TOP3_CONTROL")].iloc[0]
    gates = {
        "positive_net_excess": bool(serial["net_excess_return"] > 0),
        "positive_annual_excess_at_least_3_of_4": bool(serial["positive_annual_excess_years"] >= 3),
        "positive_sharpe": bool(serial["sharpe"] > 0),
        "mdd_above_minus_30pct": bool(serial["mdd"] > -0.30),
        "improves_c3_control_net_excess": bool(serial["net_excess_return"] > control["net_excess_return"]),
        "reconciliation": serial["reconciliation"] == "PASS",
    }
    decision = "RETAIN_D6_FOR_FORWARD_SHADOW_ONLY" if all(gates.values()) else "REJECT_D6_FOR_TRADING"
    output_root.mkdir(parents=True, exist_ok=False)
    metrics.to_csv(output_root / "candidate_metrics.csv", index=False, float_format="%.12g", lineterminator="\n")
    pd.concat(score_outputs, ignore_index=True).sort_values(["method", "date", "decision_rank", "ticker"]).to_csv(
        output_root / "daily_agent_d6_scores.csv.gz", index=False, compression={"method": "gzip", "mtime": 0}, float_format="%.12g", lineterminator="\n"
    )
    model_dir = output_root / "models"
    model_dir.mkdir()
    for year, model in sorted(walk_forward["models"].items()):
        with (model_dir / f"meta_rank_{year}.pkl").open("wb") as handle:
            pickle.dump(model, handle, protocol=5)
    selected_hashes = write_result(results["B2_TOP30_META_RANK"], output_root / "selected_run")
    _json(output_root / "walk_forward_audit.json", {"folds": walk_forward["folds"]})
    _json(output_root / "decision.json", {"decision": decision, "gates": gates, "selected_for_audit": "B2_TOP30_META_RANK", "control": "C3_TOP3_CONTROL", "evidence_status": config["evidence_status"]})
    audit = {
        "agent_b2_experiment": b_manifest["experiment_id"], "agent_c3_experiment": c_manifest["experiment_id"],
        "meta_rows": len(frame), "evaluation_rows": len(scored), "membership_rows_loaded": len(membership),
        "market_files_loaded": len(market_paths), "maximum_loaded_date": str(market["date"].max()),
        "v2_2020_2023_consumed_development_loaded": True, "legacy_v1_final_oos_accessed": False,
        "final_oos_accessed": False, "method_audit": method_audit,
    }
    _json(output_root / "data_audit.json", audit)
    manifest = {
        "schema_version": "kospi200-agent-d6-walk-forward-meta-rank-v1", "experiment_id": config["experiment_id"],
        "status": decision, "selected_for_audit": "B2_TOP30_META_RANK", "evidence_status": config["evidence_status"],
        "input_sha256": {
            "config": sha256(config_path), "agent_b2_scores": sha256(paths["agent_b2_scores"]), "agent_b2_manifest": sha256(paths["agent_b2_manifest"]),
            "agent_c3_scores": sha256(paths["agent_c3_scores"]), "agent_c3_manifest": sha256(paths["agent_c3_manifest"]),
            "official_index": sha256(paths["index_file"]), "membership_tree": tree_hash(membership_paths, paths["membership_root"]),
            "market_tree": tree_hash(market_paths, paths["market_root"]), "engine_config": sha256(paths["engine_config"]), "cost_schedule": sha256(paths["cost_schedule"]),
        },
        "selected_run_hashes": selected_hashes, "model_sha256": {p.name: sha256(p) for p in sorted(model_dir.glob("*.pkl"))},
        "final_oos_accessed": False,
    }
    for name in ("candidate_metrics.csv", "daily_agent_d6_scores.csv.gz", "walk_forward_audit.json", "decision.json", "data_audit.json"):
        manifest.setdefault("output_sha256", {})[name] = sha256(output_root / name)
    _json(output_root / "manifest.json", manifest)
    return manifest
