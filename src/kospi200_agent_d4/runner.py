"""C4의 비용 차감 예상 초과수익을 5세션 간격 저회전 주문으로 변환한다."""

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


METHODS = ("C4_SPARSE", "C4_B2_RISK_CALIBRATION_SPARSE")


def combine_scores(agent_b2: pd.DataFrame, agent_c4: pd.DataFrame, method: str) -> pd.DataFrame:
    if method not in METHODS:
        raise ValueError(method)
    required = {"date", "ticker", "agent_c4_score", "predicted_net_excess_10", "positive_excess_probability"}
    if not required.issubset(agent_c4.columns):
        raise ValueError("Agent C4 점수 계약 열이 누락됐습니다.")
    c = agent_c4[list(required)].copy()
    c["c4_percentile"] = c.groupby("date")["agent_c4_score"].rank(pct=True, method="average")
    b = agent_b2[["date", "ticker", "agent_b2_percentile"]].copy()
    output = c.merge(b, on=["date", "ticker"], how="left", validate="one_to_one")
    output["agent_b2_percentile"] = output["agent_b2_percentile"].fillna(0.0)
    if method == "C4_B2_RISK_CALIBRATION_SPARSE":
        output["decision_score"] = output["c4_percentile"] * (0.5 + 0.5 * output["agent_b2_percentile"])
    else:
        output["decision_score"] = output["c4_percentile"]
    output["decision_rank"] = output.groupby("date")["decision_score"].rank(method="first", ascending=False)
    return output.sort_values(["date", "decision_rank", "ticker"]).reset_index(drop=True)


def create_orders(scored: pd.DataFrame, market: pd.DataFrame, sessions: list[str], config: dict, method: str):
    market_index = market.set_index(["date", "ticker"])
    session_index = {day: i for i, day in enumerate(sessions)}
    orders, vetoes, signal_days = [], 0, 0
    for signal_day, group in scored.groupby("date", sort=True):
        i = session_index.get(str(signal_day))
        if i is None or i + 1 >= len(sessions) or i % int(config["rebalance_interval_sessions"]) != 0:
            continue
        signal_days += 1
        execute_day = sessions[i + 1]
        eligible = group[
            (group["predicted_net_excess_10"] > float(config["minimum_predicted_net_excess"]))
            & (group["decision_rank"] <= int(config["daily_candidate_limit"]))
        ].sort_values(["decision_rank", "ticker"])
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
            orders.append(Order(
                order_id=f"D4:{method}:{signal_day}:{row.ticker}", signal_date=date.fromisoformat(str(signal_day)),
                execute_date=date.fromisoformat(execute_day), security_id=row.ticker, side=Side.BUY,
                target_weight=Decimal(str(config["target_weight"])), priority=priority,
                max_holding_sessions=int(config["maximum_holding_sessions"]), reason=f"AGENT_D4_{method}",
            ))
    return tuple(orders), vetoes, signal_days


