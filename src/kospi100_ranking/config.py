from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class Period:
    name: str
    start: date
    end: date


@dataclass(frozen=True)
class Fold:
    name: str
    train: Period
    validation: Period


@dataclass(frozen=True)
class RankingConfig:
    path: Path
    payload: Mapping[str, Any]
    experiment_id: str
    data_root: Path
    required_partition_role: str
    maximum_permitted_date: date
    periods: Mapping[str, Period]
    folds: tuple[Fold, ...]
    purge_sessions: int
    embargo_sessions: int
    minimum_cross_section: int
    candidate_order: tuple[str, ...]
    initial_cash: Decimal
    holding_sessions: int
    maximum_holdings: int
    target_weight: Decimal
    entry_gap_cap: Decimal
    commission_rate: Decimal
    slippage_rate: Decimal
    stress_multipliers: tuple[int, ...]
    tax_schedule_path: Path
    random_seed: int

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


EXPECTED_CANDIDATES = (
    "raw_rank",
    "ols",
    "tree_d1_l002",
    "tree_d1_l005",
    "tree_d2_l002",
    "tree_d2_l005",
    "tree_d3_l002",
    "tree_d3_l005",
)


def _period(name: str, bounds: list[str]) -> Period:
    return Period(name, date.fromisoformat(bounds[0]), date.fromisoformat(bounds[1]))


def _forbidden_path(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return "sealed" in parts or "final_oos_v24" in parts


def load_config(path: Path) -> RankingConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != "phase5-ranking-v1":
        raise ValueError("지원하지 않는 Phase 5 설정 버전입니다")
    if payload.get("experiment_id") != "EXP-20260822-001":
        raise ValueError("Phase 5 Experiment ID가 사전등록 값과 다릅니다")
    if payload.get("required_partition_role") != "phase5_train_validation":
        raise PermissionError("Selection은 Train/Validation 전용 파티션만 허용합니다")
    if payload.get("maximum_permitted_date") != "2021-12-31":
        raise PermissionError("Selection 최대 입력일은 2021-12-31입니다")
    if payload.get("development_test_access") is not False:
        raise PermissionError("Development Test는 별도 승인 전 접근할 수 없습니다")
    if payload.get("final_oos_access") != "DENIED_UNTIL_PHASE_8":
        raise PermissionError("Final OOS는 Phase 8 전까지 봉인되어야 합니다")

    root = Path(str(payload["data_root"]))
    if _forbidden_path(root):
        raise PermissionError("봉인 데이터 경로는 Phase 5에서 금지됩니다")
    features = payload["feature_set"]
    if features.get("features") != ["reversal_5"]:
        raise ValueError("Phase 5 입력 Feature는 reversal_5 하나로 고정됩니다")
    target = payload["target"]
    if (target.get("entry_offset_sessions"), target.get("exit_offset_sessions")) != (1, 11):
        raise ValueError("target 시점은 t+1 시가 진입, t+11 시가 청산으로 고정됩니다")

    periods = {name: _period(name, bounds) for name, bounds in payload["periods"].items()}
    expected_periods = {
        "train": (date(2011, 1, 1), date(2018, 12, 31)),
        "validation": (date(2019, 1, 1), date(2021, 12, 31)),
        "development_test": (date(2022, 1, 1), date(2023, 12, 31)),
    }
    if {name: (p.start, p.end) for name, p in periods.items()} != expected_periods:
        raise ValueError("Phase 5 기간이 사전등록 값과 다릅니다")
    folds = tuple(
        Fold(
            str(item["fold"]),
            _period(f"{item['fold']}_train", item["train"]),
            _period(f"{item['fold']}_validation", item["validation"]),
        )
        for item in payload["folds"]
    )
    expected_folds = ((2018, 2019), (2019, 2020), (2020, 2021))
    if tuple((fold.train.end.year, fold.validation.start.year) for fold in folds) != expected_folds:
        raise ValueError("anchored annual fold가 사전등록 값과 다릅니다")

    candidates = tuple(payload["models"]["candidate_order"])
    trees = payload["models"]["trees"]
    if candidates != EXPECTED_CANDIDATES:
        raise ValueError("모델 후보 또는 고정 순서가 변경되었습니다")
    if trees.get("max_depth") != [1, 2, 3] or trees.get("min_samples_leaf") != [0.02, 0.05]:
        raise ValueError("shallow tree 후보군이 변경되었습니다")
    if int(payload["purge_sessions"]) != 20 or int(payload["embargo_sessions"]) != 20:
        raise ValueError("purge와 embargo는 각각 20 세션으로 고정됩니다")

    portfolio = payload["portfolio"]
    if (
        int(portfolio["holding_sessions"]),
        int(portfolio["maximum_holdings"]),
        Decimal(portfolio["target_weight"]),
        bool(portfolio["allow_pyramiding"]),
    ) != (20, 10, Decimal("0.10"), False):
        raise ValueError("Phase 3 비교 포트폴리오 조건이 변경되었습니다")
    costs = payload["costs"]
    if tuple(int(v) for v in costs["stress_multipliers"]) != (1, 2, 3):
        raise ValueError("비용 stress 배수가 변경되었습니다")
    if payload["selection"].get("partition") != "validation_only":
        raise PermissionError("후보 선택에는 Validation만 사용할 수 있습니다")

    return RankingConfig(
        path=path,
        payload=payload,
        experiment_id=str(payload["experiment_id"]),
        data_root=root,
        required_partition_role=str(payload["required_partition_role"]),
        maximum_permitted_date=date.fromisoformat(payload["maximum_permitted_date"]),
        periods=periods,
        folds=folds,
        purge_sessions=20,
        embargo_sessions=20,
        minimum_cross_section=int(payload["minimum_cross_section"]),
        candidate_order=candidates,
        initial_cash=Decimal(portfolio["initial_cash_krw"]),
        holding_sessions=20,
        maximum_holdings=10,
        target_weight=Decimal("0.10"),
        entry_gap_cap=Decimal(portfolio["entry_gap_cap"]),
        commission_rate=Decimal(costs["commission_rate_per_side"]),
        slippage_rate=Decimal(costs["slippage_rate_per_side"]),
        stress_multipliers=(1, 2, 3),
        tax_schedule_path=Path(costs["sell_tax_schedule"]),
        random_seed=int(payload["random_seed"]),
    )
