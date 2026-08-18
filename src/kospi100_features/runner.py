from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import pandas as pd

from .config import FeatureResearchConfig, load_config
from .evaluate import EvaluationResult, evaluate_features
from .features import FeatureMatrixResult, build_feature_matrix
from .labels import LABEL_COLUMN, attach_forward_label


REQUIRED_DATA_FILES = (
    "corporate_actions.csv.gz",
    "feature_price_panel.csv.gz",
    "full_history_ohlcv.csv.gz",
    "index_ohlcv.csv.gz",
)
CONTRACT_PATH = Path("data/contracts/feature_data_contract_v24.json")
OUTPUT_FILES = (
    "annual_ic.csv",
    "data_audit.json",
    "feature_decisions.csv",
    "feature_metrics.csv",
    "regime_feature_audit.csv",
    "redundancy_matrix.csv",
    "run.json",
)


@dataclass(frozen=True)
class Phase4Bundle:
    feature_panel: pd.DataFrame
    full_history: pd.DataFrame
    index: pd.DataFrame
    corporate_actions: pd.DataFrame
    partition: Mapping[str, object]
    manifest_hashes: Mapping[str, str]
    data_hash: str
    contract_hash: str
    audit: Mapping[str, object]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _forbidden_path(path: Path) -> bool:
    parts = {part.lower() for part in path.resolve().parts}
    return "sealed" in parts or "final_oos_v24" in parts


def _parse_bool(series: pd.Series, name: str) -> pd.Series:
    if series.dtype == bool:
        return series
    normalized = series.astype(str).str.strip().str.lower()
    invalid = ~normalized.isin({"true", "false", "1", "0"})
    if invalid.any():
        raise ValueError(f"{name} 열에 잘못된 불리언 값이 있습니다")
    return normalized.isin({"true", "1"})


