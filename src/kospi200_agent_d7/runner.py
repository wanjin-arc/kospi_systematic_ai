"""B5 Top30과 C6 LSTM/CNN 점수를 시간 분리해 결합하는 Agent D7."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from kospi100_backtest.config import engine_from_files
from kospi100_backtest.engine import BacktestEngine, EngineConfig
from kospi100_backtest.io import write_result
from kospi100_backtest.types import Order, Side
from kospi200_agent_b2.runner import load_official_index
from kospi200_agent_c.runner import guard_path, sha256
from kospi200_agent_c_independent.runner import load_membership, tree_hash
from kospi200_agent_d.runner import annual_excess, bars_from_market, load_market, mechanical_actions
from kospi200_agent_d2.runner import _official_benchmark, _read_upstream


def build_frame(agent_b: pd.DataFrame, agent_c: pd.DataFrame) -> pd.DataFrame:
    b = agent_b[["date", "ticker", "agent_b5_percentile", "report_top30"]].copy()
    c = agent_c[["date", "ticker", "agent_c3_score", "bottom_probability", "predicted_volatility"]].copy()
    for frame in (b, c):
        frame["ticker"] = frame["ticker"].astype(str).str.zfill(6)
    c["c6_percentile"] = c.groupby("date")["agent_c3_score"].rank(pct=True, method="average")
    c["volatility_percentile"] = c.groupby("date")["predicted_volatility"].rank(pct=True, method="average")
    output = b.merge(c, on=["date", "ticker"], how="inner", validate="one_to_one")
    output["report_top30"] = output["report_top30"].eq(True)
    return output.sort_values(["date", "ticker"]).reset_index(drop=True)


def apply_policy(frame: pd.DataFrame, b_weight: float, config: dict) -> pd.DataFrame:
    output = frame[frame["report_top30"]].copy()
    output["decision_score"] = float(b_weight) * output["agent_b5_percentile"] + (1.0 - float(b_weight)) * output["c6_percentile"]
    output["decision_rank"] = output.groupby("date")["decision_score"].rank(method="first", ascending=False)
    output["entry_eligible"] = (
        (output["bottom_probability"] >= float(config["entry_probability_low"]))
        & (output["decision_rank"] <= int(config["daily_candidate_limit"]))
    )
    output["target_weight"] = np.where(
        output["bottom_probability"] >= float(config["entry_probability_high"]),
        float(config["target_weight_high"]),
        float(config["target_weight_low"]),
    )
    return output.sort_values(["date", "decision_rank", "ticker"]).reset_index(drop=True)


def create_orders(scored: pd.DataFrame, market: pd.DataFrame, sessions: list[str], config: dict, policy_id: str):
    market_index = market.set_index(["date", "ticker"])
    session_index = {day: index for index, day in enumerate(sessions)}
    orders: list[Order] = []
    vetoes = 0
    for signal_day, group in scored.groupby("date", sort=True):
        index = session_index.get(str(signal_day))
        if index is None or index + 1 >= len(sessions):
            continue
        execute_day = sessions[index + 1]
        for priority, row in enumerate(group[group["entry_eligible"]].sort_values(["decision_rank", "ticker"]).itertuples(index=False)):
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
                order_id=f"D7:{policy_id}:{signal_day}:{row.ticker}", signal_date=date.fromisoformat(str(signal_day)), execute_date=date.fromisoformat(execute_day),
                security_id=row.ticker, side=Side.BUY, target_weight=Decimal(str(float(row.target_weight))), priority=priority,
                stop_price=fill * (Decimal("1") - Decimal(str(config["stop_loss_rate"]))),
                target_price=fill * (Decimal("1") + Decimal(str(config["take_profit_rate"]))),
                max_holding_sessions=int(config["maximum_holding_sessions"]), reason="AGENT_D7_SERIAL_B5_C6",
            ))
    return tuple(orders), vetoes


def _backtest(scored: pd.DataFrame, market: pd.DataFrame, sessions: list[str], index: pd.DataFrame, config: dict, base_engine, policy_id: str):
    orders, vetoes = create_orders(scored, market, sessions, config, policy_id)
    benchmark = _official_benchmark(index, sessions)
    bars = bars_from_market(market, sessions[0], sessions[-1])
    actions = tuple(action for action in mechanical_actions(market) if sessions[0] <= action.effective_date.isoformat() <= sessions[-1])
    engine = BacktestEngine(EngineConfig(initial_cash=Decimal(config["initial_cash_krw"]), max_positions=int(config["maximum_positions"])), base_engine.cost_model)
    result = engine.run(tuple(date.fromisoformat(day) for day in sessions), bars, orders, corporate_actions=actions, benchmark_close=benchmark)
    metrics = result.metrics
    annual, positive_years = annual_excess(result)
    return result, {
        "total_return": float(metrics["total_return"]), "benchmark_return": float(metrics["benchmark_total_return"]),
        "net_excess_return": float(metrics["total_return"]) - float(metrics["benchmark_total_return"]),
        "sharpe": float(metrics["sharpe_zero_rf"]) if metrics["sharpe_zero_rf"] is not None else np.nan,
        "mdd": float(metrics["max_drawdown"]), "positive_annual_excess_years": positive_years,
        "annual_excess_json": json.dumps(annual, sort_keys=True, separators=(",", ":")), "closed_trades": int(metrics["closed_trades"]),
        "turnover": float(metrics["turnover_on_average_equity"]), "average_cash_weight": float(metrics["average_cash_weight"]),
        "orders_created": len(orders), "gap_vetoes": vetoes, "reconciliation": metrics["reconciliation"],
    }


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def run(config_path: Path, output_root: Path) -> dict[str, object]:
    guard_path(config_path); guard_path(output_root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("final_oos_access") is not False or config.get("evidence_status") != "CONSUMED_DEVELOPMENT_DIAGNOSTIC_ONLY":
        raise ValueError("Agent D7 데이터 경계 계약이 일치하지 않습니다.")
    if config.get("same_bar_policy") != "STOP_FIRST":
        raise ValueError("Agent D7은 STOP_FIRST만 사용합니다.")
    paths = {key: Path(config[key]) for key in ("agent_b5_scores", "agent_b5_manifest", "agent_c6_scores", "agent_c6_manifest", "membership_root", "market_root", "index_file", "engine_config", "cost_schedule")}
    for path in paths.values(): guard_path(path)
    agent_b, b_manifest = _read_upstream(paths["agent_b5_scores"], paths["agent_b5_manifest"], "daily_agent_b5_scores.csv.gz")
    agent_c, c_manifest = _read_upstream(paths["agent_c6_scores"], paths["agent_c6_manifest"], "daily_agent_c3_scores.csv.gz")
    frame = build_frame(agent_b, agent_c)
    membership, membership_paths = load_membership(paths["membership_root"], config["data_start"], config["diagnostic_end"])
    market, all_sessions, market_paths = load_market(paths["market_root"], set(membership["ticker"]), int(config["data_start"][:4]), int(config["diagnostic_end"][:4]))
    sessions = [day for day in all_sessions if config["data_start"] <= day <= config["diagnostic_end"]]
    index = load_official_index(paths["index_file"])
    base_engine = engine_from_files(paths["engine_config"], paths["cost_schedule"])
    selection_sessions = [day for day in sessions if config["selection_start"] <= day <= config["selection_end"]]
    selection_market = market[(market["date"] >= selection_sessions[0]) & (market["date"] <= selection_sessions[-1])].copy()
    selection_frame = frame[(frame["date"] >= config["selection_start"]) & (frame["date"] <= config["selection_end"])].copy()
    rows = []
    for weight in config["agent_b_weight_grid"]:
        policy_id = f"B{int(float(weight) * 100):03d}_C{int((1.0 - float(weight)) * 100):03d}"
        _, metric = _backtest(apply_policy(selection_frame, float(weight), config), selection_market, selection_sessions, index, config, base_engine, policy_id)
        rows.append({"policy_id": policy_id, "agent_b_weight": float(weight), "agent_c_weight": 1.0 - float(weight), **metric})
    selection = pd.DataFrame(rows).sort_values(["net_excess_return", "sharpe", "turnover", "policy_id"], ascending=[False, False, True, True]).reset_index(drop=True)
    selected = selection.iloc[0]
    diagnostic_sessions = [day for day in sessions if config["diagnostic_start"] <= day <= config["diagnostic_end"]]
    diagnostic_market = market[(market["date"] >= diagnostic_sessions[0]) & (market["date"] <= diagnostic_sessions[-1])].copy()
    diagnostic_frame = frame[(frame["date"] >= config["diagnostic_start"]) & (frame["date"] <= config["diagnostic_end"])].copy()
    diagnostic_scores = apply_policy(diagnostic_frame, float(selected["agent_b_weight"]), config)
    result, diagnostic = _backtest(diagnostic_scores, diagnostic_market, diagnostic_sessions, index, config, base_engine, str(selected["policy_id"]))
    gates = {"positive_net_excess": diagnostic["net_excess_return"] > 0, "positive_excess_years_at_least_2_of_3": diagnostic["positive_annual_excess_years"] >= 2, "positive_sharpe": diagnostic["sharpe"] > 0, "mdd_above_minus_30pct": diagnostic["mdd"] > -0.30, "reconciliation": diagnostic["reconciliation"] == "PASS"}
    decision = "RETAIN_D7_FOR_FORWARD_SHADOW_ONLY" if all(gates.values()) else "REJECT_D7_FOR_TRADING"
    output_root.mkdir(parents=True, exist_ok=False)
    selection.to_csv(output_root / "selection_grid_metrics.csv", index=False, float_format="%.12g", lineterminator="\n")
    diagnostic_scores[["date", "ticker", "agent_b5_percentile", "agent_c3_score", "bottom_probability", "predicted_volatility", "decision_score", "decision_rank", "entry_eligible", "target_weight"]].to_csv(output_root / "daily_agent_d7_scores.csv.gz", index=False, compression={"method": "gzip", "mtime": 0}, float_format="%.12g", lineterminator="\n")
    selected_hashes = write_result(result, output_root / "selected_run")
    _json(output_root / "selected_policy.json", {"policy_id": selected["policy_id"], "agent_b_weight": float(selected["agent_b_weight"]), "agent_c_weight": float(selected["agent_c_weight"]), "entry_probability_low": config["entry_probability_low"], "entry_probability_high": config["entry_probability_high"]})
    _json(output_root / "diagnostic.json", {"decision": decision, "gates": gates, "metrics": diagnostic, "evidence_status": config["evidence_status"]})
    audit = {"agent_b5_experiment": b_manifest["experiment_id"], "agent_c6_experiment": c_manifest["experiment_id"], "combined_rows": len(frame), "selection_rows": len(selection_frame), "diagnostic_rows": len(diagnostic_frame), "membership_rows_loaded": len(membership), "market_files_loaded": len(market_paths), "v2_2021_2023_consumed_development_loaded": True, "final_oos_accessed": False}
    _json(output_root / "data_audit.json", audit)
    manifest = {"schema_version": "kospi200-agent-d7-serial-b5-c6-v1", "experiment_id": config["experiment_id"], "status": decision, "selected_policy": str(selected["policy_id"]), "input_sha256": {"config": sha256(config_path), "agent_b5_scores": sha256(paths["agent_b5_scores"]), "agent_b5_manifest": sha256(paths["agent_b5_manifest"]), "agent_c6_scores": sha256(paths["agent_c6_scores"]), "agent_c6_manifest": sha256(paths["agent_c6_manifest"]), "official_index": sha256(paths["index_file"]), "membership_tree": tree_hash(membership_paths, paths["membership_root"]), "market_tree": tree_hash(market_paths, paths["market_root"])}, "selected_run_hashes": selected_hashes, "final_oos_accessed": False}
    for name in ("selection_grid_metrics.csv", "daily_agent_d7_scores.csv.gz", "selected_policy.json", "diagnostic.json", "data_audit.json"):
        manifest.setdefault("output_sha256", {})[name] = sha256(output_root / name)
    _json(output_root / "manifest.json", manifest)
    return manifest
