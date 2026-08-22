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


EXPERIMENT_ID = "EXP-20260823-007"
MODEL_CONTRACT = "extra_trees_multioutput_5_10_20_consensus"
HORIZONS = (5, 10, 20)


@dataclass(frozen=True)
class MultiHorizonConfig:
    path: Path
    payload: Mapping[str, Any]
    base: MultifactorConfig
    experiment_id: str
    horizons: tuple[int, ...]
    n_estimators: int
    max_depth: int
    min_samples_leaf: int
    max_features: float
    minimum_positive_horizons: int
    entry_median_net_excess: float
    exit_positive_horizons: int
    exit_median_net_excess: float
    maximum_entry_candidates: int
    maximum_holding_sessions: int
    minimum_entry_orders: int
    maximum_mdd_worsening: float
    required_nonnegative_folds: int

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


def _period(name: str, bounds: list[str]) -> Period:
    return Period(name, date.fromisoformat(bounds[0]), date.fromisoformat(bounds[1]))


def load_config(path: Path) -> MultiHorizonConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != "phase5g-multihorizon-consensus-v1":
        raise ValueError("지원하지 않는 Phase 5G 설정 버전입니다")
    if payload.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("Phase 5G Experiment ID가 사전등록 값과 다릅니다")
    if payload.get("evaluation_status") != "TRAIN_INTERNAL_DIAGNOSTIC_ONLY":
        raise ValueError("Phase 5G는 Train 내부 진단으로만 실행할 수 있습니다")
    root = Path(str(payload["data_root"]))
    forbidden = {part.lower() for part in root.parts}
    if "sealed" in forbidden or "development" in forbidden:
        raise PermissionError("Phase 5G 허용 파티션 밖의 경로입니다")
    if payload.get("required_partition_role") != "phase4b_train_internal":
        raise PermissionError("2018년 이하 물리 파티션만 허용합니다")
    if payload.get("maximum_permitted_date") != "2018-12-31":
        raise PermissionError("Phase 5G 최대 입력일은 2018-12-31입니다")
    if payload.get("development_test_access") is not False:
        raise PermissionError("Development Test 접근은 승인되지 않았습니다")
    if payload.get("final_oos_access") != "DENIED_UNTIL_PHASE_8":
        raise PermissionError("보호 데이터 봉인 설정이 변경되었습니다")

    analysis = load_analysis_config(Path(str(payload["feature_contract"]["phase4b_config"])))
    contract = payload["feature_contract"]
    if (
        contract.get("use_all_21_stock_features") is not True
        or contract.get("use_all_5_regime_features") is not True
        or contract.get("use_all_6_interactions") is not True
        or contract.get("stock_transform") != "daily_cross_sectional_average_percentile_rank"
        or contract.get("minute_data_used") is not False
    ):
        raise ValueError("Phase 5G Feature 계약이 변경되었습니다")
    target = payload["target"]
    if (
        target.get("id"), tuple(target.get("horizons", ())),
        target.get("entry_offset_sessions"), tuple(target.get("exit_offsets_sessions", ())),
        target.get("cost_adjustment"), target.get("cross_sectional_transform"),
    ) != (
        "multihorizon_cost_adjusted_excess_open_to_open_log_return", HORIZONS,
        1, (6, 11, 21), "base_commission_slippage_and_exit_date_sell_tax", "none",
    ):
        raise ValueError("Phase 5G target 계약이 변경되었습니다")
    model = payload["model"]
    if (
        model.get("family"), model.get("n_estimators"), model.get("max_depth"),
        model.get("min_samples_leaf"), model.get("max_features"), model.get("bootstrap"),
        model.get("n_jobs"), model.get("model_selection"),
    ) != (
        "extra_trees_multioutput_regressor", 300, 6, 500, 0.5, False, 1,
        "none_single_fixed_model",
    ):
        raise ValueError("Phase 5G 모델 계약이 변경되었습니다")
    policy = payload["consensus_policy"]
    if (
        policy.get("minimum_positive_horizons"), policy.get("entry_minimum_median_net_excess"),
        policy.get("exit_at_or_below_positive_horizons"),
        policy.get("exit_at_or_below_median_net_excess"), policy.get("rank_by"),
        policy.get("maximum_entry_candidates_per_day"), policy.get("zero_eligible_action"),
    ) != (2, 0.002, 1, 0.0, "predicted_median_net_excess_descending", 10, "hold_cash"):
        raise ValueError("Phase 5G 합의 정책이 변경되었습니다")
    portfolio = payload["portfolio"]
    if (
        portfolio.get("maximum_holdings"), portfolio.get("required_minimum_holdings"),
        Decimal(str(portfolio.get("target_weight"))), portfolio.get("maximum_holding_sessions"),
        portfolio.get("allow_pyramiding"), portfolio.get("unallocated_cash"),
    ) != (10, 0, Decimal("0.10"), 20, False, "retain_without_penalty"):
        raise ValueError("Phase 5G 포트폴리오 계약이 변경되었습니다")
    gate = payload["internal_gate"]
    if (
        gate.get("required_connected_net_excess_return"), gate.get("required_cost_2x_net_excess_return"),
        gate.get("required_nonnegative_annual_folds"), gate.get("minimum_entry_orders"),
        gate.get("maximum_mdd_worsening_percentage_points"),
        gate.get("promotion_allowed_from_this_run"), gate.get("development_test_runs"),
    ) != (0.0, 0.0, 4, 100, 5.0, False, 0):
        raise ValueError("Phase 5G 내부 gate가 변경되었습니다")
    if payload.get("period") != ["2011-01-01", "2018-12-31"]:
        raise ValueError("Phase 5G 연구기간이 변경되었습니다")
    folds = tuple(
        Fold(str(item["fold"]), _period(f"{item['fold']}_train", item["train"]),
             _period(f"{item['fold']}_validation", item["validation"]))
        for item in payload["folds"]
    )
    if tuple((fold.train.end.year, fold.validation.start.year) for fold in folds) != (
        (2014, 2015), (2015, 2016), (2016, 2017), (2017, 2018)
    ):
        raise ValueError("Phase 5G anchored fold가 변경되었습니다")
    if payload.get("purge_sessions") != 20 or payload.get("embargo_sessions") != 20:
        raise ValueError("purge와 embargo는 각각 20거래일이어야 합니다")
    costs = payload["costs"]
    if tuple(costs.get("stress_multipliers", ())) != (1, 2, 3):
        raise ValueError("비용 stress 배수가 변경되었습니다")

    periods = {"research": Period("research", date(2011, 1, 1), date(2018, 12, 31))}
    base = MultifactorConfig(
        path=path, payload=payload, experiment_id=EXPERIMENT_ID, data_root=root,
        required_partition_role="phase4b_train_internal", maximum_permitted_date=date(2018, 12, 31),
        periods=periods, folds=folds, stock_features=analysis.stock_features,
        regime_features=analysis.regime_features, interactions=analysis.interactions,
        purge_sessions=20, embargo_sessions=20,
        minimum_cross_section=int(payload["minimum_cross_section"]),
        candidate_order=(MODEL_CONTRACT,), initial_cash=Decimal(portfolio["initial_cash_krw"]),
        holding_sessions=20, maximum_holdings=10, target_weight=Decimal(portfolio["target_weight"]),
        entry_gap_cap=Decimal(portfolio["entry_gap_cap"]),
        commission_rate=Decimal(costs["commission_rate_per_side"]),
        slippage_rate=Decimal(costs["slippage_rate_per_side"]),
        stress_multipliers=(1, 2, 3), tax_schedule_path=Path(costs["sell_tax_schedule"]),
        random_seed=int(payload["random_seed"]),
    )
    return MultiHorizonConfig(
        path, payload, base, EXPERIMENT_ID, HORIZONS, 300, 6, 500, 0.5,
        2, 0.002, 1, 0.0, 10, 20, 100, 0.05, 4,
    )
