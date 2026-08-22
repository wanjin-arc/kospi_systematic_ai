from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class Period:
    name: str
    start: date
    end: date


@dataclass(frozen=True)
class FeatureDefinition:
    feature_id: str
    family: str
    formula: str
    lookback: int
    expected_direction: str


@dataclass(frozen=True)
class FeatureResearchConfig:
    path: Path
    payload: Mapping[str, Any]
    experiment_id: str
    data_root: Path
    required_partition_role: str
    maximum_permitted_date: date
    research_config_hash: str
    run_command: str
    periods: Mapping[str, Period]
    features: tuple[FeatureDefinition, ...]
    regime_features: tuple[Mapping[str, Any], ...]
    purge_sessions: int
    embargo_sessions: int
    minimum_cross_section: int
    minimum_coverage: float
    minimum_validation_hac_t: float
    minimum_positive_validation_years: int
    redundancy_threshold: float
    hac_lag_sessions: int
    random_seed: int

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


ORIGINAL_EXPERIMENT_ID = "P4-FEATURES-20260818-001"
REVALIDATION_EXPERIMENT_ID = "P4-REVALIDATION-20260819-001"
ORIGINAL_CONFIG_PATH = Path("configs/phase4_features.json")
ORIGINAL_CONFIG_HASH = "2b65169985cf800c05863191e4f19bcb190865a92bd31b325f5be3f299cd7091"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_payload(path: Path) -> tuple[dict[str, Any], str, str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    version = document.get("version")
    if version == "phase4-features-v1":
        if document.get("experiment_id") != ORIGINAL_EXPERIMENT_ID:
            raise ValueError("Phase 4 Experiment ID가 사전 등록값과 다릅니다")
        command = (
            "PYTHONPATH=src python -m kospi100_features.cli run "
            "--config configs/phase4_features.json --output artifacts/phase4"
        )
        return document, _sha256(path), command
    if version != "phase4-revalidation-v1":
        raise ValueError("지원하지 않는 Phase 4 설정입니다")
    expected_wrapper = {
        "experiment_id": REVALIDATION_EXPERIMENT_ID,
        "revalidates_experiment_id": ORIGINAL_EXPERIMENT_ID,
        "base_config": ORIGINAL_CONFIG_PATH.as_posix(),
        "base_config_sha256": ORIGINAL_CONFIG_HASH,
        "required_partition_role": "phase4_train_validation",
        "maximum_permitted_date": "2021-12-31",
    }
    if any(document.get(key) != value for key, value in expected_wrapper.items()):
        raise ValueError("Phase 4 재검증 wrapper가 사전 등록값과 다릅니다")
    base_path = Path(str(document["base_config"]))
    if _sha256(base_path) != ORIGINAL_CONFIG_HASH:
        raise ValueError("원 Phase 4 동결 설정 hash가 다릅니다")
    base = json.loads(base_path.read_text(encoding="utf-8"))
    if base.get("experiment_id") != ORIGINAL_EXPERIMENT_ID:
        raise ValueError("원 Phase 4 동결 설정의 Experiment ID가 다릅니다")
    payload = dict(base)
    payload.update(
        {
            "version": version,
            "experiment_id": document["experiment_id"],
            "data_root": document["data_root"],
            "required_partition_role": document["required_partition_role"],
            "maximum_permitted_date": document["maximum_permitted_date"],
        }
    )
    command = (
        "PYTHONPATH=src python -m kospi100_features.cli run "
        "--config configs/phase4_revalidation_20260819.json "
        "--output artifacts/phase4_revalidation_20260819"
    )
    return payload, ORIGINAL_CONFIG_HASH, command


def load_config(path: Path) -> FeatureResearchConfig:
    payload, research_config_hash, run_command = _load_payload(path)
    if payload.get("required_partition_role") not in {"development", "phase4_train_validation"}:
        raise ValueError("지원하지 않는 Phase 4 파티션 역할입니다")
    if payload.get("final_oos_access") != "DENIED_UNTIL_PHASE_8":
        raise PermissionError("최종 OOS는 Phase 8까지 봉인되어야 합니다")
    evaluation = payload["evaluation"]
    if evaluation.get("development_test_access") is not False:
        raise PermissionError("Phase 4에서는 개발 테스트를 사용할 수 없습니다")
    if evaluation.get("model_training") is not False or evaluation.get("portfolio_backtest") is not False:
        raise ValueError("Phase 4에서는 모델 또는 포트폴리오를 학습·선택하지 않습니다")

    root = Path(payload["data_root"])
    lowered = {part.lower() for part in root.parts}
    if "sealed" in lowered or "final_oos_v24" in lowered:
        raise PermissionError("봉인된 최종 OOS 경로는 Phase 4에서 금지됩니다")
    periods = {
        name: Period(name, date.fromisoformat(bounds[0]), date.fromisoformat(bounds[1]))
        for name, bounds in payload["periods"].items()
    }
    expected_periods = {
        "train": (date(2011, 1, 1), date(2018, 12, 31)),
        "validation": (date(2019, 1, 1), date(2021, 12, 31)),
    }
    if {name: (value.start, value.end) for name, value in periods.items()} != expected_periods:
        raise ValueError("Phase 4 기간이 사전 확정값과 다릅니다")

    features = tuple(
        FeatureDefinition(
            feature_id=item["id"],
            family=item["family"],
            formula=item["formula"],
            lookback=int(item["lookback"]),
            expected_direction=item["expected_direction"],
        )
        for item in payload["cross_sectional_features"]
    )
    if len(features) != 21 or len({item.feature_id for item in features}) != len(features):
        raise ValueError("Phase 4 횡단면 변수군은 사전 등록한 21개여야 합니다")
    label = payload["label"]
    expected_label = {
        "name": "forward_10_session_excess_open_to_open_log_return",
        "formula": "log(stock_open_t_plus_11/stock_open_t_plus_1)-log(index_open_t_plus_11/index_open_t_plus_1)",
        "signal_time": "official_close_t",
        "entry_time": "next_session_open",
        "exit_time": "open_after_10_complete_session_intervals",
        "reset_crossing": "exclude",
        "purge_sessions": 20,
        "embargo_sessions": 20,
    }
    if any(label.get(key) != value for key, value in expected_label.items()):
        raise ValueError("Phase 4 label 또는 purge/embargo 설정이 사전 등록값과 다릅니다")
    if len(payload["regime_features"]) != 5:
        raise ValueError("Phase 4 시장상태 변수군은 사전 등록한 5개여야 합니다")
    expected_evaluation = {
        "selection_partition": "train_and_validation_only",
        "development_test_access": False,
        "minimum_cross_section": 30,
        "minimum_coverage": 0.95,
        "minimum_validation_hac_t": 1.0,
        "minimum_positive_validation_years": 2,
        "redundancy_absolute_spearman": 0.90,
        "hac_lag_sessions": 10,
        "portfolio_backtest": False,
        "model_training": False,
    }
    if any(evaluation.get(key) != value for key, value in expected_evaluation.items()):
        raise ValueError("Phase 4 평가 설정이 사전 등록값과 다릅니다")
    maximum_permitted_date = date.fromisoformat(payload["maximum_permitted_date"])
    expected_maximum = (
        date(2021, 12, 31)
        if payload["experiment_id"] == REVALIDATION_EXPERIMENT_ID
        else date(2023, 12, 31)
    )
    if maximum_permitted_date != expected_maximum:
        raise ValueError("Phase 4 입력 파티션 최대 날짜가 등록값과 다릅니다")
    return FeatureResearchConfig(
        path=path,
        payload=payload,
        experiment_id=payload["experiment_id"],
        data_root=root,
        required_partition_role=str(payload["required_partition_role"]),
        maximum_permitted_date=maximum_permitted_date,
        research_config_hash=research_config_hash,
        run_command=run_command,
        periods=periods,
        features=features,
        regime_features=tuple(payload["regime_features"]),
        purge_sessions=int(label["purge_sessions"]),
        embargo_sessions=int(label["embargo_sessions"]),
        minimum_cross_section=int(evaluation["minimum_cross_section"]),
        minimum_coverage=float(evaluation["minimum_coverage"]),
        minimum_validation_hac_t=float(evaluation["minimum_validation_hac_t"]),
        minimum_positive_validation_years=int(evaluation["minimum_positive_validation_years"]),
        redundancy_threshold=float(evaluation["redundancy_absolute_spearman"]),
        hac_lag_sessions=int(evaluation["hac_lag_sessions"]),
        random_seed=int(payload["random_seed"]),
    )
