from __future__ import annotations

import csv
import hashlib
import json
import platform
import shutil
import tempfile
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn

from kospi100_multifactor.modeling import _rank_metrics, prepare_multifactor_frame
from kospi100_ranking.data import load_selection_bundle

from .config import Phase5CConfig, load_config
from .modeling import evaluate_inherited_candidate
from .policy import apply_causal_persistence
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
        Path("src/kospi100_rank_persistence"),
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


def policy_hash(config: Phase5CConfig) -> str:
    payload = {
        "inherited_signal": config.payload["inherited_signal"],
        "ranking_policy": config.payload["ranking_policy"],
        "costs": config.payload["costs"],
        "adaptive_diagnostic": config.payload["adaptive_diagnostic"],
        "random_seed": config.base.random_seed,
        "scikit_learn": sklearn.__version__,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _registry_row(experiment_id: str) -> dict[str, str]:
    with Path("experiments/registry.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["experiment_id"] == experiment_id]
    if len(rows) != 1:
        raise ValueError("Phase 5C Experiment ID는 registry에 정확히 한 번 사전등록되어야 합니다")
    if rows[0]["status"] not in {"preregistered", "adaptive_diagnostic_completed"}:
        raise PermissionError("registry 상태가 Phase 5C 실행을 허용하지 않습니다")
    return rows[0]


def _phase5b_handoff(config: Phase5CConfig) -> dict[str, object]:
    path = Path("artifacts/phase5b/selection/candidate_selection.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("diagnostic_best_candidate") != config.inherited_candidate:
        raise ValueError("Phase 5B 진단상 최선 후보 인계가 일치하지 않습니다")
    if payload.get("accepted_candidate") is not None:
        raise ValueError("Phase 5B 기각 상태와 인계 산출물이 충돌합니다")
    return {
        "path": path.as_posix(),
        "sha256": _sha256(path),
        "inherited_candidate": config.inherited_candidate,
        "phase5b_candidate_was_trading_candidate": False,
    }


def freeze_values(config: Phase5CConfig) -> dict[str, str]:
    registry = _registry_row(config.experiment_id)
    _phase5b_handoff(config)
    bundle = load_selection_bundle(config.base)
    values = {
        "code_hash": source_hash(),
        "config_hash": config.config_hash,
        "data_version": bundle.data_hash,
        "model_hash": policy_hash(config),
    }
    for field, actual in values.items():
        registered = registry.get(field, "")
        if registered not in {"", "PENDING_PRE_RUN_FREEZE", actual}:
            raise ValueError(f"registry {field}가 실제 동결값과 다릅니다")
    return values


def _assert_frozen(config: Phase5CConfig, data_hash: str) -> dict[str, str]:
    registry = _registry_row(config.experiment_id)
    values = {
        "code_hash": source_hash(),
        "config_hash": config.config_hash,
        "data_version": data_hash,
        "model_hash": policy_hash(config),
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


def _persistent_rank_metrics(frame: pd.DataFrame, config: Phase5CConfig) -> pd.DataFrame:
    rows = []
    for fold in config.base.folds:
        selected = frame.loc[frame["fold"].eq(fold.name)].copy()
        rows.append(_rank_metrics(selected, config.policy_candidate, fold.name))
    return pd.DataFrame(rows)


def run_diagnostic(config_path: Path, output: Path) -> dict[str, object]:
    config = load_config(config_path)
    handoff = _phase5b_handoff(config)
    bundle = load_selection_bundle(config.base)
    frozen = _assert_frozen(config, bundle.data_hash)
    research = prepare_multifactor_frame(bundle, config.base)
    inherited = evaluate_inherited_candidate(research.frame, bundle.index, config)
    sessions = tuple(value.date() for value in bundle.index["date"].sort_values().drop_duplicates())
    persistent = apply_causal_persistence(inherited.predictions, sessions, config)
    evaluation = evaluate_policy(inherited.predictions, persistent, bundle, config)
    rank_metrics = pd.concat(
        [inherited.rank_metrics.assign(score_policy="raw_daily_rank"),
         _persistent_rank_metrics(persistent, config).assign(score_policy="causal_ema5_rerank")],
        ignore_index=True,
    )
    maximum_research_date = persistent["date"].max().date().isoformat()
    if maximum_research_date > "2018-12-31":
        raise PermissionError("Phase 5C 연구 계산이 허용 날짜를 넘었습니다")
    data_audit = dict(bundle.audit)
    data_audit.update(
        {
            "experiment_id": config.experiment_id,
            "source_hash": frozen["code_hash"],
            "config_hash": frozen["config_hash"],
            "data_hash": frozen["data_version"],
            "maximum_research_date": maximum_research_date,
            "research_calculated_rows": len(research.frame),
            "persistent_score_rows": len(persistent),
            "post_2018_rows_loaded_by_research_runner": 0,
            "post_2018_rows_calculated": 0,
            "post_2018_rows_evaluated": 0,
            "post_2018_rows_selected": 0,
            "development_test_input_loaded": False,
            "development_test_rows_loaded": 0,
            "development_test_rows_calculated": 0,
            "development_test_rows_evaluated": 0,
            "development_test_rows_selected": 0,
            "final_oos_accessed": False,
            "filter_applied_after_load": False,
            "research_audit": research.audit,
        }
    )
    policy_audit = {
        "score_smoothing": "causal_ema",
        "ema_span_sessions": config.ema_span_sessions,
        "reset_boundaries": ["fold", "membership_spell_id", "nonconsecutive_exchange_session"],
        "desired_entry_rank": config.desired_entry_rank,
        "fallback_max_rank": config.fallback_max_rank,
        "rank_loss_exit_below_rank": config.exit_rank,
        "maximum_holding_sessions": config.maximum_holding_sessions,
        "order_audit": evaluation.order_audit,
        "phase5b_handoff": handoff,
        "development_test_accessed": False,
        "final_oos_accessed": False,
    }
    score_contract = {
        "calculation_time": "official_close_t",
        "raw_score": "fold_train_only_elastic_a005_l02_prediction_daily_percentile_rank",
        "persistent_score": "causal_ema5_then_daily_cross_sectional_rerank",
        "order_time": "next_session_open_or_later",
        "entry_priority": "score_desc_security_id_asc_top10_then_fallback_to_rank20",
        "exit": "next_open_when_rank_below_top20_or_20_session_safety_limit",
        "minute_data_used": False,
        "development_test_accessed": False,
    }
    dependency_versions = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
    }
    run = {
        "experiment_id": config.experiment_id,
        "status": evaluation.decision["status"],
        "source_hash": frozen["code_hash"],
        "config_hash": frozen["config_hash"],
        "data_hash": frozen["data_version"],
        "policy_hash": frozen["model_hash"],
        "dependencies": dependency_versions,
        "run_command": config.payload["run_command"],
        "adaptive_diagnostic_only": True,
        "development_test_accessed": False,
        "final_oos_accessed": False,
    }
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"기존 Phase 5C 산출물을 덮어쓰지 않습니다: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phase5c_diagnostic_", dir=output.parent) as temporary:
        staging = Path(temporary) / output.name
        staging.mkdir()
        _write_csv(evaluation.metrics, staging / "portfolio_metrics.csv")
        _write_csv(rank_metrics, staging / "fold_rank_metrics.csv")
        _write_csv(inherited.fold_audit, staging / "fold_audit.csv")
        _write_json(staging / "policy_audit.json", policy_audit)
        _write_json(staging / "engineering_decision.json", evaluation.decision)
        _write_json(staging / "score_contract.json", score_contract)
        _write_json(staging / "data_audit.json", data_audit)
        _write_json(staging / "run.json", run)
        _manifest(staging)
        staging.replace(output)
    return run


def confirm_development_test(*_: object, **__: object) -> None:
    raise PermissionError("Phase 5C Development Test는 별도 사용자 승인과 동결 전까지 실행할 수 없습니다")