def trade_statistics(result) -> dict[str, float | int]:
    trades = list(result.closed_trades)
    wins = [float(item.net_pnl) for item in trades if item.net_pnl > 0]
    losses = [float(item.net_pnl) for item in trades if item.net_pnl < 0]
    gross_profit, gross_loss = sum(wins), -sum(losses)
    return {
        "trade_count": len(trades), "trade_win_rate": len(wins) / len(trades) if trades else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else np.nan,
        "expectancy_krw": sum(float(item.net_pnl) for item in trades) / len(trades) if trades else 0.0,
    }


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def run(config_path: Path, output_root: Path) -> dict[str, object]:
    guard_path(config_path); guard_path(output_root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if tuple(config["methods"]) != METHODS or config.get("final_oos_access") is not False:
        raise ValueError("Agent D4 후보·접근 계약 불일치")
    if float(config["minimum_predicted_net_excess"]) != 0.0:
        raise ValueError("D4 no-trade 경계는 경제적 손익분기 0으로 고정합니다.")
    paths = {key: Path(config[key]) for key in (
        "agent_b2_scores", "agent_b2_manifest", "agent_c4_scores", "agent_c4_manifest",
        "membership_root", "market_root", "index_file", "engine_config", "cost_schedule",
    )}
    for path in paths.values(): guard_path(path)
    agent_b, b_manifest = _read_upstream(paths["agent_b2_scores"], paths["agent_b2_manifest"], "daily_agent_b2_scores.csv.gz")
    agent_c, c_manifest = _read_upstream(paths["agent_c4_scores"], paths["agent_c4_manifest"], "daily_agent_c4_scores.csv.gz")
    for frame in (agent_b, agent_c):
        frame["ticker"] = frame["ticker"].astype(str).str.zfill(6)
    agent_b = agent_b[(agent_b["date"] >= config["data_start"]) & (agent_b["date"] <= config["data_end"])].copy()
    agent_c = agent_c[(agent_c["date"] >= config["data_start"]) & (agent_c["date"] <= config["data_end"])].copy()
    membership, membership_paths = load_membership(paths["membership_root"], config["data_start"], config["data_end"])
    market, all_sessions, market_paths = load_market(paths["market_root"], set(membership["ticker"]), 2019, 2023)
    sessions = [day for day in all_sessions if config["data_start"] <= day <= config["data_end"]]
    index = load_official_index(paths["index_file"])
    benchmark = _official_benchmark(index, sessions)
    bars = bars_from_market(market, config["data_start"], config["data_end"])
    actions = tuple(a for a in mechanical_actions(market) if config["data_start"] <= a.effective_date.isoformat() <= config["data_end"])
    base = engine_from_files(paths["engine_config"], paths["cost_schedule"])
    engine = BacktestEngine(EngineConfig(initial_cash=Decimal(config["initial_cash_krw"]), max_positions=int(config["maximum_positions"])), base.cost_model)
    rows, results, audits = [], {}, {}
    for method in METHODS:
        scored = combine_scores(agent_b, agent_c, method)
        orders, vetoes, signal_days = create_orders(scored, market, sessions, config, method)
        result = engine.run(tuple(date.fromisoformat(day) for day in sessions), bars, orders, corporate_actions=actions, benchmark_close=benchmark)
        metric = result.metrics
        total_return, benchmark_return = float(metric["total_return"]), float(metric["benchmark_total_return"])
        excess, positive_years = annual_excess(result)
        stats = trade_statistics(result)
        rows.append({
            "candidate": method, "total_return": total_return, "benchmark_return": benchmark_return,
            "net_excess_return": total_return - benchmark_return,
            "sharpe": float(metric["sharpe_zero_rf"]) if metric["sharpe_zero_rf"] is not None else np.nan,
            "mdd": float(metric["max_drawdown"]), "positive_annual_excess_years": positive_years,
            "annual_excess_json": json.dumps(excess, sort_keys=True, separators=(",", ":")),
            "turnover": float(metric["turnover_on_average_equity"]), "average_cash_weight": float(metric["average_cash_weight"]),
            "orders_created": len(orders), "gap_vetoes": vetoes, "reconciliation": metric["reconciliation"], **stats,
        })
        results[method] = result; audits[method] = {"orders_created": len(orders), "gap_vetoes": vetoes, "signal_days": signal_days}
    metrics = pd.DataFrame(rows).sort_values(["net_excess_return", "sharpe", "candidate"], ascending=[False, False, True]).reset_index(drop=True)
    selected_name = str(metrics.iloc[0]["candidate"]); selected = metrics.iloc[0]
    gates = {
        "positive_total_net_excess": bool(selected["net_excess_return"] > 0),
        "positive_annual_excess_at_least_3_of_5": bool(selected["positive_annual_excess_years"] >= 3),
        "positive_sharpe": bool(selected["sharpe"] > 0), "mdd_above_floor": bool(selected["mdd"] > -0.30),
        "reconciliation": selected["reconciliation"] == "PASS",
    }
    decision = "ACCEPT_AGENT_D4_DIAGNOSTIC" if all(gates.values()) else "REJECT_AGENT_D4"
    output_root.mkdir(parents=True, exist_ok=False)
    metrics.to_csv(output_root / "candidate_metrics.csv", index=False, float_format="%.12g", lineterminator="\n")
    selected_hashes = write_result(results[selected_name], output_root / "selected_run")
    _json(output_root / "data_audit.json", {
        "agent_b2_experiment_id": b_manifest["experiment_id"], "agent_c4_experiment_id": c_manifest["experiment_id"],
        "agent_b2_rows_loaded": len(agent_b), "agent_c4_rows_loaded": len(agent_c), "membership_rows_loaded": len(membership),
        "market_files_loaded": len(market_paths), "index_code": "1028", "benchmark_is_official_index": True,
        "method_audit": audits, "v2_consumed_development_2022_2023_loaded": True,
        "legacy_v1_development_test_partition_accessed": False, "final_oos_accessed": False,
    })
    _json(output_root / "decision.json", {"selected_candidate": selected_name, "decision": decision, "gates": gates, "consumed_development_diagnostic_only": True})
    manifest = {
        "schema_version": "kospi200-agent-d4-sparse-temporal-alpha-v1", "experiment_id": config["experiment_id"],
        "status": decision, "selected_candidate": selected_name, "input_sha256": {
            "config": sha256(config_path), "agent_b2_scores": sha256(paths["agent_b2_scores"]),
            "agent_b2_manifest": sha256(paths["agent_b2_manifest"]), "agent_c4_scores": sha256(paths["agent_c4_scores"]),
            "agent_c4_manifest": sha256(paths["agent_c4_manifest"]), "official_index": sha256(paths["index_file"]),
            "membership_tree": tree_hash(membership_paths, paths["membership_root"]), "market_tree": tree_hash(market_paths, paths["market_root"]),
            "engine_config": sha256(paths["engine_config"]), "cost_schedule": sha256(paths["cost_schedule"]),
        }, "selected_run_hashes": selected_hashes, "final_oos_accessed": False,
    }
    for name in ("candidate_metrics.csv", "data_audit.json", "decision.json"):
        manifest.setdefault("output_sha256", {})[name] = sha256(output_root / name)
    _json(output_root / "manifest.json", manifest)
    return manifest
