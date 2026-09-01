"""Phase 4F model-only preflight, 학습, 동결 및 재현 산출물."""

from __future__ import annotations

import csv
import hashlib
import json
import platform
from pathlib import Path
import pickle
from typing import Any, Iterable

import numpy as np
import pandas as pd
import scipy
import sklearn

from kospi200_phase5s.data import build_score_panel, load_phase5s_inputs, sha256
from kospi200_phase5s.labels import attach_reset_safe_labels

from .config import EXPERIMENT_ID, Phase4FConfig, load_config
from .modeling import FrozenModelBundle, bundle_state_hashes, fit_frozen_model_bundle


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "experiments" / "registry.csv"
CODE_PATHS = (
    "src/kospi100_backtest/__init__.py",
    "src/kospi100_backtest/costs.py",
    "src/kospi100_backtest/types.py",
    "src/kospi200_fundamental/__init__.py",
    "src/kospi200_fundamental/factors.py",
    "src/kospi200_phase4f/__init__.py",
    "src/kospi200_phase4f/cli.py",
    "src/kospi200_phase4f/config.py",
    "src/kospi200_phase4f/materialize.py",
    "src/kospi200_phase4f/modeling.py",
    "src/kospi200_phase4f/runner.py",
    "src/kospi200_phase5s/__init__.py",
    "src/kospi200_phase5s/config.py",
    "src/kospi200_phase5s/data.py",
    "src/kospi200_phase5s/labels.py",
    "src/kospi200_phase5s/modeling.py",
)


def _digest_paths(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted((Path(value) for value in paths), key=lambda value: value.as_posix()):
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\n")
    return digest.hexdigest()


def code_hash() -> str:
    paths = tuple(ROOT / value for value in CODE_PATHS)
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Phase 4F code hash 파일 누락: {missing}")
    return _digest_paths(paths)


def runtime_versions() -> dict[str, str]:
    """결정론적 재학습에 직접 관여하는 런타임 버전을 동결한다."""

    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
        "scikit_learn": sklearn.__version__,
    }


