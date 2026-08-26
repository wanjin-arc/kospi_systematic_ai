"""B2 선필터와 B2 위험보정을 동일한 C2 매매계약으로 비교한다."""

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
from kospi200_agent_d.runner import (
    annual_excess,
    bars_from_market,
    load_market,
    mechanical_actions,
)


METHODS = ("C2_ONLY_CONTROL", "B2_TOP80_SERIAL", "B2_RISK_CALIBRATION")


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _read_upstream(score_path: Path, manifest_path: Path, output_name: str) -> tuple[pd.DataFrame, dict]:
    guard_path(score_path)
    guard_path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest.get("output_sha256", {}).get(output_name)
    if not expected or sha256(score_path) != expected:
        raise ValueError(f"상류 산출물 hash 불일치: {output_name}")
    frame = pd.read_csv(score_path, dtype={"ticker": str})
    frame["ticker"] = frame["ticker"].str.zfill(6)
    return frame, manifest


def combine_method_scores(agent_b: pd.DataFrame, agent_c: pd.DataFrame, method: str) -> pd.DataFrame:
    """C2 단독, B2 Top80 직렬, B2 비제거 위험보정을 결정적으로 만든다."""
    if method not in METHODS:
        raise ValueError(f"등록되지 않은 Agent D2 방법: {method}")
    required_c = {"date", "ticker", "agent_c2_score"}
    required_b = {"date", "ticker", "agent_b2_percentile", "broad_quality_eligible"}
    if not required_c.issubset(agent_c.columns) or not required_b.issubset(agent_b.columns):
        raise ValueError("Agent B2/C2 점수 계약 열이 누락됐습니다.")

    c = agent_c[["date", "ticker", "agent_c2_score"]].copy()
    c["c2_percentile"] = c.groupby("date")["agent_c2_score"].rank(pct=True, method="average")
    b = agent_b[["date", "ticker", "agent_b2_percentile", "broad_quality_eligible"]].copy()
    output = c.merge(b, on=["date", "ticker"], how="left", validate="one_to_one")
    output["agent_b2_percentile"] = output["agent_b2_percentile"].fillna(0.0)
    output["broad_quality_eligible"] = output["broad_quality_eligible"].eq(True)

    if method == "B2_TOP80_SERIAL":
        output = output[output["broad_quality_eligible"]].copy()
        output["decision_score"] = output["c2_percentile"]
    elif method == "B2_RISK_CALIBRATION":
        output["decision_score"] = output["c2_percentile"] * (
            0.5 + 0.5 * output["agent_b2_percentile"]
        )
    else:
        output["decision_score"] = output["c2_percentile"]

    output["decision_rank"] = output.groupby("date")["decision_score"].rank(
        method="first", ascending=False
    )
    output["method"] = method
    return output.sort_values(["date", "decision_rank", "ticker"]).reset_index(drop=True)


def create_orders(
    scored: pd.DataFrame,
    market: pd.DataFrame,
    sessions: list[str],
    config: dict,
    method: str,
) -> tuple[tuple[Order, ...], int]:
    market_index = market.set_index(["date", "ticker"])
    session_index = {day: i for i, day in enumerate(sessions)}
    orders: list[Order] = []
    vetoes = 0
    for signal_day, group in scored.groupby("date", sort=True):
        i = session_index.get(str(signal_day))
        if i is None or i + 1 >= len(sessions):
            continue
        execute_day = sessions[i + 1]
        eligible = group[
            (group["agent_c2_score"] >= float(config["entry_c2_score_floor"]))
            & (group["decision_rank"] <= int(config["daily_entry_rank_limit"]))
        ].sort_values(["decision_rank", "ticker"])
        for priority, row in enumerate(eligible.itertuples(index=False)):
            signal_key, execute_key = (str(signal_day), row.ticker), (execute_day, row.ticker)
            if signal_key not in market_index.index or execute_key not in market_index.index:
                continue
            signal_bar = market_index.loc[signal_key]
            execution_bar = market_index.loc[execute_key]
            if signal_bar["close"] <= 0 or execution_bar["open"] <= 0 or execution_bar["volume"] <= 0:
                continue
            gap = execution_bar["open"] / signal_bar["close"] - 1.0
            if abs(gap) > float(config["gap_veto_rate"]):
                vetoes += 1
                continue
            expected_fill = Decimal(str(float(execution_bar["open"]))) * Decimal("1.001")
            target_weight = (
                config["target_weight_high"]
                if int(row.decision_rank) <= int(config["high_weight_rank_limit"])
                else config["target_weight_low"]
            )
            orders.append(
                Order(
                    order_id=f"D2:{method}:{signal_day}:{row.ticker}",
                    signal_date=date.fromisoformat(str(signal_day)),
                    execute_date=date.fromisoformat(execute_day),
                    security_id=row.ticker,
                    side=Side.BUY,
                    target_weight=Decimal(str(target_weight)),
                    priority=priority,
                    stop_price=expected_fill * (Decimal("1") - Decimal(str(config["stop_loss_rate"]))),
                    target_price=expected_fill * (Decimal("1") + Decimal(str(config["take_profit_rate"]))),
                    max_holding_sessions=int(config["maximum_holding_sessions"]),
                    reason=f"AGENT_D2_{method}",
                )
            )
    return tuple(orders), vetoes