def _source_hash() -> str:
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(root.glob("*.py"), key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def load_phase4_bundle(config: FeatureResearchConfig) -> Phase4Bundle:
    root = config.data_root.resolve()
    if _forbidden_path(root):
        raise PermissionError("Phase 4에서 봉인 OOS 경로는 금지됩니다")
    if not root.is_dir():
        raise FileNotFoundError(f"development 데이터 root가 없습니다: {root}")

    contract = CONTRACT_PATH.resolve()
    if _forbidden_path(contract) or not contract.is_file():
        raise FileNotFoundError("canonical Phase 4 데이터 계약이 없습니다")
    contract_payload = json.loads(contract.read_text(encoding="utf-8"))
    if contract_payload.get("version") != "v24":
        raise ValueError("Phase 4 데이터 계약 버전은 v24여야 합니다")

    partition_path = root / "partition.json"
    manifest_path = root / "manifest.csv"
    partition = json.loads(partition_path.read_text(encoding="utf-8"))
    if partition.get("role") != "development":
        raise PermissionError("Phase 4는 development 역할 파티션만 허용합니다")
    if partition.get("max_date") != config.maximum_permitted_date.isoformat():
        raise ValueError("development 파티션 최대 날짜가 Phase 4 설정과 다릅니다")

    manifest = pd.read_csv(manifest_path, dtype={"file": "string", "sha256": "string"})
    required_columns = {"file", "bytes", "sha256"}
    if not required_columns.issubset(manifest.columns):
        raise ValueError("development manifest 필수 열이 없습니다")
    if manifest["file"].duplicated().any():
        raise ValueError("development manifest에 중복 파일이 있습니다")
    missing = set(REQUIRED_DATA_FILES) - set(manifest["file"].astype(str))
    if missing:
        raise ValueError(f"development manifest 필수 파일 누락: {sorted(missing)}")

    verified: dict[str, str] = {}
    for row in manifest.sort_values("file", kind="mergesort").itertuples(index=False):
        path = root / str(row.file)
        if not path.is_file():
            raise FileNotFoundError(f"development manifest 파일이 없습니다: {row.file}")
        if path.stat().st_size != int(row.bytes):
            raise ValueError(f"development 파일 크기 불일치: {row.file}")
        actual = _sha256(path)
        if actual != str(row.sha256):
            raise ValueError(f"development 파일 hash 불일치: {row.file}")
        verified[str(row.file)] = actual

    feature = pd.read_csv(root / "feature_price_panel.csv.gz", low_memory=False)
    full = pd.read_csv(root / "full_history_ohlcv.csv.gz", low_memory=False)
    index = pd.read_csv(root / "index_ohlcv.csv.gz", low_memory=False)
    actions = pd.read_csv(root / "corporate_actions.csv.gz", low_memory=False)

    for frame in (feature, full, index):
        frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    for column in ("is_member", "eligible_new_entry", "tradable", "rank_eligible"):
        if column in feature:
            feature[column] = _parse_bool(feature[column], column)
    for column in ("is_member", "eligible_new_entry", "tradable", "rank_eligible"):
        if column in full:
            full[column] = _parse_bool(full[column], column)
    for column in ("feature_boundary_date", "effective_date", "first_filing_date", "last_filing_date"):
        if column in actions:
            actions[column] = pd.to_datetime(actions[column], errors="coerce")

    maximums = {
        "feature_price_panel": feature["date"].max(),
        "full_history_ohlcv": full["date"].max(),
        "index_ohlcv": index["date"].max(),
    }
    if any(value.date() > config.maximum_permitted_date for value in maximums.values()):
        raise PermissionError("development 입력이 Phase 4 최대 허용 날짜를 초과했습니다")
    if any(frame.empty for frame in (feature, full, index)):
        raise ValueError("Phase 4 필수 입력이 비어 있습니다")

    hash_material = "\n".join(f"{name}:{verified[name]}" for name in sorted(verified))
    data_hash = hashlib.sha256(hash_material.encode("utf-8")).hexdigest()
    audit = {
        "partition_role": partition["role"],
        "partition_max_date": partition["max_date"],
        "maximum_loaded_date": max(maximums.values()).date().isoformat(),
        "evaluation_maximum_permitted_date": config.periods["validation"].end.isoformat(),
        "development_test_rows_evaluated": 0,
        "development_test_accessed_for_selection": False,
        "final_oos_accessed": False,
        "manifest_files_verified": len(verified),
        "manifest_hash": _sha256(manifest_path),
        "partition_hash": _sha256(partition_path),
        "contract_path": CONTRACT_PATH.as_posix(),
        "contract_hash": _sha256(contract),
        "feature_rows": int(len(feature)),
        "full_history_rows": int(len(full)),
        "index_rows": int(len(index)),
        "corporate_action_rows": int(len(actions)),
        "data_hash": data_hash,
    }
    return Phase4Bundle(feature, full, index, actions, partition, verified, data_hash, _sha256(contract), audit)


def _write_json(path: Path, payload: object) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def _write_csv(path: Path, frame: pd.DataFrame, *, index: bool = False) -> None:
    frame.to_csv(path, index=index, encoding="utf-8", lineterminator="\n", float_format="%.12g")


def _annual_ic(evaluation: EvaluationResult) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for column in sorted(evaluation.daily_ic.columns):
        feature_id, period = column.rsplit("__", 1)
        series = evaluation.daily_ic[column].dropna()
        for year, values in series.groupby(series.index.year):
            rows.append(
                {
                    "feature_id": feature_id,
                    "period": period,
                    "year": int(year),
                    "mean_daily_spearman_ic": float(values.mean()),
                    "ic_days": int(len(values)),
                }
            )
    return pd.DataFrame(rows).sort_values(["feature_id", "period", "year"], kind="mergesort").reset_index(drop=True)


def _regime_audit(regime: pd.DataFrame, config: FeatureResearchConfig) -> pd.DataFrame:
    ids = [str(item["id"]) for item in config.regime_features]
    coverage_columns = [column for column in regime.columns if column.endswith("_coverage")]
    maximum = pd.Timestamp(config.periods["validation"].end)
    output = regime.loc[regime["date"].le(maximum), ["date"] + ids + coverage_columns].copy()
    output["decision"] = "보류_Phase7"
    return output.sort_values("date", kind="mergesort").reset_index(drop=True)


def _publish_outputs(
    output_dir: Path,
    config: FeatureResearchConfig,
    bundle: Phase4Bundle,
    features: FeatureMatrixResult,
    label_audit: Mapping[str, object],
    evaluation: EvaluationResult,
) -> dict[str, object]:
    if _forbidden_path(output_dir):
        raise PermissionError("Phase 4 산출물을 봉인 OOS 경로에 쓸 수 없습니다")
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics = evaluation.metrics.sort_values(["feature_id", "period"], kind="mergesort").reset_index(drop=True)
    decisions = evaluation.decisions.sort_values("feature_id", kind="mergesort").reset_index(drop=True)
    redundancy = evaluation.redundancy.copy().sort_index().sort_index(axis=1)
    redundancy.index.name = "feature_id"
    annual = _annual_ic(evaluation)
    regime = _regime_audit(features.regime, config)

    _write_csv(output_dir / "feature_metrics.csv", metrics)
    _write_csv(output_dir / "annual_ic.csv", annual)
    _write_csv(output_dir / "feature_decisions.csv", decisions)
    _write_csv(output_dir / "redundancy_matrix.csv", redundancy, index=True)
    _write_csv(output_dir / "regime_feature_audit.csv", regime)

    data_audit = {
        **bundle.audit,
        "feature_audit": features.audit,
        "label_audit": dict(label_audit),
        "evaluation_audit": evaluation.audit,
        "maximum_evaluated_signal_date": evaluation.audit["maximum_evaluated_signal_date"],
        "development_test_rows_evaluated": 0,
        "final_oos_accessed": False,
    }
    run = {
        "experiment_id": config.experiment_id,
        "command": "PYTHONPATH=src python -m kospi100_features.cli run --config configs/phase4_features.json --output artifacts/phase4",
        "source_hash": _source_hash(),
        "config_hash": config.config_hash,
        "data_hash": bundle.data_hash,
        "contract_hash": bundle.contract_hash,
        "random_seed": config.random_seed,
        "cross_sectional_features": len(config.features),
        "regime_features": len(config.regime_features),
        "label_column": LABEL_COLUMN,
        "model_trained": False,
        "portfolio_backtest_run": False,
        "development_test_accessed_for_selection": False,
        "final_oos_accessed": False,
        "accepted_phase5_candidates": evaluation.audit["accepted_features"],
    }
    _write_json(output_dir / "data_audit.json", data_audit)
    _write_json(output_dir / "run.json", run)

    files = {name: _sha256(output_dir / name) for name in OUTPUT_FILES}
    manifest = {
        "version": "phase4-artifacts-v1",
        "experiment_id": config.experiment_id,
        "source_hash": run["source_hash"],
        "config_hash": config.config_hash,
        "data_hash": bundle.data_hash,
        "files": files,
        "deterministic_serialization": True,
        "final_oos_accessed": False,
    }
    _write_json(output_dir / "manifest.json", manifest)
    return {"run": run, "data_audit": data_audit, "manifest": manifest}


def run_phase4(config_path: Path, output_dir: Path) -> dict[str, object]:
    config = load_config(config_path)
    if _forbidden_path(output_dir):
        raise PermissionError("Phase 4 산출물을 봉인 OOS 경로에 쓸 수 없습니다")
    bundle = load_phase4_bundle(config)
    analysis_end = pd.Timestamp(config.periods["validation"].end)
    feature_input = bundle.feature_panel.loc[bundle.feature_panel["date"].le(analysis_end)].copy()
    full_history_input = bundle.full_history.loc[bundle.full_history["date"].le(analysis_end)].copy()
    index_input = bundle.index.loc[bundle.index["date"].le(analysis_end)].copy()
    actions_input = bundle.corporate_actions.loc[
        bundle.corporate_actions["feature_boundary_date"].notna()
        & bundle.corporate_actions["feature_boundary_date"].le(analysis_end)
    ].copy()
    if any(frame["date"].max() > analysis_end for frame in (feature_input, full_history_input, index_input)):
        raise PermissionError("Development Test 행이 Phase 4 계산 입력에 포함됐습니다")
    feature_result = build_feature_matrix(
        feature_input,
        index_input,
        actions_input,
    )
    labeled, label_audit = attach_forward_label(
        feature_result.cross_sectional,
        full_history_input,
        index_input,
        actions_input,
    )
    evaluation = evaluate_features(labeled, index_input, config)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".phase4-", dir=output_dir.parent) as temporary:
        staging = Path(temporary)
        result = _publish_outputs(staging, config, bundle, feature_result, label_audit, evaluation)
        result["data_audit"]["maximum_calculation_input_date"] = analysis_end.date().isoformat()
        result["data_audit"]["development_test_rows_calculated"] = 0
        _write_json(staging / "data_audit.json", result["data_audit"])
        result["manifest"]["files"]["data_audit.json"] = _sha256(staging / "data_audit.json")
        _write_json(staging / "manifest.json", result["manifest"])
        for name, expected in result["manifest"]["files"].items():
            if _sha256(staging / name) != expected:
                raise RuntimeError(f"Phase 4 staging hash 검증 실패: {name}")
        output_dir.mkdir(parents=True, exist_ok=True)
        for name in OUTPUT_FILES:
            (staging / name).replace(output_dir / name)
        (staging / "manifest.json").replace(output_dir / "manifest.json")
    return result


__all__ = ["Phase4Bundle", "load_phase4_bundle", "run_phase4"]
