from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from kospi100_multifactor.config import MultifactorConfig, load_selection_config


EXPERIMENT_ID = "EXP-20260823-003"
INHERITED_CANDIDATE = "elastic_a005_l02"
POLICY_CANDIDATE = "elastic_a005_l02_ema5_top10_hold20"


@dataclass(frozen=True)
class Phase5CConfig:
    path: Path
    payload: Mapping[str, Any]
    base: MultifactorConfig
    experiment_id: str
    inherited_candidate: str
    policy_candidate: str
    ema_span_sessions: int
    desired_entry_rank: int
    fallback_max_rank: int
    exit_rank: int
    maximum_holding_sessions: int
    minimum_turnover_reduction_ratio: float
    minimum_explicit_cost_reduction_ratio: float
    maximum_average_cash_weight: float
    minimum_net_excess_improvement: float
    maximum_mdd_deterioration: float

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


def _forbidden_path(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return "sealed" in parts or "final_oos_v24" in parts or "development" in parts


def load_config(path: Path) -> Phase5CConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != "phase5c-persistent-ranking-v1":
        raise ValueError("지원하지 않는 Phase 5C 설정 버전입니다")
    if payload.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("Phase 5C Experiment ID가 사전등록 값과 다릅니다")
    if payload.get("phase5b_experiment_id") != "EXP-20260823-002":
        raise ValueError("Phase 5B 인계 Experiment ID가 다릅니다")
    base_path = Path(str(payload.get("phase5b_config")))
    base = load_selection_config(base_path)
    data_root = Path(str(payload.get("data_root")))
    if data_root != base.data_root or _forbidden_path(data_root):
        raise PermissionError("Phase 5C는 허용된 2018년 이하 물리 파티션만 읽을 수 있습니다")
    if payload.get("required_partition_role") != "phase4b_train_internal":
        raise PermissionError("Phase 5C 파티션 역할이 사전등록 값과 다릅니다")
    if payload.get("maximum_permitted_date") != "2018-12-31":
        raise PermissionError("Phase 5C 최대 입력일은 2018-12-31입니다")
    if payload.get("development_test_access") is not False:
        raise PermissionError("Phase 5C Development Test는 승인되지 않았습니다")
    if payload.get("final_oos_access") != "DENIED_UNTIL_PHASE_8":
        raise PermissionError("Final OOS 봉인 설정이 변경되었습니다")
    inherited = payload["inherited_signal"]
    if (
        inherited.get("candidate"),
        inherited.get("features"),
        inherited.get("target"),
    ) != (
        INHERITED_CANDIDATE,
        "phase4b_multifactor_interaction_v1",
        "forward_10_session_excess_open_to_open_rank",
    ):
        raise ValueError("Phase 5B 고정 신호 계약이 변경되었습니다")
    policy = payload["ranking_policy"]
    actual_policy = (
        policy.get("score_smoothing"),
        int(policy.get("ema_span_sessions", -1)),
        bool(policy.get("reset_on_fold_or_membership_spell_or_session_gap")),
        int(policy.get("desired_entry_rank", -1)),
        int(policy.get("fallback_max_rank", -1)),
        int(policy.get("rank_loss_exit_below_rank", -1)),
        int(policy.get("maximum_holding_sessions", -1)),
        int(policy.get("maximum_holdings", -1)),
        Decimal(str(policy.get("target_weight"))),
        bool(policy.get("allow_pyramiding")),
        Decimal(str(policy.get("entry_gap_cap"))),
        policy.get("order_time"),
    )
    expected_policy = (
        "causal_ema",
        5,
        True,
        10,
        20,
        20,
        20,
        10,
        Decimal("0.10"),
        False,
        Decimal("0.05"),
        "next_session_open_or_later",
    )
    if actual_policy != expected_policy:
        raise ValueError("Phase 5C 점수 지속성·주문 계약이 변경되었습니다")
    diagnostic = payload["adaptive_diagnostic"]
    expected_diagnostic = (
        "2015_2018_internal_validation_only",
        "phase5b_top10_hold10",
        0.40,
        0.30,
        0.10,
        0.0,
        0.05,
        False,
        0,
    )
    actual_diagnostic = (
        diagnostic.get("period"),
        diagnostic.get("reference_policy"),
        float(diagnostic.get("minimum_turnover_reduction_ratio")),
        float(diagnostic.get("minimum_explicit_cost_reduction_ratio")),
        float(diagnostic.get("maximum_average_cash_weight")),
        float(diagnostic.get("minimum_net_excess_improvement")),
        float(diagnostic.get("maximum_mdd_deterioration_percentage_points")),
        bool(diagnostic.get("result_is_confirmatory")),
        int(diagnostic.get("development_test_runs", -1)),
    )
    if actual_diagnostic != expected_diagnostic:
        raise ValueError("Phase 5C 적응적 진단 gate가 변경되었습니다")
    if int(payload.get("purge_sessions", -1)) != 20 or int(payload.get("embargo_sessions", -1)) != 20:
        raise ValueError("purge와 embargo는 각각 20 세션이어야 합니다")
    if int(payload.get("minimum_cross_section", -1)) != 30:
        raise ValueError("최소 횡단면은 30이어야 합니다")
    return Phase5CConfig(
        path=path,
        payload=payload,
        base=base,
        experiment_id=EXPERIMENT_ID,
        inherited_candidate=INHERITED_CANDIDATE,
        policy_candidate=POLICY_CANDIDATE,
        ema_span_sessions=5,
        desired_entry_rank=10,
        fallback_max_rank=20,
        exit_rank=20,
        maximum_holding_sessions=20,
        minimum_turnover_reduction_ratio=0.40,
        minimum_explicit_cost_reduction_ratio=0.30,
        maximum_average_cash_weight=0.10,
        minimum_net_excess_improvement=0.0,
        maximum_mdd_deterioration=0.05,
    )
