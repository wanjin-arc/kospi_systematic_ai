#!/usr/bin/env python3
"""Phase 4C: train-internal audit of pre-registered market-reference interactions."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from kospi100_features.evaluate import _hac_tstat
from kospi100_multifactor.config import STOCK_FEATURES, load_analysis_config
from kospi100_multifactor.modeling import prepare_multifactor_frame
from kospi100_ranking.data import load_selection_bundle
from kospi100_ranking.modeling import fold_dates


MAX_DATE = "2018-12-31"
REFERENCE_RAW = (
    "all_kospi_advance_ratio",
    "all_kospi_median_return_1d",
    "all_kospi_return_dispersion_1d",
)
REFERENCE_FEATURES = (*REFERENCE_RAW, "all_kospi_log_trading_value_relative_20")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_config(path: Path) -> dict[str, object]:
    payload = _json(path)
    if payload.get("version") != "phase4c-market-reference-audit-v1":
        raise ValueError("지원하지 않는 Phase 4C 설정 버전")
    if payload.get("experiment_id") != "EXP-20260825-002":
        raise ValueError("Phase 4C Experiment ID 불일치")
    if payload.get("maximum_permitted_date") != MAX_DATE:
        raise PermissionError("Phase 4C 최대 입력일은 2018-12-31이어야 합니다")
    if payload.get("development_test_access") is not False or payload.get("final_oos_access") != "DENIED_UNTIL_PHASE_8":
        raise PermissionError("Development Test 또는 Final OOS 접근 설정은 허용되지 않습니다")
    if tuple(payload.get("reference_features", ())) != REFERENCE_FEATURES:
        raise ValueError("사전등록 KOSPI 전체 시장상태 후보가 변경되었습니다")
    if payload.get("stock_features") != "phase4b_frozen_21_in_order":
        raise ValueError("Phase 4B 종목 Feature 계약이 변경되었습니다")
    if int(payload.get("purge_sessions", -1)) != 20 or int(payload.get("embargo_sessions", -1)) != 20:
        raise ValueError("purge와 embargo는 각각 20세션이어야 합니다")
    if int(payload.get("minimum_cross_section", -1)) != 30:
        raise ValueError("최소 횡단면은 30이어야 합니다")
    if payload.get("promotion") != "NO_PROMOTION_IN_PHASE4C_AUDIT_ONLY":
        raise PermissionError("Phase 4C에서는 Feature 승격을 허용하지 않습니다")
    for key in ("stock_partition_root", "reference_partition_root"):
        parts = {part.lower() for part in Path(str(payload[key])).parts}
        if "sealed" in parts or "final_oos_v24" in parts or "development" in parts:
            raise PermissionError("보호된 경로 또는 development 경로는 Phase 4C 입력이 될 수 없습니다")
    return payload


def _reference_manifest(root: Path) -> dict[str, object]:
    manifest = _json(root / "manifest.json")
    if manifest.get("schema_version") != "phase1b-market-reference-v1":
        raise ValueError("KOSPI 전체 참조 manifest 버전 불일치")
    if manifest.get("role") != "reference_only_not_universe":
        raise PermissionError("KOSPI 전체 참조 입력 역할 불일치")
    if str(manifest.get("max_loaded_date")) > MAX_DATE or manifest.get("post_2023_files_loaded") is not False:
        raise PermissionError("Phase 4C 참조 입력이 2018년 경계를 위반합니다")
    data = root / "all_kospi_market_reference.csv"
    if not data.is_file() or _sha256(data) != manifest.get("output_sha256"):
        raise ValueError("KOSPI 전체 참조 입력 hash 검증 실패")
    return manifest


def load_reference(root: Path) -> pd.DataFrame:
    _reference_manifest(root)  # Boundary and hash checks occur before the data reader.
    frame = pd.read_csv(root / "all_kospi_market_reference.csv", parse_dates=["date"])
    if frame.empty or frame["date"].max().date().isoformat() > MAX_DATE:
        raise PermissionError("KOSPI 전체 참조 reader 결과가 2018년 경계를 위반합니다")
    frame = frame.sort_values("date", kind="mergesort").copy()
    value = pd.to_numeric(frame["all_kospi_total_trading_value"], errors="raise")
    frame["all_kospi_log_trading_value_relative_20"] = np.log(value / value.rolling(20, min_periods=20).mean())
    return frame[["date", *REFERENCE_FEATURES]]


def standardize_from_train(train: pd.Series, validation: pd.Series) -> tuple[pd.Series, dict[str, float]]:
    mean = float(train.mean())
    std = float(train.std(ddof=0))
    if not np.isfinite(mean) or not np.isfinite(std) or std == 0.0:
        raise ValueError("Train-only 시장상태 표준화가 불가능합니다")
    return (validation.astype(float) - mean) / std, {"train_mean": mean, "train_std": std}


def _folds(payload: dict[str, object]) -> tuple[tuple[str, int, int], ...]:
    result = []
    for item in payload["internal_folds"]:  # type: ignore[index]
        row = dict(item)  # type: ignore[arg-type]
        result.append((str(row["fold"]), int(str(row["train"][1])[:4]), int(str(row["validation"][0])[:4])))
    expected = (("I2015", 2014, 2015), ("I2016", 2015, 2016), ("I2017", 2016, 2017), ("I2018", 2017, 2018))
    if tuple(result) != expected:
        raise ValueError("Phase 4C anchored internal fold가 변경되었습니다")
    return tuple(result)


def _data_hash(stock_root: Path, reference_root: Path) -> str:
    stock = _json(stock_root / "partition.json")
    reference = _reference_manifest(reference_root)
    canonical = json.dumps({"stock": stock.get("data_hash"), "reference": reference.get("output_sha256")}, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def freeze_values(payload: dict[str, object], config_path: Path) -> dict[str, str]:
    stock_root = Path(str(payload["stock_partition_root"]))
    reference_root = Path(str(payload["reference_partition_root"]))
    stock = _json(stock_root / "partition.json")
    if stock.get("role") != "phase4b_train_internal" or stock.get("max_date") != MAX_DATE:
        raise PermissionError("KOSPI 100 물리 Train 내부 partition이 아닙니다")
    return {
        "code_hash": _sha256(Path(__file__)),
        "config_hash": _sha256(config_path),
        "data_hash": _data_hash(stock_root, reference_root),
        "model_hash": "NO_MODEL_FEATURE_AUDIT",
    }


def _registry(experiment_id: str) -> dict[str, str]:
    with Path("experiments/registry.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["experiment_id"] == experiment_id]
    if len(rows) != 1:
        raise ValueError("Phase 4C registry 등록은 정확히 한 행이어야 합니다")
    return rows[0]


def _assert_frozen(payload: dict[str, object], config_path: Path) -> dict[str, str]:
    values = freeze_values(payload, config_path)
    registered = _registry(str(payload["experiment_id"]))
    if registered.get("status") != "frozen":
        raise PermissionError("실행 전 registry hash 동결이 필요합니다")
    registry_fields = {"code_hash": "code_hash", "config_hash": "config_hash", "data_hash": "data_version", "model_hash": "model_hash"}
    for key, value in values.items():
        if registered.get(registry_fields[key]) != value:
            raise ValueError(f"registry {registry_fields[key]} hash 불일치")
    return values


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, lineterminator="\n", float_format="%.12g")


def _write_json(value: object, path: Path) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")


def run(config_path: Path, output: Path) -> dict[str, object]:
    payload = load_config(config_path)
    _folds(payload)
    frozen = _assert_frozen(payload, config_path)
    base = load_analysis_config(Path("configs/phase4b_multifactor.json"))
    bundle = load_selection_bundle(base)
    prepared = prepare_multifactor_frame(bundle, base)
    reference = load_reference(Path(str(payload["reference_partition_root"])))
    frame = prepared.frame.merge(reference, on="date", how="left", validate="many_to_one")
    rows: list[dict[str, object]] = []
    state_rows: list[dict[str, object]] = []
    for fold in base.folds:
        train_dates, validation_dates = fold_dates(bundle.index, fold, 20, 20)
        train_daily = reference.loc[reference["date"].isin(train_dates)]
        validation = frame.loc[frame["date"].isin(validation_dates)].copy()
        for market in REFERENCE_FEATURES:
            z, state = standardize_from_train(train_daily[market].dropna(), validation[market])
            state_rows.append({"fold": fold.name, "reference_feature": market, **state, "fit_used_validation": False})
            for stock in STOCK_FEATURES:
                name = f"interaction__{stock}__{market}"
                values = (validation[f"rank__{stock}"].astype(float) - 0.5) * z
                available = validation[["date", "target_rank"]].copy()
                available["interaction"] = values
                available = available.dropna()
                daily = available.groupby("date", sort=True).apply(
                    lambda group: group["interaction"].corr(group["target_rank"], method="spearman"),
                    include_groups=False,
                ).dropna()
                rows.append({
                    "fold": fold.name,
                    "validation_year": fold.validation.start.year,
                    "feature_id": name,
                    "stock_feature": stock,
                    "reference_feature": market,
                    "coverage": float(available.shape[0] / len(validation)) if len(validation) else 0.0,
                    "ic_days": int(len(daily)),
                    "mean_daily_spearman_ic": float(daily.mean()) if not daily.empty else None,
                    "hac_t_stat": _hac_tstat(daily, 10),
                    "positive_ic_day_ratio": float((daily > 0).mean()) if not daily.empty else None,
                })
    metrics = pd.DataFrame(rows).sort_values(["feature_id", "fold"], kind="mergesort")
    summary = metrics.groupby(["feature_id", "stock_feature", "reference_feature"], sort=True).agg(
        minimum_coverage=("coverage", "min"),
        mean_internal_validation_ic=("mean_daily_spearman_ic", "mean"),
        positive_internal_years=("mean_daily_spearman_ic", lambda value: int((value > 0).sum())),
        minimum_hac_t=("hac_t_stat", "min"),
        internal_years=("fold", "nunique"),
    ).reset_index()
    summary["decision"] = "HOLD_AUDIT_ONLY_NO_PROMOTION"
    audit = {
        "experiment_id": payload["experiment_id"], "source_hash": frozen["code_hash"], "config_hash": frozen["config_hash"], "data_hash": frozen["data_hash"],
        "stock_partition_role": bundle.partition.get("role"), "stock_max_loaded_date": str(bundle.partition.get("max_date")),
        "reference_max_loaded_date": _reference_manifest(Path(str(payload["reference_partition_root"]))).get("max_loaded_date"),
        "research_rows": len(frame), "research_maximum_date": str(frame["date"].max().date()),
        "interaction_candidates": len(STOCK_FEATURES) * len(REFERENCE_FEATURES), "development_test_input_loaded": False,
        "development_test_rows_loaded": 0, "development_test_rows_calculated": 0, "development_test_rows_evaluated": 0,
        "final_oos_accessed": False, "post_2018_rows_loaded": 0, "preprocessing_fit_used_validation": False,
        "future_bar_used_for_market_feature": False, "label_audit": prepared.audit["label_audit"],
    }
    run = {"experiment_id": payload["experiment_id"], "status": "ANALYSIS_COMPLETED_TRAIN_INTERNAL_ONLY", "run_command": payload["run_command"], **frozen,
           "candidate_count": len(STOCK_FEATURES) * len(REFERENCE_FEATURES), "development_test_accessed": False, "final_oos_accessed": False}
    if output.exists():
        raise FileExistsError("기존 Phase 4C 산출물을 덮어쓸 수 없습니다")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phase4c_", dir=output.parent) as temporary:
        staging = Path(temporary) / output.name
        staging.mkdir()
        _write_csv(metrics, staging / "fold_interaction_metrics.csv")
        _write_csv(summary, staging / "interaction_summary.csv")
        _write_csv(pd.DataFrame(state_rows).sort_values(["fold", "reference_feature"]), staging / "train_standardization_audit.csv")
        _write_json(audit, staging / "data_audit.json")
        _write_json(run, staging / "run.json")
        manifest = {path.name: _sha256(path) for path in sorted(staging.iterdir()) if path.is_file()}
        _write_json(manifest, staging / "manifest.json")
        staging.replace(output)
    return run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 4C KOSPI 전체 시장상태 상호작용 감사")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args(argv)
    payload = load_config(args.config)
    result = freeze_values(payload, args.config) if args.freeze else run(args.config, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
