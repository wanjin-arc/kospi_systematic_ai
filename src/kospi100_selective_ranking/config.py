from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from kospi100_multifactor.config import MultifactorConfig, load_analysis_config
from kospi100_ranking.config import Fold, Period


EXPERIMENT_ID = "EXP-20260823-004"
MODEL_CANDIDATE = "elastic_a005_l02"
POLICY_CANDIDATE = "elastic_a005_l02_selective_market_capacity"


@dataclass(frozen=True)
class SelectiveConfig:
    path: Path
    payload: Mapping[str, Any]
    base: MultifactorConfig
    experiment_id: str
    model_candidate: str
    policy_candidate: str
    ema_span_sessions: int
    entry_zscore: float
    exit_zscore: float
    risk_on_entry_rank: int
    risk_on_hold_rank: int
    neutral_entry_rank: int
    neutral_hold_rank: int
    maximum_holding_sessions: int

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


def _period(name: str, bounds: list[str]) -> Period:
    return Period(name, date.fromisoformat(bounds[0]), date.fromisoformat(bounds[1]))


def load_config(path: Path) -> SelectiveConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != "phase5d-selective-ranking-v1":
        raise ValueError("지원하지 않는 Phase 5D 설정 버전입니다")
    if payload.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("Phase 5D Experiment ID가 사전등록 값과 다릅니다")
    if payload.get("evaluation_status") != "REUSED_VALIDATION_DIAGNOSTIC_NOT_OOS":
        raise ValueError("2019~2021 재사용 진단 표기가 필요합니다")
    root = Path(str(payload.get("data_root")))
    if payload.get("required_partition_role") != "phase5_train_validation":
        raise PermissionError("Phase 5D는 Train/Validation 전용 파티션만 허용합니다")
    if payload.get("maximum_permitted_date") != "2021-12-31":
        raise PermissionError("Phase 5D 최대 입력일은 2021-12-31입니다")
    if payload.get("development_test_access") is not False:
        raise PermissionError("Development Test는 승인되지 않았습니다")
    if payload.get("final_oos_access") != "DENIED_UNTIL_PHASE_8":
        raise PermissionError("Final OOS 봉인 설정이 변경되었습니다")
    parts = {part.lower() for part in root.parts}
    if "sealed" in parts or "development" in parts:
        raise PermissionError("Phase 5D 허용 파티션 밖의 경로입니다")
    inherited = payload["inherited_signal"]
    if (
        inherited.get("feature_set"),
        inherited.get("candidate"),
        inherited.get("target"),
    ) != (
        "phase4b_multifactor_interaction_v1",
        MODEL_CANDIDATE,
        "forward_10_session_excess_open_to_open_rank",
    ):
        raise ValueError("Phase 5D 고정 Feature·모델·target 계약이 변경되었습니다")
    analysis = load_analysis_config(Path(str(inherited["phase4b_config"])))
    periods = {name: _period(name, bounds) for name, bounds in payload["periods"].items()}
    if {name: (value.start, value.end) for name, value in periods.items()} != {
        "train": (date(2011, 1, 1), date(2018, 12, 31)),
        "reused_validation": (date(2019, 1, 1), date(2021, 12, 31)),
    }:
        raise ValueError("Phase 5D 기간이 변경되었습니다")
    folds = tuple(
        Fold(
            str(item["fold"]),
            _period(f"{item['fold']}_train", item["train"]),
            _period(f"{item['fold']}_validation", item["validation"]),
        )
        for item in payload["folds"]
    )
    if tuple((fold.train.end.year, fold.validation.start.year) for fold in folds) != (
        (2018, 2019),
        (2019, 2020),
        (2020, 2021),
    ):
        raise ValueError("Phase 5D anchored fold가 변경되었습니다")
    score = payload["score_policy"]
    if (
        score.get("smoothing"),
        int(score.get("ema_span_sessions", -1)),
        float(score.get("entry_minimum_daily_zscore")),
        float(score.get("exit_below_daily_zscore")),
        int(score.get("risk_on_entry_fallback_rank", -1)),
        int(score.get("risk_on_hold_rank", -1)),
        int(score.get("neutral_entry_rank", -1)),
        int(score.get("neutral_hold_rank", -1)),
        bool(score.get("reset_on_fold_or_membership_spell_or_session_gap")),
    ) != ("causal_ema_raw_prediction", 5, 1.0, 0.0, 20, 20, 5, 5, True):
        raise ValueError("Phase 5D 선택형 점수 계약이 변경되었습니다")
    market = payload["market_policy"]
    if market.get("maximum_holdings_by_regime") != {"risk_on": 10, "neutral": 5, "risk_off": 0}:
        raise ValueError("시장상태별 최대 보유 수가 변경되었습니다")
    portfolio = payload["portfolio"]
    if (
        int(portfolio.get("maximum_holdings", -1)),
        int(portfolio.get("required_minimum_holdings", -1)),
        Decimal(str(portfolio.get("target_weight"))),
        int(portfolio.get("maximum_holding_sessions", -1)),
        bool(portfolio.get("allow_pyramiding")),
        portfolio.get("unallocated_cash"),
    ) != (10, 0, Decimal("0.10"), 20, False, "retain_without_penalty"):
        raise ValueError("Phase 5D 가변 보유·현금 계약이 변경되었습니다")
    diagnostic = payload["diagnostic_reporting"]
    if (
        bool(diagnostic.get("average_cash_is_hard_gate")),
        bool(diagnostic.get("minimum_holdings_is_hard_gate")),
        bool(diagnostic.get("promotion_allowed_from_this_run")),
        int(diagnostic.get("development_test_runs", -1)),
    ) != (False, False, False, 0):
        raise ValueError("Phase 5D 재사용 진단 승격 금지 계약이 변경되었습니다")
    if int(payload.get("purge_sessions", -1)) != 20 or int(payload.get("embargo_sessions", -1)) != 20:
        raise ValueError("purge와 embargo는 각각 20 세션이어야 합니다")
    costs = payload["costs"]
    if tuple(int(value) for value in costs["stress_multipliers"]) != (1, 2, 3):
        raise ValueError("비용 stress 배수가 변경되었습니다")
    base = MultifactorConfig(
        path=path,
        payload=payload,
        experiment_id=EXPERIMENT_ID,
        data_root=root,
        required_partition_role="phase5_train_validation",
        maximum_permitted_date=date(2021, 12, 31),
        periods=periods,
        folds=folds,
        stock_features=analysis.stock_features,
        regime_features=analysis.regime_features,
        interactions=analysis.interactions,
        purge_sessions=20,
        embargo_sessions=20,
        minimum_cross_section=int(payload["minimum_cross_section"]),
        candidate_order=(MODEL_CANDIDATE,),
        initial_cash=Decimal(portfolio["initial_cash_krw"]),
        holding_sessions=20,
        maximum_holdings=10,
        target_weight=Decimal(portfolio["target_weight"]),
        entry_gap_cap=Decimal(portfolio["entry_gap_cap"]),
        commission_rate=Decimal(costs["commission_rate_per_side"]),
        slippage_rate=Decimal(costs["slippage_rate_per_side"]),
        stress_multipliers=(1, 2, 3),
        tax_schedule_path=Path(costs["sell_tax_schedule"]),
        random_seed=int(payload["random_seed"]),
    )
    return SelectiveConfig(
        path=path,
        payload=payload,
        base=base,
        experiment_id=EXPERIMENT_ID,
        model_candidate=MODEL_CANDIDATE,
        policy_candidate=POLICY_CANDIDATE,
        ema_span_sessions=5,
        entry_zscore=1.0,
        exit_zscore=0.0,
        risk_on_entry_rank=20,
        risk_on_hold_rank=20,
        neutral_entry_rank=5,
        neutral_hold_rank=5,
        maximum_holding_sessions=20,
    )