def _official_benchmark(index: pd.DataFrame, sessions: list[str]) -> dict[date, Decimal]:
    close = index.set_index("date")["close"]
    missing = [day for day in sessions if day not in close.index]
    if missing:
        raise ValueError(f"공식 KOSPI 200 지수 세션 누락: {missing[:5]}")
    return {date.fromisoformat(day): Decimal(str(float(close.loc[day]))) for day in sessions}


def run(config_path: Path, output_root: Path) -> dict[str, object]:
    guard_path(config_path)
    guard_path(output_root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if tuple(config["methods"]) != METHODS:
        raise ValueError("Agent D2 후보 집합 또는 순서를 바꿀 수 없습니다.")
    if config.get("portfolio_backtest") is not True or config.get("final_oos_access") is not False:
        raise ValueError("Agent D2 실행 경계가 올바르지 않습니다.")
    if config.get("same_bar_policy") != "STOP_FIRST":
        raise ValueError("Agent D2는 STOP_FIRST만 허용합니다.")

    paths = {
        key: Path(config[key])
        for key in (
            "agent_b2_scores", "agent_b2_manifest", "agent_c2_scores", "agent_c2_manifest",
            "membership_root", "market_root", "index_file", "engine_config", "cost_schedule",
        )
    }
    for path in paths.values():
        guard_path(path)
    agent_b, b_manifest = _read_upstream(
        paths["agent_b2_scores"], paths["agent_b2_manifest"], "daily_agent_b2_scores.csv.gz"
    )
    agent_c, c_manifest = _read_upstream(
        paths["agent_c2_scores"], paths["agent_c2_manifest"], "daily_agent_c2_scores.csv.gz"
    )
    agent_c = agent_c[
        (agent_c["date"] >= config["data_start"]) & (agent_c["date"] <= config["data_end"])
    ].copy()
    agent_b = agent_b[
        (agent_b["date"] >= config["data_start"]) & (agent_b["date"] <= config["data_end"])
    ].copy()

    membership, membership_paths = load_membership(
        paths["membership_root"], config["data_start"], config["data_end"]
    )
    tickers = set(membership["ticker"])
    market, all_sessions, market_paths = load_market(
        paths["market_root"], tickers, int(config["data_start"][:4]), int(config["data_end"][:4])
    )
    sessions = [day for day in all_sessions if config["data_start"] <= day <= config["data_end"]]
    index = load_official_index(paths["index_file"])
    benchmark = _official_benchmark(index, sessions)
    bars = bars_from_market(market, config["data_start"], config["data_end"])
    actions = tuple(
        action for action in mechanical_actions(market)
        if config["data_start"] <= action.effective_date.isoformat() <= config["data_end"]
    )
    base = engine_from_files(paths["engine_config"], paths["cost_schedule"])
    engine = BacktestEngine(
        EngineConfig(
            initial_cash=Decimal(config["initial_cash_krw"]),
            max_positions=int(config["maximum_positions"]),
        ),
        base.cost_model,
    )

    rows: list[dict[str, object]] = []
    results = {}
    method_audits = {}
    for method in METHODS:
        scored = combine_method_scores(agent_b, agent_c, method)
        orders, vetoes = create_orders(scored, market, sessions, config, method)
        result = engine.run(
            tuple(date.fromisoformat(day) for day in sessions), bars, orders,
            corporate_actions=actions, benchmark_close=benchmark,
        )
        metric = result.metrics
        total_return = float(metric["total_return"])
        benchmark_return = float(metric["benchmark_total_return"])
        net_excess = total_return - benchmark_return
        excess, positive_years = annual_excess(result)
        rows.append({
            "candidate": method,
            "total_return": total_return,
            "benchmark_return": benchmark_return,
            "net_excess_return": net_excess,
            "sharpe": float(metric["sharpe_zero_rf"]) if metric["sharpe_zero_rf"] is not None else np.nan,
            "mdd": float(metric["max_drawdown"]),
            "positive_annual_excess_years": positive_years,
            "annual_excess_json": json.dumps(excess, sort_keys=True, separators=(",", ":")),
            "closed_trades": int(metric["closed_trades"]),
            "turnover": float(metric["turnover_on_average_equity"]),
            "average_cash_weight": float(metric["average_cash_weight"]),
            "orders_created": len(orders),
            "gap_vetoes": vetoes,
            "reconciliation": metric["reconciliation"],
        })
        results[method] = result
        method_audits[method] = {
            "scored_rows": len(scored),
            "unique_scored_tickers": int(scored["ticker"].nunique()),
            "orders_created": len(orders),
            "gap_vetoes": vetoes,
        }

    metrics = pd.DataFrame(rows).sort_values(
        ["net_excess_return", "sharpe", "candidate"], ascending=[False, False, True]
    ).reset_index(drop=True)
    selected_name = str(metrics.iloc[0]["candidate"])
    selected = metrics.iloc[0]
    gates = {
        "positive_total_net_excess": bool(selected["net_excess_return"] > 0),
        "positive_annual_excess_at_least_3_of_5": bool(
            selected["positive_annual_excess_years"] >= int(config["minimum_positive_annual_excess_years"])
        ),
        "positive_sharpe": bool(selected["sharpe"] > 0),
        "mdd_above_floor": bool(selected["mdd"] > float(config["maximum_drawdown_floor"])),
        "reconciliation": selected["reconciliation"] == "PASS",
    }
    decision = "ACCEPT_AGENT_D2_DIAGNOSTIC" if all(gates.values()) else "REJECT_AGENT_D2"

    output_root.mkdir(parents=True, exist_ok=False)
    metrics.to_csv(
        output_root / "candidate_metrics.csv", index=False, float_format="%.12g", lineterminator="\n"
    )
    selected_hashes = write_result(results[selected_name], output_root / "selected_run")
    matched = agent_c.merge(
        agent_b[["date", "ticker", "agent_b2_percentile", "broad_quality_eligible"]],
        on=["date", "ticker"], how="left",
    )
    audit = {
        "agent_b2_experiment_id": b_manifest["experiment_id"],
        "agent_b2_rows_loaded": len(agent_b),
        "agent_c2_experiment_id": c_manifest["experiment_id"],
        "agent_c2_rows_loaded": len(agent_c),
        "agent_c2_rows_without_agent_b2": int(matched["agent_b2_percentile"].isna().sum()),
        "agent_b2_top80_rows_available": int(matched["broad_quality_eligible"].fillna(False).sum()),
        "membership_rows_loaded": len(membership),
        "market_files_loaded": len(market_paths),
        "index_rows_loaded": len(index),
        "index_code": "1028",
        "benchmark": "OFFICIAL_KRX_KOSPI200_CLOSE",
        "benchmark_is_official_index": True,
        "mechanical_actions": len(actions),
        "method_audit": method_audits,
        "v2_consumed_development_2022_2023_loaded": True,
        "legacy_v1_development_test_partition_accessed": False,
        "final_oos_accessed": False,
    }
    _write_json(output_root / "data_audit.json", audit)
    _write_json(output_root / "decision.json", {
        "selected_candidate": selected_name,
        "selection_order": ["net_excess_return", "sharpe", "candidate"],
        "decision": decision,
        "gates": gates,
        "consumed_development_diagnostic_only": True,
    })
    manifest = {
        "schema_version": "kospi200-agent-d2-phase4b-v1",
        "experiment_id": config["experiment_id"],
        "status": decision,
        "selected_candidate": selected_name,
        "input_sha256": {
            "config": sha256(config_path),
            "agent_b2_scores": sha256(paths["agent_b2_scores"]),
            "agent_b2_manifest": sha256(paths["agent_b2_manifest"]),
            "agent_c2_scores": sha256(paths["agent_c2_scores"]),
            "agent_c2_manifest": sha256(paths["agent_c2_manifest"]),
            "official_index": sha256(paths["index_file"]),
            "membership_tree": tree_hash(membership_paths, paths["membership_root"]),
            "market_tree": tree_hash(market_paths, paths["market_root"]),
            "engine_config": sha256(paths["engine_config"]),
            "cost_schedule": sha256(paths["cost_schedule"]),
        },
        "final_oos_accessed": False,
        "legacy_v1_development_test_partition_accessed": False,
        "selected_run_hashes": selected_hashes,
    }
    for name in ("candidate_metrics.csv", "data_audit.json", "decision.json"):
        manifest.setdefault("output_sha256", {})[name] = sha256(output_root / name)
    _write_json(output_root / "manifest.json", manifest)
    return manifest
