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


EXPERIMENT_ID = "EXP-20260823-006"
MODEL_CONTRACT = "histgb_mean_median_temporal_path_plus_train_isolation_forest"


@dataclass(frozen=True)
class TemporalRiskConfig:
    path: Path
    payload: Mapping[str, Any]
    base: MultifactorConfig
    experiment_id: str
    stock_features: tuple[str, ...]
    regime_features: tuple[str, ...]
    temporal_sessions: int
    learning_rate: float
    max_iter: int
    max_depth: int
    min_samples_leaf: int
    l2_regularization: float
    anomaly_estimators: int
    anomaly_max_samples: int
    anomaly_quantile: float
    entry_net_excess: float
    entry_median_net_excess: float
    exit_net_excess: float
    exit_median_net_excess: float
    maximum_entry_candidates: int
    maximum_holding_sessions: int
    minimum_entry_orders: int
    maximum_mdd_worsening: float

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


def _period(name: str, bounds: list[str]) -> Period:
    return Period(name, date.fromisoformat(bounds[0]), date.fromisoformat(bounds[1]))


def load_config(path: Path) -> TemporalRiskConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != "phase5f-temporal-risk-v1":
        raise ValueError("지원하지 않는 Phase 5F 설정 버전입니다")
    if payload.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("Phase 5F Experiment ID가 사전등록 값과 다릅니다")
    if payload.get("evaluation_status") != "ADAPTIVE_DIAGNOSTIC_NOT_TEST_OR_OOS":
        raise ValueError("2019~2021 adaptive diagnostic 표기가 필요합니다")
    root = Path(str(payload.get("data_root")))
    parts = {part.lower() for part in root.parts}
    if "sealed" in parts or "development" in parts:
        raise PermissionError("Phase 5F 허용 파티션 밖의 경로입니다")
    if payload.get("required_partition_role") != "phase5_train_validation":
        raise PermissionError("Phase 5F는 Train/Validation 전용 파티션만 허용합니다")
    if payload.get("maximum_permitted_date") != "2021-12-31":
        raise PermissionError("Phase 5F 최대 입력일은 2021-12-31입니다")
    if payload.get("development_test_access") is not False:
        raise PermissionError("Development Test는 승인되지 않았습니다")
    if payload.get("final_oos_access") != "DENIED_UNTIL_PHASE_8":
        raise PermissionError("보호 데이터 봉인 설정이 변경되었습니다")

    contract = payload["feature_contract"]
    expected_stock = (
        "reversal_5", "excess_momentum_20", "excess_momentum_63",
        "trend_close_sma20", "trend_close_sma60", "trend_close_sma200",
        "low_volatility_20", "volume_confirmation_5_20",
    )
    expected_regime = (
        "index_trend_200", "index_momentum_63", "index_low_volatility_20",
        "breadth_above_sma200", "breadth_positive_momentum20",
    )
    if tuple(contract.get("base_stock_features", ())) != expected_stock:
        raise ValueError("Phase 5F 종목 Feature 계약이 변경되었습니다")
    if tuple(contract.get("base_regime_features", ())) != expected_regime:
        raise ValueError("Phase 5F 시장 Feature 계약이 변경되었습니다")
    if tuple(contract.get("stock_temporal_transforms", ())) != (
        "level", "delta_5", "mean_20", "std_20", "persistence_20"
    ):
        raise ValueError("Phase 5F 종목 시계열 변환이 변경되었습니다")
    if tuple(contract.get("regime_temporal_transforms", ())) != ("level", "delta_5", "std_20"):
        raise ValueError("Phase 5F 시장 시계열 변환이 변경되었습니다")
    if (
        int(contract.get("minimum_temporal_sessions", -1)) != 20
        or contract.get("membership_and_session_gap_reset") is not True
        or contract.get("minute_data_used") is not False
    ):
        raise ValueError("Phase 5F 시계열 경계 계약이 변경되었습니다")
    analysis = load_analysis_config(Path(str(contract["phase4b_config"])))
    if not set(expected_stock).issubset(analysis.stock_features) or tuple(analysis.regime_features) != expected_regime:
        raise ValueError("Phase 4B canonical Feature와 Phase 5F 계약이 일치하지 않습니다")

    target = payload["target"]
    if (
        target.get("mean_regression_id"), target.get("robust_regression_id"),
        int(target.get("entry_offset_sessions", -1)), int(target.get("exit_offset_sessions", -1)),
        target.get("cost_adjustment"), target.get("cross_sectional_transform"),
    ) != (
        "forward_10_session_cost_adjusted_excess_open_to_open_log_return",
        "forward_10_session_cost_adjusted_excess_conditional_median",
        1, 11, "base_commission_slippage_and_exit_date_sell_tax", "none",
    ):
        raise ValueError("Phase 5F target 계약이 변경되었습니다")

    models = payload["models"]
    if (
        models.get("mean_regressor"), models.get("median_regressor"),
        float(models.get("learning_rate", -1)), int(models.get("max_iter", -1)),
        int(models.get("max_depth", -1)), int(models.get("min_samples_leaf", -1)),
        float(models.get("l2_regularization", -1)), models.get("early_stopping"),
        models.get("model_selection"),
    ) != (
        "hist_gradient_boosting_squared_error", "hist_gradient_boosting_quantile_0.50",
        0.03, 120, 2, 500, 10.0, False, "none_fixed_dual_regression",
    ):
        raise ValueError("Phase 5F 고정 이중 회귀 계약이 변경되었습니다")
    anomaly = payload["anomaly_veto"]
    if (
        anomaly.get("model"), int(anomaly.get("n_estimators", -1)),
        int(anomaly.get("max_samples", -1)), anomaly.get("contamination"),
        anomaly.get("threshold_source"), float(anomaly.get("threshold_quantile", -1)),
        anomaly.get("fit_scope"), anomaly.get("validation_or_event_labels_used"),
    ) != (
        "isolation_forest", 200, 256, "auto", "train_score_samples_quantile",
        0.05, "fold_train_unique_dates_only", False,
    ):
        raise ValueError("Phase 5F 시장 이상상태 계약이 변경되었습니다")

    policy = payload["no_trade_policy"]
    if (
        float(policy.get("entry_minimum_predicted_mean_net_excess", -1)),
        float(policy.get("entry_minimum_predicted_median_net_excess", -1)),
        policy.get("entry_requires_non_anomalous_market"),
        float(policy.get("exit_at_or_below_predicted_mean_net_excess", 1)),
        float(policy.get("exit_at_or_below_predicted_median_net_excess", 1)),
        policy.get("exit_on_market_anomaly"), policy.get("rank_eligible_candidates_by"),
        policy.get("zero_eligible_action"), int(policy.get("maximum_entry_candidates_per_day", -1)),
    ) != (0.003, 0.0, True, 0.0, 0.0, True, "predicted_mean_net_excess_descending", "hold_cash", 10):
        raise ValueError("Phase 5F no-trade 계약이 변경되었습니다")

    periods = {name: _period(name, bounds) for name, bounds in payload["periods"].items()}
    if {name: (value.start, value.end) for name, value in periods.items()} != {
        "train": (date(2011, 1, 1), date(2018, 12, 31)),
        "adaptive_diagnostic": (date(2019, 1, 1), date(2021, 12, 31)),
    }:
        raise ValueError("Phase 5F 기간이 변경되었습니다")
    folds = tuple(
        Fold(str(item["fold"]), _period(f"{item['fold']}_train", item["train"]),
             _period(f"{item['fold']}_validation", item["validation"]))
        for item in payload["folds"]
    )
    if tuple((fold.train.end.year, fold.validation.start.year) for fold in folds) != (
        (2018, 2019), (2019, 2020), (2020, 2021)
    ):
        raise ValueError("Phase 5F anchored fold가 변경되었습니다")

    portfolio = payload["portfolio"]
    if (
        int(portfolio.get("maximum_holdings", -1)), int(portfolio.get("required_minimum_holdings", -1)),
        Decimal(str(portfolio.get("target_weight"))), int(portfolio.get("maximum_holding_sessions", -1)),
        bool(portfolio.get("allow_pyramiding")), portfolio.get("unallocated_cash"),
    ) != (10, 0, Decimal("0.10"), 10, False, "retain_without_penalty"):
        raise ValueError("Phase 5F 포트폴리오 계약이 변경되었습니다")
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
        raise ValueError("Phase 5F diagnostic gate가 변경되었습니다")
    if int(payload.get("purge_sessions", -1)) != 20 or int(payload.get("embargo_sessions", -1)) != 20:
        raise ValueError("purge와 embargo는 각각 20 세션이어야 합니다")
    if tuple(int(value) for value in payload["costs"]["stress_multipliers"]) != (1, 2, 3):
        raise ValueError("비용 stress 배수가 변경되었습니다")

    base = MultifactorConfig(
        path=path, payload=payload, experiment_id=EXPERIMENT_ID, data_root=root,
        required_partition_role="phase5_train_validation", maximum_permitted_date=date(2021, 12, 31),
        periods=periods, folds=folds, stock_features=expected_stock, regime_features=expected_regime,
        interactions=(), purge_sessions=20, embargo_sessions=20,
        minimum_cross_section=int(payload["minimum_cross_section"]), candidate_order=(MODEL_CONTRACT,),
        initial_cash=Decimal(portfolio["initial_cash_krw"]), holding_sessions=10,
        maximum_holdings=10, target_weight=Decimal(portfolio["target_weight"]),
        entry_gap_cap=Decimal(portfolio["entry_gap_cap"]),
        commission_rate=Decimal(payload["costs"]["commission_rate_per_side"]),
        slippage_rate=Decimal(payload["costs"]["slippage_rate_per_side"]),
        stress_multipliers=(1, 2, 3), tax_schedule_path=Path(payload["costs"]["sell_tax_schedule"]),
        random_seed=int(payload["random_seed"]),
    )
    return TemporalRiskConfig(
        path=path, payload=payload, base=base, experiment_id=EXPERIMENT_ID,
        stock_features=expected_stock, regime_features=expected_regime, temporal_sessions=20,
        learning_rate=0.03, max_iter=120, max_depth=2, min_samples_leaf=500,
        l2_regularization=10.0, anomaly_estimators=200, anomaly_max_samples=256,
        anomaly_quantile=0.05, entry_net_excess=0.003, entry_median_net_excess=0.0,
        exit_net_excess=0.0, exit_median_net_excess=0.0, maximum_entry_candidates=10,
        maximum_holding_sessions=10, minimum_entry_orders=100, maximum_mdd_worsening=0.05,
    )
