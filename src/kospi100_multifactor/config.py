from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from kospi100_ranking.config import Fold, Period


ANALYSIS_EXPERIMENT_ID = "EXP-20260823-001"
SELECTION_EXPERIMENT_ID = "EXP-20260823-002"
STOCK_FEATURES = (
    "reversal_5",
    "momentum_20",
    "momentum_63",
    "momentum_126",
    "momentum_252",
    "excess_momentum_20",
    "excess_momentum_63",
    "excess_momentum_126",
    "trend_close_sma20",
    "trend_close_sma60",
    "trend_close_sma200",
    "trend_sma20_sma60",
    "high_proximity_252",
    "low_volatility_20",
    "low_downside_volatility_20",
    "low_atr_20",
    "risk_adjusted_momentum_63",
    "volume_confirmation_5_20",
    "trading_value_confirmation_5_20",
    "liquidity_20",
    "low_illiquidity_20",
)
REGIME_FEATURES = (
    "index_trend_200",
    "index_momentum_63",
    "index_low_volatility_20",
    "breadth_above_sma200",
    "breadth_positive_momentum20",
)
INTERACTIONS = (
    ("reversal_5", "index_trend_200"),
    ("reversal_5", "breadth_above_sma200"),
    ("excess_momentum_63", "index_trend_200"),
    ("trend_close_sma200", "breadth_above_sma200"),
    ("low_volatility_20", "index_low_volatility_20"),
    ("volume_confirmation_5_20", "breadth_positive_momentum20"),
)
CANDIDATES = (
    "equal_weight_rank",
    "ridge_a1",
    "ridge_a100",
    "elastic_a005_l02",
    "histgb_d2_l200",
    "histgb_d3_l200",
    "blend_ridge_histgb",
)


@dataclass(frozen=True)
class MultifactorConfig:
    path: Path
    payload: Mapping[str, Any]
    experiment_id: str
    data_root: Path
    required_partition_role: str
    maximum_permitted_date: date
    periods: Mapping[str, Period]
    folds: tuple[Fold, ...]
    stock_features: tuple[str, ...]
    regime_features: tuple[str, ...]
    interactions: tuple[tuple[str, str], ...]
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

    @property
    def phase4b_config_hash(self) -> str:
        source = Path(str(self.payload.get("phase4b_config", self.path)))
        return hashlib.sha256(source.read_bytes()).hexdigest()


