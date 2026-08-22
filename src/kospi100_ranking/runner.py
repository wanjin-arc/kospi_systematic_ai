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

from .config import RankingConfig, load_config
from .data import load_selection_bundle
from .modeling import evaluate_candidates, prepare_research_frame, refit_selected
from .portfolio import evaluate_portfolios


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
    )
    paths = sorted(path for root in roots for path in root.glob("*.py"))
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def dependency_hash() -> tuple[str, dict[str, str]]:
    versions = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
    }
    canonical = json.dumps(versions, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), versions


def candidate_family_hash(config: RankingConfig) -> str:
    payload = {
        "models": config.payload["models"],
        "feature_set": config.payload["feature_set"],
        "target": config.payload["target"],
        "random_seed": config.random_seed,
        "scikit_learn": sklearn.__version__,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _registry_row(experiment_id: str) -> dict[str, str]:
    with Path("experiments/registry.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["experiment_id"] == experiment_id]
    if len(rows) != 1:
        raise ValueError("Phase 5 Experiment ID는 registry에 정확히 한 번 사전등록되어야 합니다")
    if rows[0]["status"] not in {"preregistered", "selection_completed"}:
        raise PermissionError("registry 상태가 Selection 실행을 허용하지 않습니다")
    return rows[0]


def _frame_to_csv(frame: pd.DataFrame, path: Path) -> None:
    normalized = frame.copy()
    normalized.to_csv(path, index=False, lineterminator="\n", float_format="%.12g")


def _selection_payload(
    selected: str,
    portfolio_metrics: pd.DataFrame,
    rank_metrics: pd.DataFrame,
    config: RankingConfig,
) -> dict[str, object]:
    connected = portfolio_metrics.loc[
        portfolio_metrics["period"].eq("validation_2019_2021")
        & portfolio_metrics["cost_multiplier"].eq(1)
    ].copy()
    selected_metric = connected.loc[connected["candidate"].eq(selected)].iloc[0]
    selected_rank = rank_metrics.loc[rank_metrics["candidate"].eq(selected)]
    phase3 = config.payload["phase3_validation_baseline"]
    ranking = connected.sort_values(
        ["sharpe_zero_rf", "net_excess_return", "max_drawdown", "turnover_on_average_equity"],
        ascending=[False, False, False, True],
        kind="mergesort",
    )["candidate"].tolist()
    return {
        "experiment_id": config.experiment_id,
        "status": "SELECTION_FROZEN_DEVELOPMENT_TEST_NOT_AUTHORIZED",
        "selected_candidate": selected,
        "selected_feature_set": ["reversal_5"],
        "candidate_count": len(config.candidate_order),
        "candidate_order": list(config.candidate_order),
        "selection_priority": config.payload["selection"],
        "connected_validation_ranking": ranking,
        "selected_connected_validation": {
            "net_excess_return": selected_metric["net_excess_return"],
            "sharpe_zero_rf": selected_metric["sharpe_zero_rf"],
            "max_drawdown": selected_metric["max_drawdown"],
            "turnover_on_average_equity": selected_metric["turnover_on_average_equity"],
        },
        "selected_rank_diagnostics": {
            "mean_daily_spearman_ic": float(selected_rank["mean_daily_spearman_ic"].mean()),
            "mean_ndcg_at_10": float(selected_rank["ndcg_at_10"].mean()),
            "all_fold_coverage": float(selected_rank["coverage"].min()),
        },
        "phase3_validation_baseline": phase3,
        "validation_sharpe_improvement_vs_phase3": (
            float(selected_metric["sharpe_zero_rf"]) - float(phase3["sharpe_zero_rf"])
            if pd.notna(selected_metric["sharpe_zero_rf"])
            else None
        ),
        "development_test_accessed": False,
        "phase5_adoption_decision": "PENDING_SINGLE_DEVELOPMENT_TEST_AFTER_SEPARATE_USER_APPROVAL",
    }


def _manifest(output: Path) -> dict[str, str]:
    hashes = {
        path.relative_to(output).as_posix(): _sha256(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    _write_json(output / "manifest.json", hashes)
    return hashes


def run_selection(config_path: Path, output: Path) -> dict[str, object]:
    config = load_config(config_path)
    registry = _registry_row(config.experiment_id)
    if "development_test" in {part.lower() for part in output.parts}:
        raise PermissionError("Selection 산출물을 Development Test 경로에 쓸 수 없습니다")
    bundle = load_selection_bundle(config)
    code_hash = source_hash()
    dep_hash, dependencies = dependency_hash()
    frozen_fields = {
        "code_hash": code_hash,
        "config_hash": config.config_hash,
        "data_version": bundle.data_hash,
        "model_hash": candidate_family_hash(config),
    }
    for field, actual in frozen_fields.items():
        registered = registry.get(field, "")
        if registered not in {actual, "PENDING_PRE_SELECTION_FREEZE"}:
            raise ValueError(f"registry {field}가 실제 동결값과 다릅니다")

    research, research_audit = prepare_research_frame(bundle, config.minimum_cross_section)
    if research["date"].max().date() > config.maximum_permitted_date:
        raise PermissionError("Selection 계산 행이 2021년을 넘습니다")
    candidates = evaluate_candidates(research, bundle.index, config)
    portfolios = evaluate_portfolios(candidates.predictions, bundle, config)
    selected_model = refit_selected(portfolios.selected_candidate, research, bundle.index, config)
    selection = _selection_payload(
        portfolios.selected_candidate,
        portfolios.metrics,
        candidates.rank_metrics,
        config,
    )
    selection["selected_model_hash"] = selected_model["model_hash"]
    selection["dependency_hash"] = dep_hash

    fold_metrics = candidates.fold_audit.merge(
        candidates.rank_metrics,
        on=["candidate", "fold"],
        how="left",
        validate="one_to_one",
    )
    data_audit = dict(bundle.audit)
    data_audit.update(
        {
            "source_hash": code_hash,
            "config_hash": config.config_hash,
            "research_calculated_rows": len(research),
            "validation_evaluated_rows": len(candidates.predictions),
            "validation_selected_rows": int(
                len(candidates.predictions.loc[candidates.predictions["candidate"].eq(portfolios.selected_candidate)])
            ),
            "development_test_rows_loaded": 0,
            "development_test_rows_calculated": 0,
            "development_test_rows_evaluated": 0,
            "development_test_rows_selected": 0,
            "research_audit": research_audit,
        }
    )
    run = {
        "experiment_id": config.experiment_id,
        "status": "SELECTION_COMPLETED_DEVELOPMENT_TEST_PENDING_APPROVAL",
        "source_hash": code_hash,
        "config_hash": config.config_hash,
        "data_hash": bundle.data_hash,
        "dependency_hash": dep_hash,
        "dependencies": dependencies,
        "selected_candidate": portfolios.selected_candidate,
        "selected_model_hash": selected_model["model_hash"],
        "folds": [
            {
                "fold": fold.name,
                "train": [fold.train.start, fold.train.end],
                "validation": [fold.validation.start, fold.validation.end],
            }
            for fold in config.folds
        ],
        "purge_sessions": config.purge_sessions,
        "embargo_sessions": config.embargo_sessions,
        "random_seed": config.random_seed,
        "costs": config.payload["costs"],
        "run_command": config.payload["run_command"],
        "development_test_accessed": False,
        "final_oos_accessed": False,
    }

    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"기존 Selection 산출물을 덮어쓰지 않습니다: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phase5_selection_", dir=output.parent) as temporary:
        staging = Path(temporary) / output.name
        staging.mkdir()
        _write_json(staging / "data_audit.json", data_audit)
        _frame_to_csv(fold_metrics, staging / "fold_metrics.csv")
        _frame_to_csv(candidates.rank_metrics, staging / "rank_metrics.csv")
        _frame_to_csv(portfolios.metrics, staging / "portfolio_metrics.csv")
        _write_json(staging / "candidate_selection.json", selection)
        _write_json(staging / "selected_model.json", selected_model)
        _write_json(staging / "run.json", run)
        _manifest(staging)
        staging.replace(output)
    return run


def confirm_development_test(*_: object, **__: object) -> None:
    raise PermissionError("Development Test는 Selection 동결 후 별도 사용자 승인이 필요합니다")
