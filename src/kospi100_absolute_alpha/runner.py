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

from kospi100_ranking.data import load_selection_bundle

from .config import AbsoluteAlphaConfig, MODEL_CONTRACT, load_config
from .modeling import NET_TARGET, POSITIVE_TARGET, evaluate_models, prepare_absolute_frame
from .policy import apply_no_trade_policy
from .portfolio import evaluate_policy


def _json_default(value: object) -> object:
    if isinstance(value, (date, Decimal, Path, pd.Timestamp)):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def _write_json(path: Path, value: object) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default) + "\n")


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, lineterminator="\n", float_format="%.12g")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_hash() -> str:
    roots = (
        Path("src/kospi100_backtest"),
        Path("src/kospi100_baseline"),
        Path("src/kospi100_features"),
        Path("src/kospi100_ranking"),
        Path("src/kospi100_multifactor"),
        Path("src/kospi100_absolute_alpha"),
        Path("src/kospi100_data"),
    )
    paths = sorted(path for root in roots for path in root.glob("*.py"))
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def model_contract_hash(config: AbsoluteAlphaConfig) -> str:
    payload = {
        "target": config.payload["target"],
        "feature_contract": config.payload["feature_contract"],
        "models": config.payload["models"],
        "no_trade_policy": config.payload["no_trade_policy"],
        "portfolio": config.payload["portfolio"],
        "costs": config.payload["costs"],
        "random_seed": config.base.random_seed,
        "scikit_learn": sklearn.__version__,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _registry_row(experiment_id: str) -> dict[str, str]:
    with Path("experiments/registry.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["experiment_id"] == experiment_id]
    if len(rows) != 1:
        raise ValueError("Phase 5E Experiment ID는 registry에 정확히 한 번 사전등록되어야 합니다")
    if rows[0]["status"] not in {"preregistered", "adaptive_diagnostic_completed"}:
        raise PermissionError("registry 상태가 Phase 5E 실행을 허용하지 않습니다")
    return rows[0]


def freeze_values(config: AbsoluteAlphaConfig) -> dict[str, str]:
    registry = _registry_row(config.experiment_id)
    bundle = load_selection_bundle(config.base)
    values = {
        "code_hash": source_hash(),
        "config_hash": config.config_hash,
        "data_version": bundle.data_hash,
        "model_hash": model_contract_hash(config),
    }
    for field, actual in values.items():
        if registry.get(field, "") not in {"", "PENDING_PRE_RUN_FREEZE", actual}:
            raise ValueError(f"registry {field}가 실제 동결값과 다릅니다")
    return values


def _assert_frozen(config: AbsoluteAlphaConfig, data_hash: str) -> dict[str, str]:
    registry = _registry_row(config.experiment_id)
    values = {
        "code_hash": source_hash(),
        "config_hash": config.config_hash,
        "data_version": data_hash,
        "model_hash": model_contract_hash(config),
    }
    for field, actual in values.items():
        if registry.get(field) != actual:
            raise ValueError(f"실행 전 registry {field}가 동결되지 않았거나 실제 값과 다릅니다")
    return values


def _manifest(output: Path) -> dict[str, str]:
    hashes = {
        path.relative_to(output).as_posix(): _sha256(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    _write_json(output / "manifest.json", hashes)
    return hashes


def _date_rows(frame: pd.DataFrame, column: str, start: str, end: str) -> int:
    dates = pd.to_datetime(frame[column], errors="coerce")
    return int(dates.between(start, end).sum())


def run_diagnostic(config_path: Path, output: Path) -> dict[str, object]:
    config = load_config(config_path)
    bundle = load_selection_bundle(config.base)
    frozen = _assert_frozen(config, bundle.data_hash)
    research = prepare_absolute_frame(bundle, config)
    model = evaluate_models(research.frame, bundle.index, config)
    policy = apply_no_trade_policy(model.predictions, config)
    evaluation = evaluate_policy(policy, bundle, config)
    maximum_research_date = policy["date"].max().date().isoformat()
    if maximum_research_date > "2021-12-31":
        raise PermissionError("Phase 5E 연구 계산이 허용 날짜를 넘었습니다")

    reused_loaded = {
        "feature_price_panel_rows": _date_rows(bundle.feature_panel, "date", "2019-01-01", "2021-12-31"),
        "full_history_rows": _date_rows(bundle.full_history, "date", "2019-01-01", "2021-12-31"),
        "index_rows": _date_rows(bundle.index, "date", "2019-01-01", "2021-12-31"),
        "corporate_action_rows": _date_rows(bundle.corporate_actions, "feature_boundary_date", "2019-01-01", "2021-12-31"),
        "removal_order_rows": _date_rows(bundle.removal_orders, "execution_date", "2019-01-01", "2021-12-31"),
    }
    data_audit = dict(bundle.audit)
    data_audit.update({
        "experiment_id": config.experiment_id,
        "source_hash": frozen["code_hash"],
        "config_hash": frozen["config_hash"],
        "data_hash": frozen["data_version"],
        "model_contract_hash": frozen["model_hash"],
        "maximum_research_date": maximum_research_date,
        "adaptive_diagnostic_status": "ALREADY_CONSUMED_NOT_TEST_OR_OOS",
        "adaptive_2019_2021_rows_loaded": reused_loaded,
        "adaptive_2019_2021_rows_calculated": len(model.predictions),
        "adaptive_2019_2021_rows_evaluated": len(policy),
        "adaptive_2019_2021_rows_selected_for_promotion": 0,
        "development_test_input_loaded": False,
        "development_test_rows_loaded": 0,
        "development_test_rows_calculated": 0,
        "development_test_rows_evaluated": 0,
        "development_test_rows_selected": 0,
        "final_oos_accessed": False,
        "filter_applied_after_load": False,
        "research_audit": research.audit,
    })
    signal_activity = (
        policy.groupby(["fold", "date"], sort=True)
        .agg(
            cross_section=("security_id", "size"),
            passes_return_gate=("passes_return_gate", "sum"),
            passes_probability_gate=("passes_probability_gate", "sum"),
            eligible_entries=("entry_eligible", "sum"),
            mean_predicted_net_excess=("predicted_net_excess", "mean"),
            mean_positive_probability=("positive_probability", "mean"),
        )
        .reset_index()
    )
    connected_audit = evaluation.order_audit["connected_cost_1x"]
    no_trade_audit = {
        "entry_minimum_predicted_net_excess": config.entry_net_excess,
        "entry_minimum_positive_probability": config.entry_probability,
        "exit_at_or_below_predicted_net_excess": config.exit_net_excess,
        "exit_below_positive_probability": config.exit_probability,
        "maximum_entry_candidates_per_day": config.maximum_entry_candidates,
        "minimum_required_holdings": 0,
        "average_cash_is_hard_gate": False,
        "market_regime_hard_capacity_used": False,
        "connected_order_audit": connected_audit,
        "adaptive_diagnostic_not_oos": True,
        "development_test_accessed": False,
        "final_oos_accessed": False,
    }
    target_contract = {
        "signal_time": "official_close_t",
        "entry_time": "open_t_plus_1",
        "exit_time": "open_t_plus_11",
        "regression_target": NET_TARGET,
        "classification_target": POSITIVE_TARGET,
        "positive_definition": "cost_adjusted_excess_log_return_strictly_greater_than_zero",
        "cross_sectional_target_rank_used": False,
        "costs": config.payload["costs"],
        "minute_data_used": False,
        "development_test_accessed": False,
    }
    run = {
        "experiment_id": config.experiment_id,
        "status": evaluation.decision["status"],
        "source_hash": frozen["code_hash"],
        "config_hash": frozen["config_hash"],
        "data_hash": frozen["data_version"],
        "model_contract_hash": frozen["model_hash"],
        "model_contract": MODEL_CONTRACT,
        "dependencies": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "run_command": config.payload["run_command"],
        "adaptive_diagnostic_not_oos": True,
        "promotion_allowed": False,
        "development_test_accessed": False,
        "final_oos_accessed": False,
    }
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"기존 Phase 5E 산출물을 덮어쓰지 않습니다: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phase5e_diagnostic_", dir=output.parent) as temporary:
        staging = Path(temporary) / output.name
        staging.mkdir()
        _write_csv(model.metrics, staging / "model_metrics.csv")
        _write_csv(model.fold_audit, staging / "fold_audit.csv")
        _write_csv(evaluation.metrics, staging / "portfolio_metrics.csv")
        _write_csv(signal_activity, staging / "signal_activity.csv")
        _write_json(staging / "no_trade_audit.json", no_trade_audit)
        _write_json(staging / "diagnostic_decision.json", evaluation.decision)
        _write_json(staging / "target_contract.json", target_contract)
        _write_json(staging / "data_audit.json", data_audit)
        _write_json(staging / "run.json", run)
        _manifest(staging)
        staging.replace(output)
    return run


def confirm_development_test(*_: object, **__: object) -> None:
    raise PermissionError("Phase 5E Development Test는 별도 승인과 새 동결 전까지 실행할 수 없습니다")