def artifact_tree_sha256(root: Path) -> str:
    """manifest를 제외한 artifact tree의 경로와 raw byte를 함께 hash한다."""

    root = Path(root)
    files = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and path.relative_to(root).as_posix() != "manifest.json"
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    if not files:
        raise ValueError("Phase 4F artifact tree가 비었습니다.")
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\n")
    return digest.hexdigest()


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if np.isfinite(number) else None
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(_json_safe(value), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _sample_signal_dates(sessions: tuple[str, ...], start: str, end: str, step: int) -> set[str]:
    eligible = [day for day in sessions if start <= day <= end]
    return set(eligible[:: int(step)])


def _data_version(config: Phase4FConfig, audit: dict[str, object]) -> str:
    release = json.loads(config.data_release_manifest.read_text(encoding="utf-8"))
    payload = {
        "data_release_id": config.data_release_id,
        "data_release_manifest_sha256": sha256(config.data_release_manifest),
        "release_output_tree_sha256": release.get("output_tree_sha256"),
        "input_tree_sha256": audit["input_tree_sha256"],
        "maximum_loaded_date": audit["maximum_permitted_date"],
        "corporate_action_policy": audit.get("corporate_action_semantics"),
        "share_change_gross_ratio_threshold": config.share_change_gross_ratio_threshold,
        "share_change_candidate_source": audit.get("share_change_candidate_source"),
        "share_change_candidate_uses_price": audit.get("share_change_candidate_uses_price"),
        "share_change_candidate_semantics": audit.get("share_change_candidate_semantics"),
        "technical_boundary_policy": audit.get("technical_boundary_policy"),
        "label_boundary_policy": audit.get("label_boundary_policy"),
        "cost_schedule_sha256": sha256(config.cost_schedule),
        "runtime_versions": runtime_versions(),
    }
    return _canonical_hash(payload)


def preflight_values(config_path: Path) -> tuple[dict[str, Any], Any]:
    config = load_config(config_path)
    if not config.data_release_manifest.is_file():
        raise FileNotFoundError("Phase 4F 물리 데이터 release를 먼저 materialize해야 합니다.")
    release = json.loads(config.data_release_manifest.read_text(encoding="utf-8"))
    if release.get("data_release_id") != config.data_release_id:
        raise ValueError("Phase 4F data release ID가 config와 다릅니다.")
    if release.get("max_date") != config.data_end.isoformat():
        raise PermissionError("Phase 4F data release 최대일이 2020-12-30이 아닙니다.")
    for output in release.get("outputs", {}).values():
        maximum = pd.to_datetime(output.get("max_date"), errors="coerce")
        if pd.isna(maximum) or maximum.date() > config.data_end:
            raise PermissionError("Phase 4F data release에 2021+ 행이 기록됐습니다.")
    inputs = load_phase5s_inputs(config)
    values = {
        "experiment_id": EXPERIMENT_ID,
        "code_hash": code_hash(),
        "config_hash": config.config_hash,
        "data_version": _data_version(config, inputs.audit),
        "cost_schedule_sha256": sha256(config.cost_schedule),
        "runtime_versions": runtime_versions(),
        "maximum_loaded_date": max(
            str(inputs.audit["membership_max_date"]),
            str(inputs.audit["market_max_date"]),
            str(inputs.audit["index_max_date"]),
            str(inputs.audit["fundamental_max_date"]),
        ),
        "final_oos_accessed": False,
    }
    if values["maximum_loaded_date"] > config.data_end.isoformat():
        raise PermissionError("Phase 4F loader가 2020 cutoff 이후 자료를 반환했습니다.")
    return values, inputs


def _registry_row() -> dict[str, str]:
    with REGISTRY.open(encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["experiment_id"] == EXPERIMENT_ID]
    if len(rows) != 1:
        raise ValueError(f"registry에 {EXPERIMENT_ID}가 정확히 한 행이어야 합니다.")
    return rows[0]


def verify_preregistration(values: dict[str, Any]) -> None:
    row = _registry_row()
    if row["status"] != "preregistered":
        raise PermissionError("Phase 4F registry 상태가 preregistered가 아닙니다.")
    expected = {
        "code_hash": values["code_hash"],
        "config_hash": values["config_hash"],
        "data_version": values["data_version"],
        "model_hash": "TRAINING_PENDING",
        "final_oos_accessed": "false",
    }
    mismatches = {key: (row.get(key), value) for key, value in expected.items() if row.get(key) != value}
    if mismatches:
        raise PermissionError(f"Phase 4F registry hash freeze 불일치: {mismatches}")


def _model_gate(
    bundle: FrozenModelBundle,
    expected_selection_keys: set[tuple[str, str]],
) -> dict[str, Any]:
    metrics = pd.DataFrame(bundle.selection_metrics)
    selected = metrics.loc[metrics["agent"].eq(bundle.primary_agent)]
    if len(selected) != 1:
        raise AssertionError("Phase 4F primary metric이 정확히 하나가 아닙니다.")
    row = selected.iloc[0]
    d_lineage = bundle.audit.get("d_selection_audit", [])
    expected_lineage = {2019: [2017, 2018], 2020: [2017, 2018, 2019]}
    lineage_pass = len(d_lineage) == 2 and all(
        list(item.get("meta_training_oof_years", [])) == expected_lineage.get(int(item["year"]))
        for item in d_lineage
    )
    d_coefficients = (
        bundle.audit.get("agent_d", {})
        .get("fitted_state", {})
        .get("coefficient", [])
    )
    oof_keys = [
        (str(item["date"]), str(item["ticker"]).zfill(6))
        for item in bundle.selection_oof_scores
    ]
    exact_oof_universe = (
        len(oof_keys) == len(set(oof_keys))
        and set(oof_keys) == expected_selection_keys
    )
    gates = {
        "both_selection_years_evaluated": bool(int(row["evaluated_years"]) == 2),
        "all_candidates_both_years_evaluated": bool(metrics["evaluated_years"].eq(2).all()),
        "positive_mean_rank_ic": bool(float(row["mean_rank_ic"]) > 0.0),
        "nonnegative_selection_year_at_least_one": bool(int(row["nonnegative_years"]) >= 1),
        "finite_top10_quality": bool(np.isfinite(float(row["mean_top10_target_quality"]))),
        "eligible_universe_scored_before_label_filter": bool(exact_oof_universe),
        "d_inner_oof_lineage": bool(lineage_pass),
        "d_coefficients_nonnegative": bool(
            len(d_coefficients) == len(bundle.agent_d_features)
            and all(float(value) >= -1e-12 for value in d_coefficients)
        ),
        "portfolio_metrics_used_for_selection": False,
    }
    gates["all_pass"] = all(
        bool(value) for key, value in gates.items() if key != "portfolio_metrics_used_for_selection"
    )
    return gates


def run(config_path: Path, output_root: Path) -> dict[str, Any]:
    config = load_config(config_path)
    output_root = Path(output_root)
    if output_root.exists():
        raise FileExistsError(f"Phase 4F output이 이미 존재합니다: {output_root}")
    values, inputs = preflight_values(config_path)
    verify_preregistration(values)
    score_panel = build_score_panel(inputs, minimum_history_sessions=60)
    sampled_dates = _sample_signal_dates(
        inputs.sessions,
        config.label_and_model_start.isoformat(),
        config.training_end.isoformat(),
        config.sample_every_sessions,
    )
    signals = score_panel.loc[score_panel["date"].isin(sampled_dates)].copy()
    labelled, label_audit = attach_reset_safe_labels(
        signals,
        inputs.market,
        inputs.sessions,
        inputs.index,
        inputs.membership,
        config.cost_schedule,
        horizon=config.target_horizon_sessions,
        downside_penalty=config.downside_penalty,
        commission_rate=config.base_commission_rate,
        slippage_rate=config.base_slippage_rate,
        label_start=config.label_and_model_start.isoformat(),
    )
    fit_panel = labelled.loc[
        labelled["label_valid"]
        & labelled["exit_date"].astype(str).le(config.training_end.isoformat())
    ].copy()
    if label_audit["valid_label_share_change_crossing_rows"] != 0:
        raise AssertionError("Phase 4F 유효 학습 라벨이 share-change candidate를 가로지릅니다.")
    if label_audit["valid_label_listed_shares_gap_rows"] != 0:
        raise AssertionError("Phase 4F 유효 학습 라벨이 listed-shares gap을 가로지릅니다.")
    if fit_panel.empty:
        raise ValueError("Phase 4F 유효 학습행이 없습니다.")
    if fit_panel["ticker"].isin(config.excluded_tickers).any():
        raise AssertionError("Phase 4F 학습행에 제외 종목이 있습니다.")
    if labelled["ticker"].isin(config.excluded_tickers).any():
        raise AssertionError("Phase 4F 전체 OOF score universe에 제외 종목이 있습니다.")
    # OOF scoring은 미래 label 유효성과 무관한 전체 eligible U_t를 유지한다.
    # modeling 내부에서만 label_valid/exit cutoff를 fit과 metric에 적용한다.
    bundle = fit_frozen_model_bundle(labelled, inputs.sessions, config)
    bundle_bytes = pickle.dumps(bundle, protocol=5)
    state_hashes = bundle_state_hashes(bundle)
    model_hash = str(state_hashes["model_state_hash"])
    expected_selection = labelled.loc[
        labelled["date"].astype(str).str[:4].isin({"2019", "2020"}),
        ["date", "ticker"],
    ].copy()
    if expected_selection.duplicated(["date", "ticker"]).any():
        raise AssertionError("Phase 4F selection score universe key가 중복됩니다.")
    expected_selection_keys = {
        (str(row.date), str(row.ticker).zfill(6))
        for row in expected_selection.itertuples(index=False)
    }
    selection_valid = labelled.loc[
        labelled["date"].astype(str).str[:4].isin({"2019", "2020"})
        & labelled["label_valid"]
    ]
    selection_boundary_violations = int(
        selection_valid["label_invalid_reason"].str.contains(
            "UNRESOLVED_SHARE_CHANGE_CROSSING|LISTED_SHARES_OBSERVATION_GAP",
            regex=True,
        ).sum()
    )
    if selection_boundary_violations:
        raise AssertionError("Phase 4F selection metric 유효행이 주식수 경계를 가로지릅니다.")
    gates = _model_gate(bundle, expected_selection_keys)
    model_gate_pass = bool(gates["all_pass"])
    # 사용자는 Phase 4F gate 실패 시에도 순서 검증을 위한 Phase 5S 소비개발
    # 진단을 계속하도록 지시했다. 다만 Phase 5S 최종 gate는 이 실패를 상속한다.
    phase5s_predict_only_diagnostic_allowed = True
    decision = (
        "FREEZE_MODEL_FOR_PHASE5S_CONSUMED_DIAGNOSTIC"
        if model_gate_pass
        else "FREEZE_BEST_DIAGNOSTIC_MODEL_GATE_FAIL"
    )

    output_root.mkdir(parents=True, exist_ok=False)
    (output_root / "frozen_model_bundle.pkl").write_bytes(bundle_bytes)
    metrics = pd.DataFrame(bundle.selection_metrics).sort_values("agent", kind="stable")
    metrics.to_csv(
        output_root / "selection_metrics.csv",
        index=False,
        float_format="%.12g",
        lineterminator="\n",
    )
    oof_scores = pd.DataFrame(bundle.selection_oof_scores).sort_values(
        ["date", "ticker"], kind="stable"
    )
    oof_scores.to_csv(
        output_root / "oof_scores.csv.gz",
        index=False,
        compression={"method": "gzip", "mtime": 0},
        float_format="%.12g",
        lineterminator="\n",
    )
    audit = {
        "input": inputs.audit,
        "label": label_audit,
        "score_panel_rows": int(len(score_panel)),
        "sampled_signal_rows": int(len(signals)),
        "fit_rows": int(len(fit_panel)),
        "fit_min_date": str(fit_panel["date"].min()),
        "fit_max_date": str(fit_panel["date"].max()),
        "fit_max_exit_date": str(fit_panel["exit_date"].max()),
        "excluded_training_rows": 0,
        "bundle": bundle.audit,
        "portfolio_accessed": False,
        "orders_created": 0,
        "post_2020_fit_rows": 0,
        "valid_fit_share_change_crossing_rows": 0,
        "valid_fit_listed_shares_gap_rows": 0,
        "valid_selection_boundary_crossing_rows": selection_boundary_violations,
        "technical_pre_boundary_history_leakage_rows": 0,
        "share_change_boundary_contract_complete": True,
        "final_oos_accessed": False,
    }
    _write_json(output_root / "audit.json", audit)
    _write_json(output_root / "label_audit.json", label_audit)
    _write_json(
        output_root / "fold_boundaries.json",
        {
            "oof_roles": bundle.audit["oof_roles"],
            "oof_folds": bundle.audit["oof_folds"],
            "d_selection_audit": bundle.audit["d_selection_audit"],
        },
    )
    _write_json(
        output_root / "feature_contract.json",
        {
            "agent_b_features": bundle.agent_b_features,
            "agent_c_features": bundle.agent_c_features,
            "agent_d_features": bundle.agent_d_features,
            "excluded_tickers": sorted(config.excluded_tickers),
            "fundamental_percentile_scope": "FINAL_ELIGIBLE_U_T",
        },
    )
    _write_json(output_root / "component_hashes.json", state_hashes)
    _write_json(
        output_root / "selected_primary.json",
        {
            "experiment_id": EXPERIMENT_ID,
            "primary_agent": bundle.primary_agent,
            "phase4f_model_gate_pass": model_gate_pass,
            "phase5s_predict_only_diagnostic_allowed": phase5s_predict_only_diagnostic_allowed,
            "model_state_hash": model_hash,
            "selection_metrics": bundle.selection_metrics,
        },
    )
    _write_json(
        output_root / "decision.json",
        {
            "experiment_id": EXPERIMENT_ID,
            "primary_agent": bundle.primary_agent,
            "gates": gates,
            "decision": decision,
            "phase4f_model_gate_pass": model_gate_pass,
            "phase5s_predict_only_diagnostic_allowed": phase5s_predict_only_diagnostic_allowed,
            "evidence_status": "CONSUMED_DEVELOPMENT_MODEL_ONLY",
        },
    )
    output_files = sorted(
        path
        for path in output_root.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    )
    output_hashes = {
        path.relative_to(output_root).as_posix(): sha256(path) for path in output_files
    }
    tree_hash = artifact_tree_sha256(output_root)
    manifest = {
        "schema_version": "v2-phase4f-share-change-safe-model-release-v1",
        "experiment_id": EXPERIMENT_ID,
        "decision": decision,
        "phase4f_model_gate_pass": model_gate_pass,
        "phase5s_eligible": model_gate_pass,
        "phase5s_predict_only_diagnostic_allowed": phase5s_predict_only_diagnostic_allowed,
        "primary_agent": bundle.primary_agent,
        "model_hash": model_hash,
        "model_state_hash": model_hash,
        "component_sha256": state_hashes["component_sha256"],
        "bundle_sha256": sha256(output_root / "frozen_model_bundle.pkl"),
        "artifact_tree_sha256": tree_hash,
        "input_hashes": values,
        "output_sha256": output_hashes,
        "agent_b_features": list(bundle.agent_b_features),
        "agent_c_features": list(bundle.agent_c_features),
        "agent_d_features": list(bundle.agent_d_features),
        "fit_max_date": str(fit_panel["date"].max()),
        "fit_max_exit_date": str(fit_panel["exit_date"].max()),
        "fit_allowed_through": config.training_end.isoformat(),
        "share_change_gross_ratio_threshold": config.share_change_gross_ratio_threshold,
        "share_change_candidate_uses_price": False,
        "share_change_candidate_semantics": "CANDIDATE_ONLY_NOT_EXECUTABLE_ACTION",
        "valid_fit_share_change_crossing_rows": 0,
        "valid_fit_listed_shares_gap_rows": 0,
        "valid_selection_boundary_crossing_rows": selection_boundary_violations,
        "technical_pre_boundary_history_leakage_rows": 0,
        "portfolio_accessed": False,
        "orders_created": 0,
        "final_oos_accessed": False,
    }
    _write_json(output_root / "manifest.json", manifest)
    return manifest


__all__ = [
    "artifact_tree_sha256",
    "code_hash",
    "preflight_values",
    "run",
    "runtime_versions",
    "verify_preregistration",
]
