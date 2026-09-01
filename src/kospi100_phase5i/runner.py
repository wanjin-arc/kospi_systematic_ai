from __future__ import annotations

import csv
import hashlib
import json
import platform
import tempfile
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn

from kospi100_backtest.costs import CostSchedule, ExecutionCostModel
from kospi100_backtest.engine import BacktestEngine, EngineConfig
from kospi100_backtest.types import OrderStatus
from kospi100_multifactor.modeling import feature_score_relationships, prepare_multifactor_frame
from kospi100_rank_persistence.modeling import evaluate_inherited_candidate
from kospi100_rank_persistence.policy import apply_causal_persistence
from kospi100_ranking.config import Period
from kospi100_ranking.data import SelectionBundle, load_selection_bundle
from kospi100_ranking.portfolio import _assert_successor_safety, build_context, run_portfolio

from .config import Phase5IConfig, load_config
from .policy import add_policy_flags, generate_orders


def _json_default(value: object) -> object:
    if isinstance(value, (date, Decimal, Path, pd.Timestamp)):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8", newline="\n")


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, lineterminator="\n", float_format="%.12g")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_hash() -> str:
    roots = [
        Path("src/kospi100_backtest"), Path("src/kospi100_baseline"), Path("src/kospi100_features"),
        Path("src/kospi100_ranking"), Path("src/kospi100_multifactor"), Path("src/kospi100_rank_persistence"),
        Path("src/kospi100_phase5i"), Path("src/kospi100_data"),
    ]
    paths = sorted(path for root in roots for path in root.glob("*.py"))
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.as_posix().encode()); digest.update(b"\0"); digest.update(path.read_bytes()); digest.update(b"\0")
    return digest.hexdigest()


