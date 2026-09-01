"""v2 Phase 5R predict-only 포트폴리오 설정과 보호 경계."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "v2-phase5r-frozen-model-portfolio-v2"
EXPERIMENT_ID = "EXP-20260901-002"
PHASE4E_EXPERIMENT_ID = "EXP-20260901-001"
MAXIMUM_PERMITTED_DATE = date(2023, 12, 28)
FORBIDDEN_PATH_PARTS = frozenset({"sealed", "final_oos_v24"})
FUNDAMENTAL_FEATURES = (
    "roe", "roa", "operating_margin", "net_margin", "cfo_to_assets",
    "earnings_yield", "book_to_market", "sales_to_market_cap", "cfo_yield", "free_cash_flow_yield",
    "debt_to_equity", "liabilities_to_assets", "current_ratio", "cash_to_assets", "equity_ratio",
    "revenue_growth_yoy", "operating_income_growth_yoy", "net_income_growth_yoy", "assets_growth_yoy",
    "equity_growth_yoy",
)
TECHNICAL_FEATURES = (
    "return_1", "return_5", "return_20", "return_60", "volatility_5", "volatility_20",
    "downside_volatility_20", "close_to_ma20", "close_to_ma60", "drawdown_20", "drawdown_60",
    "intraday_range", "volume_ratio_20", "gap_1", "index_return_20", "index_trend_60",
    "index_volatility_20",
)
PENDING_HASH = "PHASE4E_OUTPUT_PENDING"


@dataclass(frozen=True)
class ExcludedSecurity:
    security_id: str
    ticker: str
    audit_name: str


@dataclass(frozen=True)
class Phase5RConfig:
    path: Path
    payload: Mapping[str, Any]
    experiment_id: str
    phase4e_experiment_id: str
    phase4e_bundle: Path
    phase4e_manifest: Path
    phase4e_manifest_sha256: str
    phase4e_artifact_tree_sha256: str
    phase4e_bundle_sha256: str
    phase4e_model_hash: str
    membership_root: Path
    market_roots: tuple[Path, ...]
    fundamental_panel: Path
    index_file: Path
    corporate_action_file: Path
    engine_config: Path
    cost_schedule: Path
    data_start: date
    evaluation_start: date
    fundamental_start: date
    data_end: date
    target_horizon_sessions: int
    sample_every_sessions: int
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

    @property
    def phase4_hashes_resolved(self) -> bool:
        return all(
            value != PENDING_HASH and len(value) == 64
            for value in (
                self.phase4e_manifest_sha256,
                self.phase4e_artifact_tree_sha256,
                self.phase4e_bundle_sha256,
                self.phase4e_model_hash,
            )
        )


def _path_parts(path: Path) -> set[str]:
    return {part.casefold() for part in path.parts}


def guard_path(path: Path) -> Path:
    candidate = Path(path)
    forbidden = FORBIDDEN_PATH_PARTS.intersection(
        _path_parts(candidate) | _path_parts(candidate.resolve(strict=False))
    )
    if forbidden:
        raise PermissionError(f"금지된 protected OOS 경로입니다: {candidate}")
    return candidate


def _equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise ValueError(f"Phase 5R 동결 계약 변경: {label}")


def _path(payload: Mapping[str, Any], key: str) -> Path:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Phase 5R 경로 누락: {key}")
    return guard_path(Path(value))


def load_config(path: Path, *, require_resolved_phase4_hashes: bool = False) -> Phase5RConfig:
    path = guard_path(Path(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    _equal(payload.get("schema_version"), SCHEMA_VERSION, "schema_version")
    _equal(payload.get("experiment_id"), EXPERIMENT_ID, "experiment_id")
    _equal(payload.get("phase4e_experiment_id"), PHASE4E_EXPERIMENT_ID, "phase4e_experiment_id")
    _equal(payload.get("data_start"), "2004-01-02", "data_start")
    _equal(payload.get("evaluation_start"), "2021-01-04", "evaluation_start")
    _equal(payload.get("fundamental_start"), "2016-03-24", "fundamental_start")
    _equal(payload.get("data_end"), MAXIMUM_PERMITTED_DATE.isoformat(), "data_end")
    _equal(int(payload.get("target_horizon_sessions", -1)), 20, "target_horizon_sessions")
    _equal(int(payload.get("sample_every_sessions", -1)), 20, "sample_every_sessions")
    if payload.get("fit_allowed") is not False:
        raise PermissionError("Phase 5R에서 fit·재학습은 금지됩니다.")
    if payload.get("development_backtest_approved") is not True:
        raise PermissionError("Phase 5R 소비 개발 백테스트 승인이 없습니다.")
    for key in ("external_portfolio_execution_approved", "network_order_submission", "final_oos_access"):
        if payload.get(key) is not False:
            raise PermissionError(f"Phase 5R 금지 플래그가 변경됐습니다: {key}")

    raw_exclusions = payload.get("excluded_securities")
    if not isinstance(raw_exclusions, list):
        raise ValueError("Phase 5R 제외 security 계약 누락")
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
        raise ValueError("Phase 5R 삼성전자·SK하이닉스 제외 계약 변경")

    agent_b = payload.get("agent_b", {})
    _equal(tuple(agent_b.get("features", ())), FUNDAMENTAL_FEATURES, "Agent B features")
    _equal(agent_b.get("feature_suffix"), "__phase4e_percentile", "Agent B suffix")
    agent_c = payload.get("agent_c", {})
    _equal(tuple(agent_c.get("features", ())), TECHNICAL_FEATURES, "Agent C features")
    _equal(
        tuple(payload.get("phase4e_candidate_controls", ())),
        ("B_ONLY", "C_ONLY", "D_SOFT_FUSION"),
        "Phase 4E candidate controls",
    )
    _equal(
        payload.get("phase5_execute_selected_primary_only"),
        True,
        "Phase 5 selected-primary-only execution",
    )
    portfolio = payload.get("portfolio", {})
    expected_portfolio = {
        "rebalance_sessions": 20,
        "liquidity_lookback_sessions": 20,
        "liquidity_core_size": 50,
        "core_total_weight": 0.70,
        "core_name_weight": 0.014,
        "alpha_size": 10,
        "alpha_total_weight": 0.20,
        "alpha_increment_weight": 0.02,
        "cash_weight": 0.10,
        "maximum_name_weight": 0.034,
        "gap_buy_limit_rate": 0.05,
        "maximum_holding_sessions": 20,
        "pyramiding": False,
        "leverage": False,
        "shorting": False,
    }
    for key, expected_value in expected_portfolio.items():
        _equal(portfolio.get(key), expected_value, f"portfolio.{key}")
    _equal(str(portfolio.get("initial_cash_krw")), "100000000", "portfolio.initial_cash_krw")
    _equal(portfolio.get("stop_loss_rate"), None, "portfolio.stop_loss_rate")
    _equal(portfolio.get("take_profit_rate"), None, "portfolio.take_profit_rate")
    _equal(
        tuple(payload.get("benchmarks", ())),
        (
            "OFFICIAL_KRX_KOSPI200_1028",
            "EX2_PIT_MARKET_CAP_PROXY",
            "NEUTRAL_LIQUIDITY_TOP50_EQUAL_WEIGHT_90",
            "EXPOSURE_MATCHED_KRX1028",
        ),
        "benchmarks",
    )
    _equal(payload.get("cost_stress_multipliers"), [1.0, 2.0], "cost stress")
    if float(payload.get("base_commission_rate", -1)) != 0.0002:
        raise ValueError("Phase 5R commission 변경")
    if float(payload.get("base_slippage_rate", -1)) != 0.001:
        raise ValueError("Phase 5R slippage 변경")
    expected_development_gate = {
        "minimum_nonnegative_years": 2,
        "minimum_net_excess_vs_neutral_core": 0.0,
        "minimum_worst_rolling_12m_vs_neutral_core": -0.10,
        "minimum_mdd": -0.25,
        "maximum_mdd_shortfall_vs_neutral_core": 0.05,
        "minimum_annualized_excess_vs_ex2_cap": -0.01,
        "maximum_downside_capture_vs_ex2_cap": 0.90,
        "minimum_worst_calendar_year_vs_official": -0.15,
        "minimum_worst_rolling_12m_vs_official": -0.20,
        "minimum_average_equity_exposure": 0.80,
        "minimum_closed_trades": 30,
    }
    development_gate = payload.get("development_gate", {})
    for key, expected_value in expected_development_gate.items():
        _equal(
            float(development_gate.get(key, float("nan"))),
            float(expected_value),
            f"development_gate.{key}",
        )
    expected_forward_gate = {
        "provisional_minimum_sessions": 126,
        "final_minimum_sessions": 252,
        "minimum_closed_trades": 30,
    }
    forward_gate = payload.get("forward_gate", {})
    for key, expected_value in expected_forward_gate.items():
        _equal(int(forward_gate.get(key, -1)), expected_value, f"forward_gate.{key}")
    _equal(
        payload.get("evidence_status"),
        "PREREGISTERED_CONSUMED_DEVELOPMENT_PREDICT_ONLY",
        "evidence_status",
    )
    _equal(int(payload.get("seed", -1)), 20260901, "seed")

    market_values = payload.get("market_roots")
    if not isinstance(market_values, list) or not market_values:
        raise ValueError("Phase 5R market_roots 누락")
    config = Phase5RConfig(
        path=path,
        payload=payload,
        experiment_id=EXPERIMENT_ID,
        phase4e_experiment_id=PHASE4E_EXPERIMENT_ID,
        phase4e_bundle=_path(payload, "phase4e_bundle"),
        phase4e_manifest=_path(payload, "phase4e_manifest"),
        phase4e_manifest_sha256=str(payload["phase4e_manifest_sha256"]),
        phase4e_artifact_tree_sha256=str(payload["phase4e_artifact_tree_sha256"]),
        phase4e_bundle_sha256=str(payload["phase4e_bundle_sha256"]),
        phase4e_model_hash=str(payload["phase4e_model_hash"]),
        membership_root=_path(payload, "membership_root"),
        market_roots=tuple(guard_path(Path(str(value))) for value in market_values),
        fundamental_panel=_path(payload, "fundamental_panel"),
        index_file=_path(payload, "index_file"),
        corporate_action_file=_path(payload, "corporate_action_file"),
        engine_config=_path(payload, "engine_config"),
        cost_schedule=_path(payload, "cost_schedule"),
        data_start=date.fromisoformat(str(payload["data_start"])),
        evaluation_start=date.fromisoformat(str(payload["evaluation_start"])),
        fundamental_start=date.fromisoformat(str(payload["fundamental_start"])),
        data_end=date.fromisoformat(str(payload["data_end"])),
        target_horizon_sessions=int(payload["target_horizon_sessions"]),
        sample_every_sessions=int(payload["sample_every_sessions"]),
        excluded_securities=exclusions,
        base_commission_rate=float(payload["base_commission_rate"]),
        base_slippage_rate=float(payload["base_slippage_rate"]),
        seed=int(payload["seed"]),
    )
    if require_resolved_phase4_hashes and not config.phase4_hashes_resolved:
        raise PermissionError("Phase 4E bundle/model hash가 아직 동결되지 않았습니다.")
    return config


__all__ = [
    "EXPERIMENT_ID",
    "ExcludedSecurity",
    "FUNDAMENTAL_FEATURES",
    "MAXIMUM_PERMITTED_DATE",
    "PHASE4E_EXPERIMENT_ID",
    "Phase5RConfig",
    "SCHEMA_VERSION",
    "TECHNICAL_FEATURES",
    "guard_path",
    "load_config",
]
