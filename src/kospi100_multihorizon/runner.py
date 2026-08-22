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

from .config import MODEL_CONTRACT, MultiHorizonConfig, load_config
from .modeling import evaluate_model, prepare_frame
from .policy import apply_consensus_policy
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
        Path("src/kospi100_backtest"), Path("src/kospi100_baseline"),
        Path("src/kospi100_features"), Path("src/kospi100_ranking"),
        Path("src/kospi100_multifactor"), Path("src/kospi100_multihorizon"),
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


def model_contract_hash(config: MultiHorizonConfig) -> str:
    payload = {
        "target": config.payload["target"], "feature_contract": config.payload["feature_contract"],
        "model": config.payload["model"], "consensus_policy": config.payload["consensus_policy"],
        "portfolio": config.payload["portfolio"], "costs": config.payload["costs"],
        "random_seed": config.base.random_seed, "scikit_learn": sklearn.__version__,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _registry_row(experiment_id: str) -> dict[str, str]:
    with Path("experiments/registry.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["experiment_id"] == experiment_id]
    if len(rows) != 1:
        raise ValueError("Phase 5G Experiment ID가 registry에 정확히 한 번 사전등록되어야 합니다")
    if rows[0]["status"] not in {"preregistered", "internal_diagnostic_completed"}:
        raise PermissionError("registry 상태가 Phase 5G 실행을 허용하지 않습니다")
    return rows[0]


def freeze_values(config: MultiHorizonConfig) -> dict[str, str]:
    registry = _registry_row(config.experiment_id)
    bundle = load_selection_bundle(config.base)
    values = {
        "code_hash": source_hash(), "config_hash": config.config_hash,
        "data_version": bundle.data_hash, "model_hash": model_contract_hash(config),
    }
    for field, actual in values.items():
        if registry.get(field, "") not in {"", "PENDING_PRE_RUN_FREEZE", actual}:
            raise ValueError(f"registry {field}가 실제 동결값과 다릅니다")
    return values


def _assert_frozen(config: MultiHorizonConfig, data_hash: str) -> dict[str, str]:
    registry = _registry_row(config.experiment_id)
    values = {
        "code_hash": source_hash(), "config_hash": config.config_hash,
        "data_version": data_hash, "model_hash": model_contract_hash(config),
    }
    for field, actual in values.items():
        if registry.get(field) != actual:
            raise ValueError(f"실행 전 registry {field}가 동결되지 않았거나 실제 값과 다릅니다")
    return values


def _manifest(output: Path) -> dict[str, str]:
    hashes = {
        path.relative_to(output).as_posix(): _sha256(path)
        for path in sorted(output.rglob("*")) if path.is_file() and path.name != "manifest.json"
    }
    _write_json(output / "manifest.json", hashes)
    return hashes


def run_diagnostic(config_path: Path, output: Path) -> dict[str, object]:
    config = load_config(config_path)
    bundle = load_selection_bundle(config.base)
    frozen = _assert_frozen(config, bundle.data_hash)
    research = prepare_frame(bundle, config)
    model = evaluate_model(research, bundle.index, config)
    policy = apply_consensus_policy(model.predictions, config)
    evaluation = evaluate_policy(policy, bundle, config)
    if policy["date"].max().date() > date(2018, 12, 31):
        raise PermissionError("Phase 5G 계산이 2018년을 초과했습니다")
    data_audit = dict(bundle.audit)
    data_audit.update({
        "experiment_id": config.experiment_id, "source_hash": frozen["code_hash"],
        "config_hash": frozen["config_hash"], "data_hash": frozen["data_version"],
        "model_contract_hash": frozen["model_hash"],
        "maximum_research_date": policy["date"].max().date().isoformat(),
        "post_2018_input_rows_loaded": 0, "post_2018_rows_calculated": 0,
        "post_2018_rows_evaluated": 0, "post_2018_rows_selected": 0,
        "development_test_input_loaded": False, "development_test_rows_loaded": 0,
        "development_test_rows_calculated": 0, "development_test_rows_evaluated": 0,
        "development_test_rows_selected": 0, "final_oos_accessed": False,
        "filter_applied_after_load": False, "research_audit": research.audit,
    })
    signal_activity = (
        policy.groupby(["fold", "date"], sort=True)
        .agg(
            cross_section=("security_id", "size"),
            direction_gate=("passes_direction_gate", "sum"),
            magnitude_gate=("passes_magnitude_gate", "sum"),
            eligible_entries=("entry_eligible", "sum"),
            mean_positive_horizons=("positive_horizons", "mean"),
            mean_predicted_median_net_excess=("predicted_median_net_excess", "mean"),
        ).reset_index()
    )
    target_contract = {
        "signal_time": "official_close_t", "entry_time": "open_t_plus_1",
        "exit_times": {str(value): f"open_t_plus_{value + 1}" for value in config.horizons},
        "targets": [f"forward_cost_adjusted_excess_log_return_{value}" for value in config.horizons],
        "costs": config.payload["costs"], "cross_sectional_target_rank_used": False,
        "minute_data_used": False, "development_test_accessed": False,
    }
    score_contract = {
        "model": MODEL_CONTRACT, "daily_scoring": True,
        "positive_horizon_requirement": config.minimum_positive_horizons,
        "entry_median_net_excess": config.entry_median_net_excess,
        "ranking": "predicted_median_net_excess_desc_security_id_asc",
        "maximum_holdings": config.base.maximum_holdings, "minimum_holdings": 0,
        "maximum_holding_sessions": config.maximum_holding_sessions,
        "order_time": "next_session_open_or_later", "promotion_allowed": False,
    }
    run = {
        "experiment_id": config.experiment_id, "status": evaluation.decision["status"],
        "source_hash": frozen["code_hash"], "config_hash": frozen["config_hash"],
        "data_hash": frozen["data_version"], "model_contract_hash": frozen["model_hash"],
        "model_contract": MODEL_CONTRACT,
        "dependencies": {"python": platform.python_version(), "numpy": np.__version__,
                         "pandas": pd.__version__, "scikit_learn": sklearn.__version__},
        "run_command": config.payload["run_command"], "internal_train_diagnostic_only": True,
        "promotion_allowed": False, "development_test_accessed": False,
        "final_oos_accessed": False,
    }
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"기존 Phase 5G 산출물을 덮어쓰지 않습니다: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phase5g_diagnostic_", dir=output.parent) as temporary:
        staging = Path(temporary) / output.name
        staging.mkdir()
        _write_csv(model.metrics, staging / "model_metrics.csv")
        _write_csv(model.fold_audit, staging / "fold_audit.csv")
        _write_csv(evaluation.metrics, staging / "portfolio_metrics.csv")
        _write_csv(signal_activity, staging / "signal_activity.csv")
        _write_json(staging / "internal_decision.json", evaluation.decision)
        _write_json(staging / "target_contract.json", target_contract)
        _write_json(staging / "score_contract.json", score_contract)
        _write_json(staging / "order_audit.json", evaluation.order_audit)
        _write_json(staging / "data_audit.json", data_audit)
        _write_json(staging / "run.json", run)
        _manifest(staging)
        staging.replace(output)
    return run


def confirm_development_test(*_: object, **__: object) -> None:
    raise PermissionError("Phase 5G Development Test는 별도 승인과 새 증거 경계 전에는 실행할 수 없습니다")
