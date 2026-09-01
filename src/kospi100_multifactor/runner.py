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

from kospi100_ranking.data import load_selection_bundle

from .config import MultifactorConfig, load_analysis_config, load_selection_config
from .modeling import (
    evaluate_candidates,
    feature_diagnostics,
    feature_score_relationships,
    prepare_multifactor_frame,
    refit_candidate,
)
from .portfolio import evaluate_internal_portfolios


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


def dependency_hash() -> tuple[str, dict[str, str]]:
    versions = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
    }
    canonical = json.dumps(versions, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), versions


def candidate_family_hash(config: MultifactorConfig) -> str:
    if not config.candidate_order:
        return "NO_MODEL_FEATURE_AUDIT"
    payload = {
        "models": config.payload["models"],
        "phase4b_config_hash": config.phase4b_config_hash,
        "target": config.payload["target"],
        "portfolio": config.payload["portfolio"],
        "random_seed": config.random_seed,
        "scikit_learn": sklearn.__version__,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _registry_row(experiment_id: str) -> dict[str, str]:
    with Path("experiments/registry.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["experiment_id"] == experiment_id]
    if len(rows) != 1:
        raise ValueError("Phase 4B/5B Experiment ID는 registry에 정확히 한 번 사전등록되어야 합니다")
    if rows[0]["status"] not in {"preregistered", "analysis_completed", "selection_completed", "rejected"}:
        raise PermissionError("registry 상태가 실행을 허용하지 않습니다")
    return rows[0]


def freeze_values(config: MultifactorConfig) -> dict[str, str]:
    registry = _registry_row(config.experiment_id)
    bundle = load_selection_bundle(config)  # manifest와 2018년 이하 물리 입력만 검증·로드한다.
    values = {
        "code_hash": source_hash(),
        "config_hash": config.config_hash,
        "data_version": bundle.data_hash,
        "model_hash": candidate_family_hash(config),
    }
    for field, actual in values.items():
        registered = registry.get(field, "")
        if registered not in {"", "PENDING_PRE_RUN_FREEZE", actual}:
            raise ValueError(f"registry {field}가 실제 동결값과 다릅니다")
    return values


def _assert_frozen(config: MultifactorConfig, bundle_data_hash: str) -> dict[str, str]:
    registry = _registry_row(config.experiment_id)
    values = {
        "code_hash": source_hash(),
        "config_hash": config.config_hash,
        "data_version": bundle_data_hash,
        "model_hash": candidate_family_hash(config),
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


def _data_audit(
    config: MultifactorConfig,
    bundle_audit: dict[str, object],
    research_audit: dict[str, object],
    frozen: dict[str, str],
) -> dict[str, object]:
    audit = dict(bundle_audit)
    audit.update(
        {
            "experiment_id": config.experiment_id,
            "source_hash": frozen["code_hash"],
            "config_hash": frozen["config_hash"],
            "data_hash": frozen["data_version"],
            "maximum_research_date": research_audit["maximum_signal_date"],
            "research_calculated_rows": research_audit["research_rows"],
            "post_2018_research_rows": 0,
            "2019_2021_rows_loaded_by_research_runner": 0,
            "2019_2021_rows_calculated": 0,
            "2019_2021_rows_evaluated": 0,
            "2019_2021_rows_selected": 0,
            "development_test_input_loaded": False,
            "development_test_rows_loaded": 0,
            "development_test_rows_calculated": 0,
            "development_test_rows_evaluated": 0,
            "development_test_rows_selected": 0,
            "final_oos_accessed": False,
            "research_audit": research_audit,
        }
    )
    return audit


def _phase5_failure_analysis() -> dict[str, object]:
    selection_path = Path("artifacts/phase5/selection/candidate_selection.json")
    metrics_path = Path("artifacts/phase5/selection/portfolio_metrics.csv")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    metrics = pd.read_csv(metrics_path)
    selected = str(selection["selected_candidate"])
    connected = metrics.loc[
        metrics["candidate"].eq(selected)
        & metrics["period"].eq("validation_2019_2021")
        & metrics["cost_multiplier"].eq(1)
    ].iloc[0]
    annual = metrics.loc[
        metrics["candidate"].eq(selected)
        & metrics["period"].str.startswith("F")
        & metrics["cost_multiplier"].eq(1)
    ]
    return {
        "source_experiment_id": "EXP-20260822-001",
        "selected_candidate": selected,
        "strategy_total_return": float(connected["total_return"]),
        "benchmark_total_return": float(connected["benchmark_total_return"]),
        "net_excess_return": float(connected["net_excess_return"]),
        "average_cash_weight": float(connected["average_cash_weight"]),
        "turnover_on_average_equity": float(connected["turnover_on_average_equity"]),
        "nonnegative_annual_excess_folds": int((annual["net_excess_return"].astype(float) >= 0.0).sum()),
        "diagnosis": [
            "단일 reversal_5 입력의 평균 rank IC는 양수지만 약해 비용 차감 포트폴리오 성과로 이어지지 않았다.",
            "모든 후보가 동일한 1차원 입력의 선형 또는 구간 변환이어서 새로운 정보가 추가되지 않았다.",
            "10세션 target과 20세션 보유가 불일치해 점수 갱신보다 오래된 포지션이 유지되었다.",
            "평균 현금 비중과 거래비용이 강한 상승장에서 지수 추종 대비 불리하게 작용했다.",
        ],
        "corrective_design": [
            "21개 종목 기술변수의 일별 횡단면 순위를 공동 입력으로 사용한다.",
            "5개 시장상태와 6개 사전등록 상호작용으로 종목 신호의 국면 의존성을 표현한다.",
            "target과 보유기간을 10세션으로 정렬한다.",
            "모든 내부 Validation 연도 및 연결 구간의 비용 차감 지수 초과수익률을 hard gate로 둔다.",
        ],
    }


def run_analysis(config_path: Path, output: Path) -> dict[str, object]:
    config = load_analysis_config(config_path)
    bundle = load_selection_bundle(config)
    frozen = _assert_frozen(config, bundle.data_hash)
    research = prepare_multifactor_frame(bundle, config)
    fold_metrics = feature_diagnostics(research.frame, bundle.index, config)
    summary = (
        fold_metrics.groupby("feature_id", sort=False)
        .agg(
            minimum_coverage=("coverage", "min"),
            mean_internal_validation_ic=("mean_daily_spearman_ic", "mean"),
            positive_internal_years=("mean_daily_spearman_ic", lambda values: int((values > 0).sum())),
            internal_years=("fold", "nunique"),
            minimum_hac_t=("hac_t_stat", "min"),
        )
        .reset_index()
    )
    minimum_coverage = float(config.payload["minimum_feature_coverage"])
    summary["joint_model_eligible"] = summary["minimum_coverage"] >= minimum_coverage
    data_audit = _data_audit(config, bundle.audit, research.audit, frozen)
    dep_hash, dependencies = dependency_hash()
    run = {
        "experiment_id": config.experiment_id,
        "status": "ANALYSIS_COMPLETED_TRAIN_INTERNAL_ONLY",
        "source_hash": frozen["code_hash"],
        "config_hash": frozen["config_hash"],
        "data_hash": frozen["data_version"],
        "dependency_hash": dep_hash,
        "dependencies": dependencies,
        "stock_feature_count": len(config.stock_features),
        "regime_feature_count": len(config.regime_features),
        "interaction_count": len(config.interactions),
        "run_command": config.payload["run_command"],
        "development_test_accessed": False,
        "final_oos_accessed": False,
    }
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"기존 Phase 4B 산출물을 덮어쓰지 않습니다: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phase4b_analysis_", dir=output.parent) as temporary:
        staging = Path(temporary) / output.name
        staging.mkdir()
        _write_csv(summary, staging / "feature_diagnostics.csv")
        _write_csv(fold_metrics, staging / "fold_feature_metrics.csv")
        _write_json(staging / "failure_analysis.json", _phase5_failure_analysis())
        _write_json(staging / "data_audit.json", data_audit)
        _write_json(staging / "run.json", run)
        _manifest(staging)
        staging.replace(output)
    return run


def run_selection(config_path: Path, output: Path) -> dict[str, object]:
    config = load_selection_config(config_path)
    phase4b_manifest_path = Path("artifacts/phase4b_multifactor/manifest.json")
    phase4b_manifest = json.loads(phase4b_manifest_path.read_text(encoding="utf-8"))
    if "run.json" not in phase4b_manifest:
        raise ValueError("완료된 Phase 4B manifest가 필요합니다")
    bundle = load_selection_bundle(config)
    frozen = _assert_frozen(config, bundle.data_hash)
    research = prepare_multifactor_frame(bundle, config)
    candidates = evaluate_candidates(research.frame, bundle.index, config)
    portfolios = evaluate_internal_portfolios(candidates.predictions, bundle, config)
    model_candidate = portfolios.accepted_candidate or portfolios.diagnostic_best_candidate
    model_payload, model_binary = refit_candidate(model_candidate, research.frame, bundle.index, config)
    relationships = feature_score_relationships(
        research.frame,
        candidates.predictions,
        model_candidate,
        config,
    )
    data_audit = _data_audit(config, bundle.audit, research.audit, frozen)
    data_audit.update(
        {
            "internal_validation_evaluated_rows": len(candidates.predictions),
            "accepted_model_selected_rows": (
                int(len(candidates.predictions.loc[candidates.predictions["candidate"].eq(portfolios.accepted_candidate)]))
                if portfolios.accepted_candidate
                else 0
            ),
            "diagnostic_model_rows": int(
                len(candidates.predictions.loc[candidates.predictions["candidate"].eq(model_candidate)])
            ),
        }
    )
    dep_hash, dependencies = dependency_hash()
    score_contract = {
        "calculation_time": "official_close_t",
        "eligible_universe": "is_member and eligible_new_entry and rank_eligible and tradable and not_ca_blocked",
        "stock_transform": "daily_cross_sectional_average_percentile_rank",
        "model_output": "predicted_forward_10_session_excess_return_rank",
        "final_score_transform": "daily_cross_sectional_average_percentile_rank",
        "order_priority": "score_desc_security_id_asc",
        "order_time": "next_session_open_or_later",
        "maximum_holdings": config.maximum_holdings,
        "holding_sessions": config.holding_sessions,
        "development_test_accessed": False,
    }
    selection = dict(portfolios.gate)
    selection.update(
        {
            "experiment_id": config.experiment_id,
            "model_artifact_candidate": model_candidate,
            "model_artifact_is_trading_candidate": portfolios.accepted_candidate is not None,
            "model_hash": model_payload["model_hash"],
            "phase4b_manifest_sha256": _sha256(phase4b_manifest_path),
            "candidate_count": len(config.candidate_order),
            "candidate_order": list(config.candidate_order),
        }
    )
    run = {
        "experiment_id": config.experiment_id,
        "status": portfolios.gate["status"],
        "source_hash": frozen["code_hash"],
        "config_hash": frozen["config_hash"],
        "data_hash": frozen["data_version"],
        "candidate_family_hash": frozen["model_hash"],
        "dependency_hash": dep_hash,
        "dependencies": dependencies,
        "accepted_candidate": portfolios.accepted_candidate,
        "diagnostic_best_candidate": portfolios.diagnostic_best_candidate,
        "model_hash": model_payload["model_hash"],
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
        "run_command": config.payload["run_command"],
        "development_test_accessed": False,
        "final_oos_accessed": False,
    }
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"기존 Phase 5B 산출물을 덮어쓰지 않습니다: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phase5b_selection_", dir=output.parent) as temporary:
        staging = Path(temporary) / output.name
        staging.mkdir()
        _write_csv(portfolios.metrics, staging / "candidate_portfolio_metrics.csv")
        _write_csv(candidates.rank_metrics, staging / "fold_rank_metrics.csv")
        _write_csv(candidates.fold_audit, staging / "fold_audit.csv")
        _write_csv(relationships, staging / "feature_relationships.csv")
        _write_json(staging / "candidate_selection.json", selection)
        _write_json(staging / "selected_model.json", model_payload)
        (staging / "selected_model.pkl").write_bytes(model_binary)
        _write_json(staging / "score_contract.json", score_contract)
        _write_json(staging / "data_audit.json", data_audit)
        _write_json(staging / "run.json", run)
        _manifest(staging)
        staging.replace(output)
    return run


def confirm_development_test(*_: object, **__: object) -> None:
    raise PermissionError("Phase 5B Development Test는 사용자 승인과 별도 동결 절차 전까지 실행할 수 없습니다")
