"""B2 펀더멘털과 C3 LSTM·CNN의 비선형 관계를 성공확률로 결합한다."""

from __future__ import annotations

import json
import pickle
from datetime import date
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

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


META_FEATURES = (
    "agent_b2_percentile", "c3_percentile", "bottom_probability", "volatility_percentile",
    "b_c_product", "b_probability_product", "c_probability_product", "agent_agreement", "c_risk_adjusted",
)


def relationship_features(agent_b: pd.DataFrame, agent_c: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    b = agent_b[["date", "ticker", "agent_b2_percentile"]].copy()
    c = agent_c[["date", "ticker", "agent_c3_score", "bottom_probability", "predicted_volatility"]].copy()
    for frame in (b, c, targets):
        frame["ticker"] = frame["ticker"].astype(str).str.zfill(6)
    c["c3_percentile"] = c.groupby("date")["agent_c3_score"].rank(pct=True, method="average")
    c["volatility_percentile"] = c.groupby("date")["predicted_volatility"].rank(pct=True, method="average")
    frame = c.merge(b, on=["date", "ticker"], how="inner", validate="one_to_one")
    frame = frame.merge(
        targets[["date", "ticker", "target_success_2to1", "target_terminal_net_return_10", "target_net_excess_10"]],
        on=["date", "ticker"], how="left", validate="one_to_one",
    )
    frame["b_c_product"] = frame["agent_b2_percentile"] * frame["c3_percentile"]
    frame["b_probability_product"] = frame["agent_b2_percentile"] * frame["bottom_probability"]
    frame["c_probability_product"] = frame["c3_percentile"] * frame["bottom_probability"]
    frame["agent_agreement"] = 1.0 - (frame["agent_b2_percentile"] - frame["c3_percentile"]).abs()
    frame["c_risk_adjusted"] = frame["c3_percentile"] * (1.0 - frame["volatility_percentile"])
    return frame.sort_values(["date", "ticker"]).reset_index(drop=True)


def fit_relationship(frame: pd.DataFrame, config: dict) -> HistGradientBoostingClassifier:
    usable = frame.dropna(subset=[*META_FEATURES, "target_success_2to1"])
    if len(usable) < int(config["minimum_meta_rows"]):
        raise RuntimeError("Agent D5 관계 모델 학습행이 부족합니다.")
    model = HistGradientBoostingClassifier(
        learning_rate=float(config["meta_model"]["learning_rate"]),
        max_iter=int(config["meta_model"]["max_iter"]),
        max_depth=int(config["meta_model"]["max_depth"]),
        min_samples_leaf=int(config["meta_model"]["min_samples_leaf"]),
        l2_regularization=float(config["meta_model"]["l2_regularization"]),
        early_stopping=False,
        random_state=int(config["seed"]),
    )
    model.fit(usable[list(META_FEATURES)], usable["target_success_2to1"].astype(int))
    return model


def score_relationship(model: HistGradientBoostingClassifier, frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    valid = output[list(META_FEATURES)].notna().all(axis=1)
    output["meta_success_probability"] = np.nan
    output.loc[valid, "meta_success_probability"] = model.predict_proba(output.loc[valid, list(META_FEATURES)])[:, 1]
    output["meta_probability_percentile"] = output.groupby("date")["meta_success_probability"].rank(pct=True, method="average")
    return output


def apply_policy(scored: pd.DataFrame, b_weight: float, probability_threshold: float, score_percentile_threshold: float) -> pd.DataFrame:
    output = scored.copy()
    output["agent_blend"] = b_weight * output["agent_b2_percentile"] + (1.0 - b_weight) * output["c3_percentile"]
    output["decision_score"] = output["meta_success_probability"] * (0.5 + 0.5 * output["agent_blend"])
    output["decision_percentile"] = output.groupby("date")["decision_score"].rank(pct=True, method="average")
    output["entry_eligible"] = (
        (output["meta_success_probability"] >= probability_threshold)
        & (output["decision_percentile"] >= score_percentile_threshold)
    )
    return output


def create_orders(scored: pd.DataFrame, market: pd.DataFrame, sessions: list[str], config: dict, policy_id: str):
    market_index = market.set_index(["date", "ticker"])
    positions = {day: index for index, day in enumerate(sessions)}
    orders, vetoes = [], 0
    interval = int(config["rebalance_interval_sessions"])
    for signal_day, group in scored.groupby("date", sort=True):
        index = positions.get(str(signal_day))
        if index is None or index + 1 >= len(sessions) or index % interval != 0:
            continue
        execute_day = sessions[index + 1]
        eligible = group[group["entry_eligible"]].sort_values(["decision_score", "ticker"], ascending=[False, True]).head(int(config["maximum_positions"]))
        for priority, row in enumerate(eligible.itertuples(index=False)):
            signal_key, execute_key = (str(signal_day), row.ticker), (execute_day, row.ticker)
            if signal_key not in market_index.index or execute_key not in market_index.index:
                continue
            signal_bar, execution_bar = market_index.loc[signal_key], market_index.loc[execute_key]
            if signal_bar["close"] <= 0 or execution_bar["open"] <= 0 or execution_bar["volume"] <= 0:
                continue
            if abs(execution_bar["open"] / signal_bar["close"] - 1.0) > float(config["gap_veto_rate"]):
                vetoes += 1
                continue
            fill = Decimal(str(float(execution_bar["open"]))) * Decimal("1.001")
            orders.append(Order(
                order_id=f"D5:{policy_id}:{signal_day}:{row.ticker}",
                signal_date=date.fromisoformat(str(signal_day)), execute_date=date.fromisoformat(execute_day),
                security_id=row.ticker, side=Side.BUY, target_weight=Decimal(str(config["target_weight"])), priority=priority,
                stop_price=fill * (Decimal("1") - Decimal(str(config["stop_loss_rate"]))),
                target_price=fill * (Decimal("1") + Decimal(str(config["take_profit_rate"]))),
                max_holding_sessions=int(config["maximum_holding_sessions"]), reason="AGENT_D5_RELATIONSHIP_PROBABILITY",
            ))
    return tuple(orders), vetoes


def backtest(scored: pd.DataFrame, market: pd.DataFrame, sessions: list[str], index: pd.DataFrame, config: dict, base_engine, policy_id: str):
    orders, vetoes = create_orders(scored, market, sessions, config, policy_id)
    benchmark = _official_benchmark(index, sessions)
    bars = bars_from_market(market, sessions[0], sessions[-1])
    actions = tuple(item for item in mechanical_actions(market) if sessions[0] <= item.effective_date.isoformat() <= sessions[-1])
    engine = BacktestEngine(
        EngineConfig(initial_cash=Decimal(config["initial_cash_krw"]), max_positions=int(config["maximum_positions"])),
        base_engine.cost_model,
    )
    result = engine.run(tuple(date.fromisoformat(day) for day in sessions), bars, orders, corporate_actions=actions, benchmark_close=benchmark)
    metrics = result.metrics
    annual, positive_years = annual_excess(result)
    return result, {
        "total_return": float(metrics["total_return"]), "benchmark_return": float(metrics["benchmark_total_return"]),
        "net_excess_return": float(metrics["total_return"]) - float(metrics["benchmark_total_return"]),
        "sharpe": float(metrics["sharpe_zero_rf"]) if metrics["sharpe_zero_rf"] is not None else np.nan,
        "mdd": float(metrics["max_drawdown"]), "turnover": float(metrics["turnover_on_average_equity"]),
        "average_cash_weight": float(metrics["average_cash_weight"]), "closed_trades": int(metrics["closed_trades"]),
        "profit_factor": float(metrics["profit_factor"]) if metrics.get("profit_factor") is not None else np.nan,
        "positive_annual_excess_years": positive_years, "annual_excess_json": json.dumps(annual, sort_keys=True, separators=(",", ":")),
        "orders_created": len(orders), "gap_vetoes": vetoes, "reconciliation": metrics["reconciliation"],
    }


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def run(config_path: Path, output_root: Path) -> dict[str, object]:
    guard_path(config_path); guard_path(output_root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("final_oos_access") is not False or config.get("evidence_status") != "CONSUMED_DEVELOPMENT_DIAGNOSTIC_ONLY":
        raise ValueError("Agent D5 데이터 경계 계약 불일치")
    if config["diagnostic_start"] < "2021-01-01" or config["diagnostic_end"] > "2023-12-31":
        raise ValueError("Agent D5 진단 기간 불일치")
    paths = {key: Path(config[key]) for key in (
        "agent_b2_scores", "agent_b2_manifest", "agent_c3_scores", "agent_c3_manifest", "membership_root",
        "market_root", "index_file", "engine_config", "cost_schedule",
    )}
    for path in paths.values(): guard_path(path)
    agent_b, b_manifest = _read_upstream(paths["agent_b2_scores"], paths["agent_b2_manifest"], "daily_agent_b2_scores.csv.gz")
    agent_c, c_manifest = _read_upstream(paths["agent_c3_scores"], paths["agent_c3_manifest"], "daily_agent_c3_scores.csv.gz")
    membership, membership_paths = load_membership(paths["membership_root"], config["data_start"], config["diagnostic_end"])
    market, all_sessions, market_paths = load_market(paths["market_root"], set(membership["ticker"]), 2019, 2023)
    sessions = [day for day in all_sessions if config["data_start"] <= day <= config["diagnostic_end"]]
    index = load_official_index(paths["index_file"])
    targets = target_frame(market, index, sessions, int(config["target_horizon_sessions"]), float(config["stop_loss_rate"]), float(config["take_profit_rate"]), float(config["roundtrip_target_cost_rate"]))
    frame = relationship_features(agent_b, agent_c, targets)

    selection_fit = frame[(frame["date"] >= config["data_start"]) & (frame["date"] <= config["selection_fit_end"])].copy()
    selection_validation = frame[(frame["date"] >= config["selection_validation_start"]) & (frame["date"] <= config["selection_validation_end"])].copy()
    selection_model = fit_relationship(selection_fit, config)
    validation_scored = score_relationship(selection_model, selection_validation)
    valid_probability = validation_scored.dropna(subset=["meta_success_probability", "target_success_2to1"])
    selection_auc = float(roc_auc_score(valid_probability["target_success_2to1"], valid_probability["meta_success_probability"]))
    base_engine = engine_from_files(paths["engine_config"], paths["cost_schedule"])
    selection_sessions = [day for day in sessions if config["selection_validation_start"] <= day <= config["selection_validation_end"]]
    selection_market = market[(market["date"] >= selection_sessions[0]) & (market["date"] <= selection_sessions[-1])].copy()
    selection_rows = []
    for b_weight in config["agent_b_weight_grid"]:
        for probability_threshold in config["probability_threshold_grid"]:
            for percentile_threshold in config["score_percentile_threshold_grid"]:
                policy_id = f"B{int(100*float(b_weight)):03d}_P{int(100*float(probability_threshold)):03d}_Q{int(100*float(percentile_threshold)):03d}"
                policy_scores = apply_policy(validation_scored, float(b_weight), float(probability_threshold), float(percentile_threshold))
                _, metrics = backtest(policy_scores, selection_market, selection_sessions, index, config, base_engine, policy_id)
                selection_rows.append({"policy_id": policy_id, "agent_b_weight": float(b_weight), "agent_c_weight": 1.0-float(b_weight), "probability_threshold": float(probability_threshold), "score_percentile_threshold": float(percentile_threshold), **metrics})
    selection_metrics = pd.DataFrame(selection_rows).sort_values(
        ["net_excess_return", "sharpe", "turnover", "policy_id"], ascending=[False, False, True, True]
    ).reset_index(drop=True)
    selected = selection_metrics.iloc[0].to_dict()

    final_fit = frame[(frame["date"] >= config["data_start"]) & (frame["date"] <= config["final_fit_end"])].copy()
    final_model = fit_relationship(final_fit, config)
    diagnostic_frame = frame[(frame["date"] >= config["diagnostic_start"]) & (frame["date"] <= config["diagnostic_end"])].copy()
    diagnostic_scored = score_relationship(final_model, diagnostic_frame)
    diagnostic_scored = apply_policy(diagnostic_scored, float(selected["agent_b_weight"]), float(selected["probability_threshold"]), float(selected["score_percentile_threshold"]))
    diagnostic_sessions = [day for day in sessions if config["diagnostic_start"] <= day <= config["diagnostic_end"]]
    diagnostic_market = market[(market["date"] >= diagnostic_sessions[0]) & (market["date"] <= diagnostic_sessions[-1])].copy()
    final_result, diagnostic_metrics = backtest(diagnostic_scored, diagnostic_market, diagnostic_sessions, index, config, base_engine, str(selected["policy_id"]))
    diagnostic_valid = diagnostic_scored.dropna(subset=["meta_success_probability", "target_success_2to1"])
    diagnostic_auc = float(roc_auc_score(diagnostic_valid["target_success_2to1"], diagnostic_valid["meta_success_probability"]))
    gates = {
        "positive_net_excess": diagnostic_metrics["net_excess_return"] > 0,
        "positive_excess_years_at_least_2_of_3": diagnostic_metrics["positive_annual_excess_years"] >= 2,
        "positive_sharpe": diagnostic_metrics["sharpe"] > 0,
        "mdd_above_minus_30pct": diagnostic_metrics["mdd"] > -0.30,
        "reconciliation": diagnostic_metrics["reconciliation"] == "PASS",
    }
    decision = "RETAIN_FOR_FORWARD_SHADOW_NOT_OOS" if all(gates.values()) else "REJECT_FOR_TRADING_ARCHIVE_STRUCTURE"

    output_root.mkdir(parents=True, exist_ok=False)
    selection_metrics.to_csv(output_root / "selection_grid_metrics.csv", index=False, float_format="%.12g", lineterminator="\n")
    score_columns = ["date", "ticker", *META_FEATURES, "meta_success_probability", "agent_blend", "decision_score", "decision_percentile", "entry_eligible"]
    diagnostic_scored[score_columns].to_csv(output_root / "daily_agent_d5_scores.csv.gz", index=False, compression={"method": "gzip", "mtime": 0}, float_format="%.12g", lineterminator="\n")
    with (output_root / "relationship_model.pkl").open("wb") as handle:
        pickle.dump(final_model, handle, protocol=5)
    selected_run_hashes = write_result(final_result, output_root / "selected_run")
    _json(output_root / "selected_policy.json", {"selection_auc": selection_auc, **{key: selected[key] for key in ("policy_id", "agent_b_weight", "agent_c_weight", "probability_threshold", "score_percentile_threshold")}})
    _json(output_root / "diagnostic.json", {"decision": decision, "gates": gates, "meta_auc": diagnostic_auc, "metrics": diagnostic_metrics, "evidence_status": config["evidence_status"]})
    audit = {
        "agent_b2_experiment": b_manifest["experiment_id"], "agent_c3_experiment": c_manifest["experiment_id"],
        "relationship_rows": len(frame), "selection_fit_rows": len(selection_fit), "selection_validation_rows": len(selection_validation),
        "final_fit_rows": len(final_fit), "diagnostic_rows": len(diagnostic_frame), "membership_rows_loaded": len(membership),
        "market_files_loaded": len(market_paths), "legacy_dart_rows_used": 0,
        "legacy_dart_reason": "NUMERIC_ACCOUNT_AND_IDENTITY_AUDIT_NOT_COMPLETED",
        "v2_2021_2023_consumed_development_loaded": True, "final_oos_accessed": False,
    }
    _json(output_root / "data_audit.json", audit)
    manifest = {
        "schema_version": "kospi200-agent-d5-relationship-probability-v1", "experiment_id": config["experiment_id"],
        "status": decision, "selected_policy": str(selected["policy_id"]), "evidence_status": config["evidence_status"],
        "input_sha256": {"config": sha256(config_path), "agent_b2_scores": sha256(paths["agent_b2_scores"]), "agent_c3_scores": sha256(paths["agent_c3_scores"]), "official_index": sha256(paths["index_file"]), "membership_tree": tree_hash(membership_paths, paths["membership_root"]), "market_tree": tree_hash(market_paths, paths["market_root"])},
        "selected_run_hashes": selected_run_hashes, "final_oos_accessed": False,
    }
    for name in ("selection_grid_metrics.csv", "daily_agent_d5_scores.csv.gz", "relationship_model.pkl", "selected_policy.json", "diagnostic.json", "data_audit.json"):
        manifest.setdefault("output_sha256", {})[name] = sha256(output_root / name)
    _json(output_root / "manifest.json", manifest)
    return manifest