def _forbidden_path(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return "sealed" in parts or "final_oos_v24" in parts or "development" in parts


def _period(name: str, bounds: list[str]) -> Period:
    return Period(name, date.fromisoformat(bounds[0]), date.fromisoformat(bounds[1]))


def _folds(items: list[dict[str, object]]) -> tuple[Fold, ...]:
    return tuple(
        Fold(
            str(item["fold"]),
            _period(f"{item['fold']}_train", item["train"]),  # type: ignore[arg-type]
            _period(f"{item['fold']}_validation", item["validation"]),  # type: ignore[arg-type]
        )
        for item in items
    )


def _validate_common(payload: Mapping[str, Any]) -> tuple[Path, tuple[Fold, ...]]:
    root = Path(str(payload["data_root"]))
    if _forbidden_path(root):
        raise PermissionError("Phase 4B/5B는 허용된 2018년 이하 연구 파티션만 읽을 수 있습니다")
    if payload.get("required_partition_role") != "phase4b_train_internal":
        raise PermissionError("Phase 4B/5B 파티션 역할이 사전등록 값과 다릅니다")
    if payload.get("maximum_permitted_date") != "2018-12-31":
        raise PermissionError("Phase 4B/5B 최대 입력일은 2018-12-31입니다")
    if payload.get("development_test_access") is not False:
        raise PermissionError("Development Test는 승인되지 않았습니다")
    if payload.get("final_oos_access") != "DENIED_UNTIL_PHASE_8":
        raise PermissionError("Final OOS 봉인 설정이 변경되었습니다")
    target = payload["target"]
    if (
        target.get("id"),
        target.get("entry_offset_sessions"),
        target.get("exit_offset_sessions"),
        target.get("cross_sectional_transform"),
    ) != (
        "forward_10_session_excess_open_to_open_rank",
        1,
        11,
        "percentile_rank_average",
    ):
        raise ValueError("Phase 4B/5B target 계약이 변경되었습니다")
    if int(payload["purge_sessions"]) != 20 or int(payload["embargo_sessions"]) != 20:
        raise ValueError("purge와 embargo는 각각 20 세션이어야 합니다")
    folds = _folds(list(payload["internal_folds"]))
    expected = ((2014, 2015), (2015, 2016), (2016, 2017), (2017, 2018))
    if tuple((fold.train.end.year, fold.validation.start.year) for fold in folds) != expected:
        raise ValueError("2011~2018 Train 내부 anchored fold가 변경되었습니다")
    return root, folds


def load_analysis_config(path: Path) -> MultifactorConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != "phase4b-multifactor-v1":
        raise ValueError("지원하지 않는 Phase 4B 설정 버전입니다")
    if payload.get("experiment_id") != ANALYSIS_EXPERIMENT_ID:
        raise ValueError("Phase 4B Experiment ID가 사전등록 값과 다릅니다")
    if payload.get("research_period") != ["2011-01-01", "2018-12-31"]:
        raise ValueError("Phase 4B 연구기간이 변경되었습니다")
    if tuple(payload.get("stock_features", ())) != STOCK_FEATURES:
        raise ValueError("Phase 4B 종목 Feature 21개 또는 순서가 변경되었습니다")
    if tuple(payload.get("regime_features", ())) != REGIME_FEATURES:
        raise ValueError("Phase 4B 시장상태 Feature 5개 또는 순서가 변경되었습니다")
    interactions = tuple(tuple(value) for value in payload.get("interactions", ()))
    if interactions != INTERACTIONS:
        raise ValueError("Phase 4B 상호작용 6개 또는 순서가 변경되었습니다")
    root, folds = _validate_common(payload)
    periods = {"research": _period("research", payload["research_period"])}
    return MultifactorConfig(
        path=path,
        payload=payload,
        experiment_id=ANALYSIS_EXPERIMENT_ID,
        data_root=root,
        required_partition_role="phase4b_train_internal",
        maximum_permitted_date=date(2018, 12, 31),
        periods=periods,
        folds=folds,
        stock_features=STOCK_FEATURES,
        regime_features=REGIME_FEATURES,
        interactions=INTERACTIONS,
        purge_sessions=20,
        embargo_sessions=20,
        minimum_cross_section=int(payload["minimum_cross_section"]),
        candidate_order=(),
        initial_cash=Decimal("5000000"),
        holding_sessions=10,
        maximum_holdings=10,
        target_weight=Decimal("0.10"),
        entry_gap_cap=Decimal("0.05"),
        commission_rate=Decimal("0.0002"),
        slippage_rate=Decimal("0.0010"),
        stress_multipliers=(1, 2, 3),
        tax_schedule_path=Path("configs/kospi_sell_cost_schedule.csv"),
        random_seed=int(payload["random_seed"]),
    )


def load_selection_config(path: Path) -> MultifactorConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != "phase5b-multifactor-ranking-v1":
        raise ValueError("지원하지 않는 Phase 5B 설정 버전입니다")
    if payload.get("experiment_id") != SELECTION_EXPERIMENT_ID:
        raise ValueError("Phase 5B Experiment ID가 사전등록 값과 다릅니다")
    if payload.get("phase4b_experiment_id") != ANALYSIS_EXPERIMENT_ID:
        raise ValueError("Phase 4B 인계 Experiment ID가 다릅니다")
    analysis = load_analysis_config(Path(str(payload["phase4b_config"])))
    payload = dict(payload)
    payload["internal_folds"] = [
        {
            "fold": fold.name,
            "train": [fold.train.start.isoformat(), fold.train.end.isoformat()],
            "validation": [fold.validation.start.isoformat(), fold.validation.end.isoformat()],
        }
        for fold in analysis.folds
    ]
    root, folds = _validate_common(payload)
    models = payload["models"]
    if tuple(models.get("candidate_order", ())) != CANDIDATES:
        raise ValueError("Phase 5B 모델 후보 또는 순서가 변경되었습니다")
    if models.get("ridge_alpha") != [1.0, 100.0]:
        raise ValueError("Ridge 후보가 변경되었습니다")
    if models.get("elastic_net") != {
        "alpha": 0.005,
        "l1_ratio": 0.2,
        "max_iter": 10000,
        "tol": 0.00002,
    }:
        raise ValueError("ElasticNet 후보가 변경되었습니다")
    portfolio = payload["portfolio"]
    if (
        int(portfolio["holding_sessions"]),
        int(portfolio["maximum_holdings"]),
        Decimal(str(portfolio["target_weight"])),
        bool(portfolio["allow_pyramiding"]),
    ) != (10, 10, Decimal("0.10"), False):
        raise ValueError("Phase 5B 일별 ranking 포트폴리오 계약이 변경되었습니다")
    selection = payload["selection"]
    if (
        selection.get("partition"),
        int(selection.get("required_nonnegative_annual_excess_folds", -1)),
        float(selection.get("required_connected_net_excess_return", -1)),
        selection.get("if_no_candidate_passes"),
        int(selection.get("development_test_runs", -1)),
    ) != (
        "2015_2018_internal_validation_only",
        4,
        0.0,
        "reject_all_and_record_diagnostic_best",
        0,
    ):
        raise ValueError("Phase 5B 선택 gate가 변경되었습니다")
    costs = payload["costs"]
    if tuple(int(value) for value in costs["stress_multipliers"]) != (1, 2, 3):
        raise ValueError("비용 stress 배수가 변경되었습니다")
    return MultifactorConfig(
        path=path,
        payload=payload,
        experiment_id=SELECTION_EXPERIMENT_ID,
        data_root=root,
        required_partition_role="phase4b_train_internal",
        maximum_permitted_date=date(2018, 12, 31),
        periods=analysis.periods,
        folds=folds,
        stock_features=analysis.stock_features,
        regime_features=analysis.regime_features,
        interactions=analysis.interactions,
        purge_sessions=20,
        embargo_sessions=20,
        minimum_cross_section=int(payload["minimum_cross_section"]),
        candidate_order=CANDIDATES,
        initial_cash=Decimal(portfolio["initial_cash_krw"]),
        holding_sessions=10,
        maximum_holdings=10,
        target_weight=Decimal("0.10"),
        entry_gap_cap=Decimal(portfolio["entry_gap_cap"]),
        commission_rate=Decimal(costs["commission_rate_per_side"]),
        slippage_rate=Decimal(costs["slippage_rate_per_side"]),
        stress_multipliers=(1, 2, 3),
        tax_schedule_path=Path(costs["sell_tax_schedule"]),
        random_seed=int(payload["random_seed"]),
    )
