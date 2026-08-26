from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from kospi100_multifactor.config import INTERACTIONS, REGIME_FEATURES, STOCK_FEATURES, MultifactorConfig
from kospi100_ranking.config import Fold, Period


EXPERIMENT_ID = "EXP-20260825-004"


@dataclass(frozen=True)
class Phase5IConfig:
    path: Path
    payload: Mapping[str, Any]
    base: MultifactorConfig
    inherited_candidate: str
    ema_span_sessions: int
    entry_rank: int
    entry_persistence_sessions: int
    exit_rank: int
    exit_persistence_sessions: int
    rebalance_sessions: int
    maximum_holding_sessions: int

    @property
    def experiment_id(self) -> str:
        return EXPERIMENT_ID

    @property
    def policy_candidate(self) -> str:
        return "phase5i_hysteresis_rebalance"

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


def _forbidden(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return bool(parts & {"sealed", "final_oos_v24", "development"})


def load_config(path: Path) -> Phase5IConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != "phase5i-2004-hysteresis-rebalance-v1":
        raise ValueError("Phase 5I 설정 버전이 다릅니다")
    if payload.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("Phase 5I Experiment ID가 다릅니다")
    root = Path(str(payload["data_root"]))
    if _forbidden(root):
        raise PermissionError("Phase 5I는 허용된 2018년 이하 물리 파티션만 읽습니다")
    if payload.get("required_partition_role") != "phase5i_train_internal_2004_2018":
        raise PermissionError("Phase 5I 입력 역할이 다릅니다")
    if payload.get("maximum_permitted_date") != "2018-12-31":
        raise PermissionError("Phase 5I 최대 입력일이 다릅니다")
    if payload.get("development_test_access") is not False or payload.get("final_oos_access") != "DENIED_UNTIL_PHASE_8":
        raise PermissionError("보호 데이터 접근 설정이 변경되었습니다")
    if payload.get("research_period") != ["2004-01-02", "2018-12-31"]:
        raise ValueError("Phase 5I 연구기간이 다릅니다")
    target = payload["target"]
    if (target.get("entry_offset_sessions"), target.get("exit_offset_sessions"), target.get("cross_sectional_transform")) != (1, 11, "percentile_rank_average"):
        raise ValueError("Phase 5I target 시점이 변경되었습니다")
    model = payload["model"]
    if model.get("candidate") != "elastic_a005_l02":
        raise ValueError("Phase 5I 모델은 고정 ElasticNet 하나입니다")
    if (model.get("stock_features"), model.get("regime_features"), model.get("interactions")) != (
        "phase4b_frozen_21_in_order", "phase4b_frozen_5_in_order", "phase4b_frozen_6_in_order"
    ):
        raise ValueError("Phase 4B 고정 Feature 인계가 변경되었습니다")
    fold_items = list(payload["internal_folds"])
    folds = tuple(
        Fold(
            str(item["fold"]),
            Period(f"{item['fold']}_train", date.fromisoformat(item["train"][0]), date.fromisoformat(item["train"][1])),
            Period(f"{item['fold']}_validation", date.fromisoformat(item["validation"][0]), date.fromisoformat(item["validation"][1])),
        )
        for item in fold_items
    )
    if tuple(fold.validation.start.year for fold in folds) != tuple(range(2011, 2019)):
        raise ValueError("Phase 5I는 2011~2018 연도별 fold 8개여야 합니다")
    if any(fold.train.start != date(2004, 1, 2) or fold.train.end.year + 1 != fold.validation.start.year for fold in folds):
        raise ValueError("Phase 5I anchored fold가 변경되었습니다")
    if int(payload["purge_sessions"]) != 20 or int(payload["embargo_sessions"]) != 20:
        raise ValueError("purge/embargo는 각각 20세션입니다")
    policy = payload["policy"]
    expected_policy = (5, 10, 3, 20, 3, 5, 20, 10, 0, Decimal("0.10"), False)
    actual_policy = (
        int(policy["ema_span_sessions"]), int(policy["entry_top_rank"]), int(policy["entry_persistence_sessions"]),
        int(policy["exit_below_rank"]), int(policy["exit_persistence_sessions"]), int(policy["rebalance_every_sessions"]),
        int(policy["maximum_holding_sessions"]), int(policy["maximum_holdings"]), int(policy["minimum_holdings"]),
        Decimal(str(policy["target_weight"])), bool(policy["allow_pyramiding"]),
    )
    if actual_policy != expected_policy:
        raise ValueError("Phase 5I 매매 구조가 사전등록 값과 다릅니다")
    costs = payload["costs"]
    if tuple(costs["stress_multipliers"]) != (1, 2, 3):
        raise ValueError("비용 stress가 변경되었습니다")
    base = MultifactorConfig(
        path=path,
        payload=payload,
        experiment_id=EXPERIMENT_ID,
        data_root=root,
        required_partition_role=str(payload["required_partition_role"]),
        maximum_permitted_date=date(2018, 12, 31),
        periods={"research": Period("research", date(2004, 1, 2), date(2018, 12, 31))},
        folds=folds,
        stock_features=STOCK_FEATURES,
        regime_features=REGIME_FEATURES,
        interactions=INTERACTIONS,
        purge_sessions=20,
        embargo_sessions=20,
        minimum_cross_section=int(payload["minimum_cross_section"]),
        candidate_order=("elastic_a005_l02",),
        initial_cash=Decimal(costs["initial_cash_krw"]),
        holding_sessions=20,
        maximum_holdings=10,
        target_weight=Decimal("0.10"),
        entry_gap_cap=Decimal(policy["entry_gap_cap"]),
        commission_rate=Decimal(costs["commission_rate_per_side"]),
        slippage_rate=Decimal(costs["slippage_rate_per_side"]),
        stress_multipliers=(1, 2, 3),
        tax_schedule_path=Path(costs["sell_tax_schedule"]),
        random_seed=int(payload["random_seed"]),
    )
    return Phase5IConfig(
        path, payload, base, "elastic_a005_l02", 5, 10, 3, 20, 3, 5, 20
    )
