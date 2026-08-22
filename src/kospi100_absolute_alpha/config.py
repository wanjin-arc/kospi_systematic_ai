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


EXPERIMENT_ID = "EXP-20260823-005"
MODEL_CONTRACT = "ridge_a100_plus_logistic_c1_absolute_net_alpha"


@dataclass(frozen=True)
class AbsoluteAlphaConfig:
    path: Path
    payload: Mapping[str, Any]
    base: MultifactorConfig
    experiment_id: str
    ridge_alpha: float
    logistic_c: float
    logistic_max_iter: int
    entry_net_excess: float
    entry_probability: float
    exit_net_excess: float
    exit_probability: float
    maximum_entry_candidates: int
    maximum_holding_sessions: int
    minimum_entry_orders: int
    maximum_mdd_worsening: float

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


def _period(name: str, bounds: list[str]) -> Period:
    return Period(name, date.fromisoformat(bounds[0]), date.fromisoformat(bounds[1]))


def load_config(path: Path) -> AbsoluteAlphaConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != "phase5e-absolute-alpha-v1":
        raise ValueError("지원하지 않는 Phase 5E 설정 버전입니다")
    if payload.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("Phase 5E Experiment ID가 사전등록 값과 다릅니다")
    if payload.get("evaluation_status") != "ADAPTIVE_DIAGNOSTIC_NOT_TEST_OR_OOS":
        raise ValueError("2019~2021 adaptive diagnostic 표기가 필요합니다")
    root = Path(str(payload.get("data_root")))
    parts = {part.lower() for part in root.parts}
    if "sealed" in parts or "development" in parts:
        raise PermissionError("Phase 5E 허용 파티션 밖의 경로입니다")
    if payload.get("required_partition_role") != "phase5_train_validation":
        raise PermissionError("Phase 5E는 Train/Validation 전용 파티션만 허용합니다")
    if payload.get("maximum_permitted_date") != "2021-12-31":
        raise PermissionError("Phase 5E 최대 입력일은 2021-12-31입니다")
    if payload.get("development_test_access") is not False:
        raise PermissionError("Development Test는 승인되지 않았습니다")
    if payload.get("final_oos_access") != "DENIED_UNTIL_PHASE_8":
        raise PermissionError("보호 데이터 봉인 설정이 변경되었습니다")

    contract = payload["feature_contract"]
    if (
        contract.get("feature_set"),
        int(contract.get("stock_features", -1)),
        int(contract.get("regime_features", -1)),
        int(contract.get("interactions", -1)),
        bool(contract.get("market_state_is_model_input_not_hard_capacity")),
    ) != ("phase4b_multifactor_interaction_v1", 21, 5, 6, True):
        raise ValueError("Phase 5E Feature 계약이 변경되었습니다")
    analysis = load_analysis_config(Path(str(contract["phase4b_config"])))

    target = payload["target"]
    if (
        target.get("regression_id"),
        target.get("classification_id"),
        int(target.get("entry_offset_sessions", -1)),
        int(target.get("exit_offset_sessions", -1)),
        float(target.get("binary_threshold", 1.0)),
        target.get("cost_adjustment"),
        target.get("cross_sectional_transform"),
    ) != (
        "forward_10_session_cost_adjusted_excess_open_to_open_log_return",
        "forward_10_session_positive_cost_adjusted_excess",
        1,
        11,
        0.0,
        "base_commission_slippage_and_exit_date_sell_tax",
        "none",
    ):
        raise ValueError("Phase 5E 절대 target 계약이 변경되었습니다")

    models = payload["models"]
    if (
        models.get("regressor"),
        float(models.get("ridge_alpha", -1)),
        models.get("classifier"),
        float(models.get("logistic_c", -1)),
        int(models.get("logistic_max_iter", -1)),
        models.get("class_weight"),
        models.get("model_selection"),
    ) != ("ridge", 100.0, "logistic_regression", 1.0, 5000, None, "none_fixed_dual_model"):
        raise ValueError("Phase 5E 고정 이중 모델 계약이 변경되었습니다")

    policy = payload["no_trade_policy"]
    if (
        float(policy.get("entry_minimum_predicted_net_excess", -1)),
        float(policy.get("entry_minimum_positive_probability", -1)),
        float(policy.get("exit_at_or_below_predicted_net_excess", 1)),
        float(policy.get("exit_below_positive_probability", -1)),
        policy.get("rank_eligible_candidates_by"),
        policy.get("zero_eligible_action"),
        int(policy.get("maximum_entry_candidates_per_day", -1)),
    ) != (0.005, 0.60, 0.0, 0.50, "predicted_net_excess_descending", "hold_cash", 10):
        raise ValueError("Phase 5E no-trade threshold가 변경되었습니다")

    periods = {name: _period(name, bounds) for name, bounds in payload["periods"].items()}
    if {name: (value.start, value.end) for name, value in periods.items()} != {
        "train": (date(2011, 1, 1), date(2018, 12, 31)),
        "adaptive_diagnostic": (date(2019, 1, 1), date(2021, 12, 31)),
    }:
        raise ValueError("Phase 5E 기간이 변경되었습니다")
    folds = tuple(
        Fold(
            str(item["fold"]),
            _period(f"{item['fold']}_train", item["train"]),
            _period(f"{item['fold']}_validation", item["validation"]),
        )
        for item in payload["folds"]
    )
    if tuple((fold.train.end.year, fold.validation.start.year) for fold in folds) != (
        (2018, 2019), (2019, 2020), (2020, 2021)
    ):
        raise ValueError("Phase 5E anchored fold가 변경되었습니다")

    portfolio = payload["portfolio"]
    if (
        int(portfolio.get("maximum_holdings", -1)),
        int(portfolio.get("required_minimum_holdings", -1)),
        Decimal(str(portfolio.get("target_weight"))),
        int(portfolio.get("maximum_holding_sessions", -1)),
        bool(portfolio.get("allow_pyramiding")),
        portfolio.get("unallocated_cash"),
    ) != (10, 0, Decimal("0.10"), 10, False, "retain_without_penalty"):
        raise ValueError("Phase 5E 포트폴리오 계약이 변경되었습니다")
    gate = payload["diagnostic_gate"]
    if (
        float(gate.get("required_connected_net_excess_return", -1)),
        float(gate.get("required_cost_2x_net_excess_return", -1)),
        int(gate.get("minimum_entry_orders", -1)),
        float(gate.get("maximum_mdd_worsening_percentage_points", -1)),
        bool(gate.get("annual_positive_ratio_is_hard_gate")),
        bool(gate.get("average_cash_is_hard_gate")),
        bool(gate.get("promotion_allowed_from_this_run")),
        int(gate.get("development_test_runs", -1)),
    ) != (0.0, 0.0, 100, 5.0, False, False, False, 0):
        raise ValueError("Phase 5E diagnostic gate가 변경되었습니다")
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
        candidate_order=(MODEL_CONTRACT,),
        initial_cash=Decimal(portfolio["initial_cash_krw"]),
        holding_sessions=10,
        maximum_holdings=10,
        target_weight=Decimal(portfolio["target_weight"]),
        entry_gap_cap=Decimal(portfolio["entry_gap_cap"]),
        commission_rate=Decimal(costs["commission_rate_per_side"]),
        slippage_rate=Decimal(costs["slippage_rate_per_side"]),
        stress_multipliers=(1, 2, 3),
        tax_schedule_path=Path(costs["sell_tax_schedule"]),
        random_seed=int(payload["random_seed"]),
    )
    return AbsoluteAlphaConfig(
        path=path,
        payload=payload,
        base=base,
        experiment_id=EXPERIMENT_ID,
        ridge_alpha=100.0,
        logistic_c=1.0,
        logistic_max_iter=5000,
        entry_net_excess=0.005,
        entry_probability=0.60,
        exit_net_excess=0.0,
        exit_probability=0.50,
        maximum_entry_candidates=10,
        maximum_holding_sessions=10,
        minimum_entry_orders=100,
        maximum_mdd_worsening=0.05,
    )
