"""v2 Phase 4F model-only 설정과 fail-closed 경계."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from kospi200_phase5s.config import (
    ExcludedSecurity,
    FUNDAMENTAL_FEATURES,
    TECHNICAL_FEATURES,
    guard_path,
)


SCHEMA_VERSION = "v2-phase4f-share-change-safe-model-v1"
EXPERIMENT_ID = "EXP-20260901-003"
TRAINING_END = date(2020, 12, 30)


@dataclass(frozen=True)
class Phase4FConfig:
    path: Path
    payload: Mapping[str, Any]
    experiment_id: str
    data_release_id: str
    membership_root: Path
    market_roots: tuple[Path, ...]
    fundamental_panel: Path
    index_file: Path
    corporate_action_file: Path
    data_release_manifest: Path
    engine_config: Path
    cost_schedule: Path
    data_start: date
    label_and_model_start: date
    fundamental_start: date
    training_end: date
    data_end: date
    oof_years: tuple[int, ...]
    selection_years: tuple[int, ...]
    target_horizon_sessions: int
    sample_every_sessions: int
    purge_sessions: int
    embargo_sessions: int
    downside_penalty: float
    share_change_gross_ratio_threshold: float
    excluded_securities: tuple[ExcludedSecurity, ...]
    base_commission_rate: float
    base_slippage_rate: float
    seed: int

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    @property
    def excluded_tickers(self) -> frozenset[str]:
        return frozenset(item.ticker for item in self.excluded_securities)

    @property
    def excluded_security_ids(self) -> frozenset[str]:
        return frozenset(item.security_id for item in self.excluded_securities)


def _equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise ValueError(f"Phase 4F 동결 계약 변경: {label}")


def _path(payload: Mapping[str, Any], key: str) -> Path:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Phase 4F 경로 누락: {key}")
    return guard_path(Path(value))


def load_config(path: Path) -> Phase4FConfig:
    path = guard_path(Path(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    _equal(payload.get("schema_version"), SCHEMA_VERSION, "schema_version")
    _equal(payload.get("experiment_id"), EXPERIMENT_ID, "experiment_id")
    _equal(payload.get("supersedes_experiment_id"), "EXP-20260901-001", "supersedes")
    _equal(payload.get("data_start"), "2004-01-02", "data_start")
    _equal(payload.get("label_and_model_start"), "2011-01-03", "label_and_model_start")
    _equal(payload.get("fundamental_start"), "2016-03-24", "fundamental_start")
    _equal(payload.get("training_end"), TRAINING_END.isoformat(), "training_end")
    _equal(payload.get("data_end"), TRAINING_END.isoformat(), "data_end")
    _equal(tuple(payload.get("oof_years", ())), (2017, 2018, 2019, 2020), "oof_years")
    _equal(tuple(payload.get("selection_years", ())), (2019, 2020), "selection_years")
    for key in ("target_horizon_sessions", "sample_every_sessions", "purge_sessions", "embargo_sessions"):
        _equal(int(payload.get(key, -1)), 20, key)
    _equal(float(payload.get("downside_penalty", -1)), 0.5, "downside_penalty")
    boundary = payload.get("share_change_boundary")
    if not isinstance(boundary, Mapping):
        raise ValueError("Phase 4F share_change_boundary 계약 누락")
    _equal(
        float(boundary.get("share_change_gross_ratio_threshold", -1)),
        1.20,
        "share-change gross ratio threshold",
    )
    _equal(boundary.get("source"), "CONSECUTIVE_SESSION_LISTED_SHARES", "share-change source")
    _equal(
        boundary.get("semantics"),
        "CANDIDATE_ONLY_NOT_EXECUTABLE_ACTION",
        "share-change semantics",
    )
    _equal(boundary.get("candidate_uses_price"), False, "share-change price independence")
    _equal(
        boundary.get("label_policy"),
        "INVALIDATE_SIGNAL_TO_EXIT_CROSSING",
        "share-change label policy",
    )
    _equal(
        boundary.get("technical_policy"),
        "RESET_SEGMENT_AT_CANDIDATE_OR_OBSERVATION_GAP",
        "share-change technical policy",
    )
    if payload.get("model_training_approved") is not True:
        raise PermissionError("Phase 4F 모델 학습 승인이 없습니다.")
    if payload.get("portfolio_backtest_approved") is not False:
        raise PermissionError("Phase 4F에서는 포트폴리오 백테스트가 금지됩니다.")
    for key in ("external_portfolio_execution_approved", "network_order_submission", "final_oos_access"):
        if payload.get(key) is not False:
            raise PermissionError(f"Phase 4F 금지 플래그가 변경됐습니다: {key}")

    raw_exclusions = payload.get("excluded_securities")
    if not isinstance(raw_exclusions, list):
        raise ValueError("Phase 4F 제외 security 계약 누락")
    exclusions = tuple(
        ExcludedSecurity(
            str(item["security_id"]),
            str(item["ticker"]).zfill(6),
            str(item.get("audit_name", "")),
        )
        for item in raw_exclusions
    )
    expected = {
        ("KRX_COMMON:005930", "005930"),
        ("KRX_COMMON:000660", "000660"),
    }
    if {(item.security_id, item.ticker) for item in exclusions} != expected:
        raise ValueError("Phase 4F 삼성전자·SK하이닉스 제외 계약 변경")

    agent_b = payload.get("agent_b", {})
    _equal(tuple(agent_b.get("features", ())), FUNDAMENTAL_FEATURES, "Agent B features")
    _equal(agent_b.get("feature_suffix"), "__phase4e_percentile", "Agent B suffix")
    _equal(agent_b.get("model"), "RIDGE_FIXED", "Agent B model")
    _equal(float(agent_b.get("alpha", -1)), 10.0, "Agent B alpha")
    _equal(agent_b.get("imputer_strategy"), "median", "Agent B imputer")
    _equal(agent_b.get("keep_empty_features"), True, "Agent B keep-empty policy")
    _equal(
        agent_b.get("all_missing_fold_policy"),
        "KEEP_FEATURE_ZERO_AFTER_IMPUTE",
        "Agent B all-missing fold policy",
    )
    _equal(
        float(agent_b.get("missing_score_percentile", -1)),
        0.5,
        "Agent B missing percentile",
    )
    agent_c = payload.get("agent_c", {})
    _equal(tuple(agent_c.get("features", ())), TECHNICAL_FEATURES, "Agent C features")
    _equal(agent_c.get("model"), "HIST_GRADIENT_BOOSTING_FIXED", "Agent C model")
    for key, expected_value in {
        "learning_rate": 0.05,
        "max_depth": 3,
        "max_iter": 100,
        "min_samples_leaf": 100,
        "l2_regularization": 10.0,
    }.items():
        actual = agent_c.get(key)
        _equal(float(actual), float(expected_value), f"Agent C {key}")
    agent_d = payload.get("agent_d", {})
    _equal(agent_d.get("model"), "POSITIVE_RIDGE_OOF", "Agent D model")
    _equal(float(agent_d.get("alpha", -1)), 10.0, "Agent D alpha")
    if agent_d.get("hard_fundamental_gate") is not False:
        raise ValueError("Phase 4F B hard gate 금지")

    selection = payload.get("selection", {})
    _equal(
        tuple(selection.get("metric_order", ())),
        (
            "mean_rank_ic",
            "nonnegative_years",
            "mean_top10_target_quality",
            "simplicity",
        ),
        "selection.metric_order",
    )
    _equal(float(selection.get("minimum_mean_rank_ic", -1)), 0.0, "selection IC floor")
    _equal(
        int(selection.get("minimum_nonnegative_selection_years", -1)),
        1,
        "selection nonnegative years",
    )
    _equal(
        int(selection.get("required_evaluated_selection_years", -1)),
        2,
        "selection evaluated years",
    )
    for key in (
        "d_requires_strict_improvement_vs_best_single_mean_rank_ic",
        "d_requires_noninferior_to_best_single_top10_quality",
        "d_requires_no_fewer_nonnegative_years_than_best_single",
    ):
        _equal(selection.get(key), True, f"selection.{key}")
    _equal(
        tuple(selection.get("simplicity_order", ())),
        ("C_ONLY", "B_ONLY", "D_SOFT_FUSION"),
        "selection.simplicity_order",
    )
    _equal(float(payload.get("base_commission_rate", -1)), 0.0002, "commission")
    _equal(float(payload.get("base_slippage_rate", -1)), 0.001, "slippage")
    _equal(int(payload.get("seed", -1)), 20260901, "seed")

    sources = payload.get("materialization_sources")
    if not isinstance(sources, Mapping):
        raise ValueError("Phase 4F materialization_sources 누락")
    for value in sources.values():
        guard_path(Path(str(value)))
    market_values = payload.get("market_roots")
    if not isinstance(market_values, list) or not market_values:
        raise ValueError("Phase 4F market_roots 누락")
    return Phase4FConfig(
        path=path,
        payload=payload,
        experiment_id=EXPERIMENT_ID,
        data_release_id=str(payload["data_release_id"]),
        membership_root=_path(payload, "membership_root"),
        market_roots=tuple(guard_path(Path(str(value))) for value in market_values),
        fundamental_panel=_path(payload, "fundamental_panel"),
        index_file=_path(payload, "index_file"),
        corporate_action_file=_path(payload, "corporate_action_file"),
        data_release_manifest=_path(payload, "data_release_manifest"),
        engine_config=_path(payload, "engine_config"),
        cost_schedule=_path(payload, "cost_schedule"),
        data_start=date.fromisoformat(str(payload["data_start"])),
        label_and_model_start=date.fromisoformat(str(payload["label_and_model_start"])),
        fundamental_start=date.fromisoformat(str(payload["fundamental_start"])),
        training_end=date.fromisoformat(str(payload["training_end"])),
        data_end=date.fromisoformat(str(payload["data_end"])),
        oof_years=tuple(int(value) for value in payload["oof_years"]),
        selection_years=tuple(int(value) for value in payload["selection_years"]),
        target_horizon_sessions=int(payload["target_horizon_sessions"]),
        sample_every_sessions=int(payload["sample_every_sessions"]),
        purge_sessions=int(payload["purge_sessions"]),
        embargo_sessions=int(payload["embargo_sessions"]),
        downside_penalty=float(payload["downside_penalty"]),
        share_change_gross_ratio_threshold=float(
            boundary["share_change_gross_ratio_threshold"]
        ),
        excluded_securities=exclusions,
        base_commission_rate=float(payload["base_commission_rate"]),
        base_slippage_rate=float(payload["base_slippage_rate"]),
        seed=int(payload["seed"]),
    )


__all__ = ["EXPERIMENT_ID", "Phase4FConfig", "SCHEMA_VERSION", "TRAINING_END", "load_config"]
