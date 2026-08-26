"""독립 Agent B·C 점수를 고정 규칙으로 결합하고 결정론적으로 실행한다."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from kospi100_backtest.config import engine_from_files
from kospi100_backtest.engine import BacktestEngine, EngineConfig
from kospi100_backtest.io import write_result
from kospi100_backtest.types import Bar, CorporateAction, CorporateActionType, Order, Side
from kospi200_agent_c.runner import guard_path, sha256
from kospi200_agent_c_independent.runner import load_membership, tree_hash


def _column(frame: pd.DataFrame, names: tuple[str, ...]) -> str:
    return next(name for name in names if name in frame.columns)


def load_market(root: Path, tickers: set[str], start_year: int, end_year: int):
    guard_path(root)
    paths = sorted(path for year in range(start_year, end_year + 1) for path in (root / str(year)).glob("*.csv.gz"))
    pieces, sessions = [], []
    for path in paths:
        day = path.stem.split(".")[0]; day_text = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
        raw = pd.read_csv(path, compression="gzip", encoding="cp949", dtype=str, keep_default_na=False)
        columns = [_column(raw, ("종목코드", "ISU_SRT_CD")), _column(raw, ("시가", "TDD_OPNPRC")),
                   _column(raw, ("고가", "TDD_HGPRC")), _column(raw, ("저가", "TDD_LWPRC")),
                   _column(raw, ("종가", "TDD_CLSPRC")), _column(raw, ("거래량", "ACC_TRDVOL")),
                   _column(raw, ("시가총액", "MKTCAP")), _column(raw, ("상장주식수", "LIST_SHRS"))]
        part = raw[columns].copy(); part.columns = ["ticker", "open", "high", "low", "close", "volume", "market_cap", "listed_shares"]
        part["ticker"] = part["ticker"].str.replace(r"\D", "", regex=True).str.zfill(6); part = part[part["ticker"].isin(tickers)]
        for column in part.columns[1:]: part[column] = pd.to_numeric(part[column].str.replace(",", "", regex=False), errors="coerce")
        part["date"] = day_text; pieces.append(part); sessions.append(day_text)
    return pd.concat(pieces, ignore_index=True).drop_duplicates(["date", "ticker"]), sessions, paths


def combine_scores(agent_b: pd.DataFrame, agent_c: pd.DataFrame, b_weight: float) -> pd.DataFrame:
    c = agent_c.copy()
    c["c_percentile"] = c.groupby("date")["agent_c_score"].rank(pct=True, method="average")
    b = agent_b[["date", "ticker", "agent_b_score"]].copy()
    b["b_percentile"] = b.groupby("date")["agent_b_score"].rank(pct=True, method="average")
    output = c.merge(b[["date", "ticker", "b_percentile"]], on=["date", "ticker"], how="left")
    output["b_percentile"] = output["b_percentile"].fillna(0.0)
    output["combined_score"] = (1.0 - b_weight) * output["c_percentile"] + b_weight * output["b_percentile"]
    return output


def mechanical_actions(market: pd.DataFrame) -> tuple[CorporateAction, ...]:
    frame = market.sort_values(["ticker", "date"]).copy(); group = frame.groupby("ticker", sort=False)
    share_ratio = frame["listed_shares"] / group["listed_shares"].shift(1); price_ratio = frame["close"] / group["close"].shift(1)
    mask = (share_ratio > 0) & (price_ratio > 0) & (np.abs(np.log(share_ratio)) >= np.log(1.20))
    mask &= np.abs(np.log(share_ratio) + np.log(price_ratio)) <= np.log(1.15)
    actions = []
    for index in frame.index[mask]:
        row = frame.loc[index]; ratio = Decimal(str(float(share_ratio.loc[index]))); open_price = Decimal(str(float(row["open"])))
        actions.append(CorporateAction(action_id=f"OBSERVED-SHARE-RESET:{row['date']}:{row['ticker']}", effective_date=date.fromisoformat(row["date"]),
                                       security_id=str(row["ticker"]), kind=CorporateActionType.SPLIT, share_multiplier=ratio,
                                       cash_in_lieu_price=open_price, source_status="PIT_OBSERVED_MECHANICAL_RESET"))
    return tuple(actions)


def benchmark_proxy(market: pd.DataFrame, membership: pd.DataFrame, sessions: list[str]) -> dict[date, Decimal]:
    values = {date.fromisoformat(sessions[0]): Decimal("1000")}; level = 1000.0
    indexed = market.set_index(["date", "ticker"])
    members = {day: set(group["ticker"]) for day, group in membership.groupby("date")}
    for previous, current in zip(sessions, sessions[1:]):
        tickers = sorted(members.get(previous, set()))
        returns, weights = [], []
        for ticker in tickers:
            if (previous, ticker) not in indexed.index or (current, ticker) not in indexed.index: continue
            prior = indexed.loc[(previous, ticker)]; now = indexed.loc[(current, ticker)]
            if prior["close"] <= 0 or prior["market_cap"] <= 0 or now["close"] <= 0: continue
            share_ratio = now["listed_shares"] / prior["listed_shares"] if prior["listed_shares"] > 0 else 1.0
            price_ratio = now["close"] / prior["close"]
            adjustment = share_ratio if abs(np.log(share_ratio)) >= np.log(1.20) and abs(np.log(share_ratio) + np.log(price_ratio)) <= np.log(1.15) else 1.0
            returns.append(price_ratio * adjustment - 1.0); weights.append(float(prior["market_cap"]))
        if weights and sum(weights) > 0: level *= 1.0 + float(np.average(returns, weights=weights))
        values[date.fromisoformat(current)] = Decimal(str(level))
    return values


def bars_from_market(market: pd.DataFrame, start: str, end: str) -> tuple[Bar, ...]:
    bars = []
    for row in market[(market["date"] >= start) & (market["date"] <= end)].itertuples(index=False):
        valid = all(pd.notna(getattr(row, name)) and getattr(row, name) > 0 for name in ("open", "high", "low", "close"))
        bars.append(Bar(session=date.fromisoformat(row.date), security_id=row.ticker,
                        open=Decimal(str(row.open)) if valid else None, high=Decimal(str(row.high)) if valid else None,
                        low=Decimal(str(row.low)) if valid else None, close=Decimal(str(row.close)) if valid else None,
                        tradable=bool(valid and row.volume > 0)))
    return tuple(bars)


def create_orders(scored: pd.DataFrame, market: pd.DataFrame, sessions: list[str], config: dict) -> tuple[tuple[Order, ...], int]:
    market_index = market.set_index(["date", "ticker"]); session_index = {day: i for i, day in enumerate(sessions)}
    orders, vetoes = [], 0
    for signal_day, group in scored.groupby("date", sort=True):
        i = session_index.get(signal_day)
        if i is None or i + 1 >= len(sessions): continue
        execute_day = sessions[i + 1]
        eligible = group[group["agent_c_score"] >= float(config["entry_score_5pct"])].sort_values(["combined_score", "ticker"], ascending=[False, True]).head(int(config["maximum_positions"]))
        for priority, row in enumerate(eligible.itertuples(index=False)):
            if (signal_day, row.ticker) not in market_index.index or (execute_day, row.ticker) not in market_index.index: continue
            signal_bar, execution_bar = market_index.loc[(signal_day, row.ticker)], market_index.loc[(execute_day, row.ticker)]
            if signal_bar["close"] <= 0 or execution_bar["open"] <= 0 or execution_bar["volume"] <= 0: continue
            gap = execution_bar["open"] / signal_bar["close"] - 1.0
            if abs(gap) > float(config["gap_veto_rate"]): vetoes += 1; continue
            expected_fill = Decimal(str(float(execution_bar["open"]))) * Decimal("1.001")
            weight = Decimal(str(config["target_weight_high"] if row.agent_c_score >= float(config["entry_score_11pct"]) else config["target_weight_low"]))
            orders.append(Order(order_id=f"D:{signal_day}:{row.ticker}", signal_date=date.fromisoformat(signal_day), execute_date=date.fromisoformat(execute_day),
                                security_id=row.ticker, side=Side.BUY, target_weight=weight, priority=priority,
                                stop_price=expected_fill * (Decimal("1") - Decimal(str(config["stop_loss_rate"]))),
                                target_price=expected_fill * (Decimal("1") + Decimal(str(config["take_profit_rate"]))),
                                max_holding_sessions=int(config["maximum_holding_sessions"]), reason="AGENT_D_ENTRY"))
    return tuple(orders), vetoes


def annual_excess(result) -> tuple[dict[str, float], int]:
    equity_end, benchmark_end = {}, {}
    for point in result.equity_curve:
        equity_end[point.session.year] = float(point.equity); benchmark_end[point.session.year] = float(point.benchmark_close) if point.benchmark_close else np.nan
    prior_equity, prior_benchmark = float(result.initial_cash), float(result.equity_curve[0].benchmark_close)
    excess = {}
    for year in sorted(equity_end):
        strategy = equity_end[year] / prior_equity - 1.0; benchmark = benchmark_end[year] / prior_benchmark - 1.0
        excess[str(year)] = strategy - benchmark; prior_equity, prior_benchmark = equity_end[year], benchmark_end[year]
    return excess, sum(value > 0 for value in excess.values())


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(config_path: Path, output_root: Path) -> dict[str, object]:
    guard_path(config_path); guard_path(output_root); config = json.loads(config_path.read_text(encoding="utf-8"))
    paths = {key: Path(config[key]) for key in ("agent_b_scores", "agent_c_scores", "membership_root", "market_root", "engine_config", "cost_schedule")}
    for path in paths.values(): guard_path(path)
    agent_b = pd.read_csv(paths["agent_b_scores"], dtype={"ticker": str}); agent_c = pd.read_csv(paths["agent_c_scores"], dtype={"ticker": str})
    for frame in (agent_b, agent_c): frame["ticker"] = frame["ticker"].str.zfill(6)
    membership, membership_paths = load_membership(paths["membership_root"], config["data_start"], config["data_end"])
    tickers = set(membership["ticker"]); market, all_sessions, market_paths = load_market(paths["market_root"], tickers, int(config["data_start"][:4]), int(config["data_end"][:4]))
    sessions = [day for day in all_sessions if config["data_start"] <= day <= config["data_end"]]
    benchmark = benchmark_proxy(market, membership, sessions); bars = bars_from_market(market, config["data_start"], config["data_end"])
    actions = tuple(action for action in mechanical_actions(market) if config["data_start"] <= action.effective_date.isoformat() <= config["data_end"])
    base = engine_from_files(paths["engine_config"], paths["cost_schedule"])
    engine = BacktestEngine(EngineConfig(initial_cash=Decimal(config["initial_cash_krw"]), max_positions=int(config["maximum_positions"])), base.cost_model)
    rows, best_result, best_name, best_key, total_vetoes = [], None, None, None, 0
    for name, b_weight in config["weight_candidates"].items():
        scored = combine_scores(agent_b, agent_c, float(b_weight)); orders, vetoes = create_orders(scored, market, sessions, config); total_vetoes += vetoes
        result = engine.run(tuple(date.fromisoformat(day) for day in sessions), bars, orders, corporate_actions=actions, benchmark_close=benchmark)
        metric = result.metrics; total_return = float(metric["total_return"]); benchmark_return = float(metric["benchmark_total_return"]); net_excess = total_return - benchmark_return
        excess, positive_years = annual_excess(result)
        row = {"candidate": name, "b_weight": b_weight, "total_return": total_return, "benchmark_return": benchmark_return, "net_excess_return": net_excess,
               "sharpe": float(metric["sharpe_zero_rf"]) if metric["sharpe_zero_rf"] is not None else np.nan, "mdd": float(metric["max_drawdown"]),
               "positive_annual_excess_years": positive_years, "annual_excess_json": json.dumps(excess, sort_keys=True, separators=(",", ":")),
               "closed_trades": int(metric["closed_trades"]), "turnover": float(metric["turnover_on_average_equity"]), "average_cash_weight": float(metric["average_cash_weight"]),
               "gap_vetoes": vetoes, "reconciliation": metric["reconciliation"]}
        rows.append(row); key = (net_excess, row["sharpe"], -float(b_weight))
        if best_key is None or key > best_key: best_key, best_result, best_name = key, result, name
    metrics = pd.DataFrame(rows).sort_values(["net_excess_return", "sharpe", "b_weight"], ascending=[False, False, True])
    assert best_result is not None and best_name is not None
    selected = metrics[metrics["candidate"] == best_name].iloc[0]
    gates = {"positive_total_net_excess": bool(selected["net_excess_return"] > 0), "positive_annual_excess_at_least_3_of_5": bool(selected["positive_annual_excess_years"] >= int(config["minimum_positive_annual_excess_years"])),
             "positive_sharpe": bool(selected["sharpe"] > 0), "mdd_above_floor": bool(selected["mdd"] > float(config["maximum_drawdown_floor"])), "reconciliation": selected["reconciliation"] == "PASS"}
    decision = "ACCEPT_AGENT_D_DIAGNOSTIC" if all(gates.values()) else "REJECT_AGENT_D"
    output_root.mkdir(parents=True, exist_ok=False); metrics.to_csv(output_root / "candidate_metrics.csv", index=False, float_format="%.12g", lineterminator="\n")
    selected_hashes = write_result(best_result, output_root / "selected_run")
    audit = {"agent_b_rows_loaded": len(agent_b), "agent_c_rows_loaded": len(agent_c), "membership_rows_loaded": len(membership), "market_files_loaded": len(market_paths),
             "mechanical_actions": len(actions), "gap_vetoes_all_candidates": total_vetoes, "benchmark": config["benchmark"], "benchmark_is_official_index": False,
             "v2_consumed_development_2022_2023_loaded": True, "legacy_v1_development_test_partition_accessed": False, "final_oos_accessed": False}
    _json(output_root / "data_audit.json", audit); _json(output_root / "decision.json", {"selected_candidate": best_name, "decision": decision, "gates": gates})
    manifest = {"schema_version": "kospi200-agent-d-phase4-v1", "experiment_id": config["experiment_id"], "status": decision, "selected_candidate": best_name,
                "input_sha256": {"config": sha256(config_path), "agent_b": sha256(paths["agent_b_scores"]), "agent_c": sha256(paths["agent_c_scores"]),
                                 "membership_tree": tree_hash(membership_paths, paths["membership_root"]), "market_tree": tree_hash(market_paths, paths["market_root"])},
                "final_oos_accessed": False, "legacy_v1_development_test_partition_accessed": False, "selected_run_hashes": selected_hashes}
    for name in ("candidate_metrics.csv", "data_audit.json", "decision.json"): manifest.setdefault("output_sha256", {})[name] = sha256(output_root / name)
    _json(output_root / "manifest.json", manifest); return manifest