def policy_hash(config: Phase5IConfig) -> str:
    payload = {"model": config.payload["model"], "policy": config.payload["policy"], "costs": config.payload["costs"], "gate": config.payload["diagnostic_gate"], "sklearn": sklearn.__version__}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _registry(config: Phase5IConfig) -> dict[str, str]:
    with Path("experiments/registry.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["experiment_id"] == config.experiment_id]
    if len(rows) != 1 or rows[0]["status"] not in {"preregistered", "adaptive_diagnostic_completed", "rejected"}:
        raise PermissionError("Phase 5I registry 사전등록 상태가 올바르지 않습니다")
    return rows[0]


def freeze_values(config: Phase5IConfig) -> dict[str, str]:
    row = _registry(config)
    bundle = load_selection_bundle(config.base)
    values = {"code_hash": source_hash(), "config_hash": config.config_hash, "data_version": bundle.data_hash, "model_hash": policy_hash(config)}
    for field, actual in values.items():
        if row.get(field) not in {"", "PENDING_PRE_RUN_FREEZE", actual}:
            raise ValueError(f"registry {field} 불일치")
    return values


def _assert_frozen(config: Phase5IConfig, data_hash: str) -> dict[str, str]:
    row = _registry(config)
    values = {"code_hash": source_hash(), "config_hash": config.config_hash, "data_version": data_hash, "model_hash": policy_hash(config)}
    for field, actual in values.items():
        if row.get(field) != actual:
            raise ValueError(f"실행 전 registry {field} 동결 필요")
    return values


def _engine(config: Phase5IConfig, multiplier: int) -> BacktestEngine:
    base = config.base
    costs = ExecutionCostModel(CostSchedule.from_csv(base.tax_schedule_path), commission_rate=base.commission_rate * multiplier, buy_slippage_rate=base.slippage_rate * multiplier, sell_slippage_rate=base.slippage_rate * multiplier)
    return BacktestEngine(EngineConfig(initial_cash=base.initial_cash, allow_pyramiding=False, max_positions=base.maximum_holdings), costs)


def _run_policy(predictions: pd.DataFrame, context, unresolved, config: Phase5IConfig, multiplier: int) -> tuple[dict[str, object], dict[str, int]]:
    orders, audit = generate_orders(predictions, context.sessions, config)
    _assert_successor_safety(orders, context.sessions, unresolved)
    result = _engine(config, multiplier).run(context.sessions, context.bars, tuple(context.controls) + orders, corporate_actions=context.actions, benchmark_close=context.benchmark)
    if not result.reconciliation.passed:
        raise AssertionError("Phase 5I 원장 조정 실패")
    unsafe = {OrderStatus.UNFILLED_NOT_TRADABLE, OrderStatus.UNFILLED_NO_BAR, OrderStatus.UNFILLED_LIQUIDITY, OrderStatus.PARTIALLY_FILLED}
    failed = [event for event in result.order_events if event.order_id.startswith(("P5:CA_EXIT:", "P5:REMOVAL_EXIT:")) and event.status in unsafe]
    if failed:
        raise RuntimeError(f"필수 강제청산 미체결: {failed[0].order_id}")
    metrics = result.metrics
    total = Decimal(str(metrics["total_return"])); benchmark = Decimal(str(metrics["benchmark_total_return"]))
    return {
        "policy": config.policy_candidate, "candidate": config.inherited_candidate, "period": context.name, "cost_multiplier": multiplier,
        "total_return": total, "benchmark_total_return": benchmark, "net_excess_return": total - benchmark,
        "sharpe_zero_rf": metrics["sharpe_zero_rf"], "max_drawdown": metrics["max_drawdown"],
        "turnover_on_average_equity": metrics["turnover_on_average_equity"], "average_cash_weight": metrics["average_cash_weight"],
        "fills": metrics["fills"], "all_explicit_costs": metrics["all_explicit_costs"], "reconciliation": metrics["reconciliation"], "engine_input_hash": result.input_hash,
    }, audit


def _evaluate(raw: pd.DataFrame, policy: pd.DataFrame, bundle: SelectionBundle, config: Phase5IConfig) -> tuple[pd.DataFrame, dict[str, object], dict[str, object]]:
    connected = Period("internal_validation_2011_2018", date(2011, 1, 1), date(2018, 12, 31))
    context, unresolved = build_context(bundle, connected)
    rows: list[dict[str, object]] = []
    reference = run_portfolio(config.inherited_candidate, raw, context, unresolved, config.base, 1); reference["policy"] = "daily_top10_hold20_reference"; rows.append(reference)
    audits: dict[str, object] = {}
    for multiplier in config.base.stress_multipliers:
        row, audit = _run_policy(policy, context, unresolved, config, multiplier); rows.append(row); audits[f"connected_{multiplier}x"] = audit
    for fold in config.base.folds:
        context, unresolved = build_context(bundle, fold.validation)
        selected = policy.loc[policy["fold"].eq(fold.name)]
        row, audit = _run_policy(selected, context, unresolved, config, 1); rows.append(row); audits[fold.name] = audit
    frame = pd.DataFrame(rows)
    connected_rows = frame.loc[frame["policy"].eq(config.policy_candidate) & frame["period"].eq(connected.name)]
    base = connected_rows.loc[connected_rows["cost_multiplier"].eq(1)].iloc[0]
    stress = connected_rows.loc[connected_rows["cost_multiplier"].eq(2)].iloc[0]
    annual = frame.loc[frame["policy"].eq(config.policy_candidate) & frame["period"].str.startswith("I20") & frame["cost_multiplier"].eq(1)]
    checks = {"connected_base_net_excess_positive": float(base["net_excess_return"]) > 0, "connected_2x_net_excess_nonnegative": float(stress["net_excess_return"]) >= 0}
    decision = {
        "experiment_id": config.experiment_id, "status": "ADAPTIVE_DIAGNOSTIC_PASS" if all(checks.values()) else "ADAPTIVE_DIAGNOSTIC_FAIL",
        "checks": checks, "nonnegative_annual_excess_folds": int((annual["net_excess_return"].astype(float) >= 0).sum()), "annual_folds": len(annual),
        "result_is_confirmatory": False, "trading_candidate": False, "development_test_candidate": False, "development_test_runs": 0, "d20_superseded": False,
    }
    return frame, audits, decision


def _manifest(output: Path) -> dict[str, str]:
    hashes = {path.relative_to(output).as_posix(): _sha256(path) for path in sorted(output.rglob("*")) if path.is_file() and path.name != "manifest.json"}
    _write_json(output / "manifest.json", hashes)
    return hashes


def run_diagnostic(config_path: Path, output: Path) -> dict[str, object]:
    config = load_config(config_path)
    bundle = load_selection_bundle(config.base)
    frozen = _assert_frozen(config, bundle.data_hash)
    research = prepare_multifactor_frame(bundle, config.base)
    inherited = evaluate_inherited_candidate(research.frame, bundle.index, config)
    sessions = tuple(value.date() for value in bundle.index["date"].sort_values().drop_duplicates())
    smoothed = apply_causal_persistence(inherited.predictions, sessions, config)
    policy = add_policy_flags(smoothed, config)
    metrics, policy_audit, decision = _evaluate(inherited.predictions, policy, bundle, config)
    relationships = feature_score_relationships(research.frame, inherited.predictions, config.inherited_candidate, config.base)
    partition_audit = bundle.partition.get("audit", {})
    data_audit = dict(bundle.audit)
    data_audit.update({
        "experiment_id": config.experiment_id, "source_hash": frozen["code_hash"], "config_hash": frozen["config_hash"], "data_hash": frozen["data_version"],
        "minimum_loaded_date": min(item["loaded_min_date"] for item in bundle.audit["inputs"]), "maximum_research_date": policy["date"].max().date().isoformat(),
        "pre_2011_training_rows": int((research.frame["date"] < "2011-01-01").sum()), "partition_audit": partition_audit,
        "2019_plus_rows_loaded": 0, "development_test_rows_loaded": 0, "development_test_rows_calculated": 0, "development_test_rows_evaluated": 0,
        "development_test_rows_selected": 0, "final_oos_accessed": False, "filter_applied_after_load": False,
    })
    run = {
        "experiment_id": config.experiment_id, "status": decision["status"], "source_hash": frozen["code_hash"], "config_hash": frozen["config_hash"],
        "data_hash": frozen["data_version"], "policy_hash": frozen["model_hash"], "dependencies": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "scikit_learn": sklearn.__version__},
        "run_command": config.payload["run_command"], "adaptive_diagnostic_only": True, "development_test_accessed": False, "final_oos_accessed": False,
    }
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"기존 Phase 5I 산출물을 덮어쓰지 않습니다: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phase5i_", dir=output.parent) as temporary:
        staging = Path(temporary) / output.name; staging.mkdir()
        _write_csv(metrics, staging / "portfolio_metrics.csv")
        _write_csv(inherited.rank_metrics, staging / "fold_rank_metrics.csv")
        _write_csv(inherited.fold_audit, staging / "fold_audit.csv")
        _write_csv(relationships, staging / "feature_score_relationships.csv")
        _write_json(staging / "policy_audit.json", policy_audit)
        _write_json(staging / "engineering_decision.json", decision)
        _write_json(staging / "data_audit.json", data_audit)
        _write_json(staging / "run.json", run)
        _manifest(staging); staging.replace(output)
    return run
