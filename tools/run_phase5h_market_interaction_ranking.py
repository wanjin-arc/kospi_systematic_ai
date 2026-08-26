#!/usr/bin/env python3
"""Phase 5H: fixed all-market interaction ranking experiment."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pickle
import tempfile
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn

from kospi100_multifactor.config import CANDIDATES, STOCK_FEATURES, load_analysis_config
from kospi100_multifactor.modeling import evaluate_candidates, prepare_multifactor_frame, refit_candidate
from kospi100_multifactor.portfolio import evaluate_internal_portfolios
from kospi100_ranking.data import load_selection_bundle


MAX_DATE = "2018-12-31"
MARKET_FEATURES = (
    "all_kospi_advance_ratio", "all_kospi_median_return_1d", "all_kospi_return_dispersion_1d",
    "all_kospi_log_trading_value_relative_20",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_config(path: Path) -> dict[str, object]:
    payload = _read_json(path)
    if payload.get("version") != "phase5h-market-interaction-ranking-v1" or payload.get("experiment_id") != "EXP-20260825-003":
        raise ValueError("Phase 5H 설정 버전 또는 Experiment ID 불일치")
    if payload.get("maximum_permitted_date") != MAX_DATE:
        raise PermissionError("Phase 5H 최대 입력일은 2018-12-31입니다")
    if payload.get("development_test_access") is not False or payload.get("final_oos_access") != "DENIED_UNTIL_PHASE_8":
        raise PermissionError("Development Test 또는 Final OOS 접근은 허용되지 않습니다")
    feature = payload.get("feature_contract", {})
    if feature != {
        "stock_features": "phase4b_frozen_21_in_order", "market_features": "phase4c_frozen_4_in_order",
        "all_stock_market_interactions": 84, "phase4c_result_based_selection": False,
        "train_only_market_standardization": True,
    }:
        raise ValueError("Phase 5H 고정 Feature 계약이 변경되었습니다")
    models = payload.get("models", {})
    if tuple(models.get("candidate_order", ())) != CANDIDATES:
        raise ValueError("Phase 5H 모델 후보 또는 순서가 변경되었습니다")
    selection = payload.get("selection", {})
    if (selection.get("period"), selection.get("required_nonnegative_annual_excess_folds"), selection.get("required_connected_net_excess_return"), selection.get("development_test_runs")) != ("2015_2018_internal_validation_only", 4, 0.0, 0):
        raise ValueError("Phase 5H 선택 gate가 변경되었습니다")
    if (payload.get("purge_sessions"), payload.get("embargo_sessions"), payload.get("minimum_cross_section")) != (20, 20, 30):
        raise ValueError("Phase 5H purge·embargo·횡단면 계약 불일치")
    for key in ("stock_partition_root", "reference_partition_root"):
        parts = {part.lower() for part in Path(str(payload[key])).parts}
        if "sealed" in parts or "final_oos_v24" in parts or "development" in parts:
            raise PermissionError("Phase 5H 금지 경로")
    return payload


def _reference(root: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    manifest = _read_json(root / "manifest.json")
    if manifest.get("role") != "reference_only_not_universe" or str(manifest.get("max_loaded_date")) > MAX_DATE:
        raise PermissionError("Phase 5H 참조 입력 역할 또는 날짜 경계 위반")
    path = root / "all_kospi_market_reference.csv"
    if _sha256(path) != manifest.get("output_sha256"):
        raise ValueError("Phase 5H 참조 입력 hash 불일치")
    frame = pd.read_csv(path, parse_dates=["date"]).sort_values("date", kind="mergesort")
    if frame["date"].max().date().isoformat() > MAX_DATE:
        raise PermissionError("Phase 5H 참조 reader 결과 날짜 경계 위반")
    value = pd.to_numeric(frame["all_kospi_total_trading_value"], errors="raise")
    frame["all_kospi_log_trading_value_relative_20"] = np.log(value / value.rolling(20, min_periods=20).mean())
    return frame[["date", *MARKET_FEATURES]], manifest


def _model_config(payload: dict[str, object]):
    base = load_analysis_config(Path("configs/phase4b_multifactor.json"))
    interactions = tuple((stock, market) for stock in STOCK_FEATURES for market in MARKET_FEATURES)
    extended_payload = dict(base.payload)
    extended_payload["models"] = payload["models"]
    extended_payload["selection"] = payload["selection"]
    extended_payload["feature_contract"] = payload["feature_contract"]
    extended_payload["run_command"] = payload["run_command"]
    return replace(
        base, payload=extended_payload, experiment_id=str(payload["experiment_id"]),
        regime_features=MARKET_FEATURES, interactions=interactions, candidate_order=CANDIDATES,
        random_seed=int(payload["random_seed"]),
    )


def _data_hash(stock_root: Path, reference_root: Path) -> str:
    stock = _read_json(stock_root / "partition.json")
    reference = _read_json(reference_root / "manifest.json")
    canonical = json.dumps({"stock": stock.get("data_hash"), "reference": reference.get("output_sha256")}, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def freeze_values(payload: dict[str, object], config_path: Path) -> dict[str, str]:
    stock_root = Path(str(payload["stock_partition_root"]))
    stock = _read_json(stock_root / "partition.json")
    if stock.get("role") != "phase4b_train_internal" or stock.get("max_date") != MAX_DATE:
        raise PermissionError("Phase 5H KOSPI 100 물리 partition 경계 위반")
    reference_root = Path(str(payload["reference_partition_root"]))
    _reference(reference_root)
    model_contract = json.dumps({"features": payload["feature_contract"], "models": payload["models"], "portfolio": payload["portfolio"], "selection": payload["selection"], "sklearn": sklearn.__version__}, sort_keys=True, separators=(",", ":"))
    return {
        "code_hash": _sha256(Path(__file__)), "config_hash": _sha256(config_path),
        "data_hash": _data_hash(stock_root, reference_root),
        "model_hash": hashlib.sha256(model_contract.encode("utf-8")).hexdigest(),
    }


def _registry(experiment_id: str) -> dict[str, str]:
    with Path("experiments/registry.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["experiment_id"] == experiment_id]
    if len(rows) != 1:
        raise ValueError("Phase 5H registry 행은 정확히 하나여야 합니다")
    return rows[0]


def _assert_frozen(payload: dict[str, object], config_path: Path) -> dict[str, str]:
    actual = freeze_values(payload, config_path)
    registered = _registry(str(payload["experiment_id"]))
    mapping = {"code_hash": "code_hash", "config_hash": "config_hash", "data_hash": "data_version", "model_hash": "model_hash"}
    if registered.get("status") != "frozen":
        raise PermissionError("Phase 5H 실행 전 registry hash 동결이 필요합니다")
    for key, value in actual.items():
        if registered.get(mapping[key]) != value:
            raise ValueError(f"Phase 5H registry {mapping[key]} 불일치")
    return actual


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(path, index=False, lineterminator="\n", float_format="%.12g")


def run(config_path: Path, output: Path) -> dict[str, object]:
    payload = load_config(config_path)
    frozen = _assert_frozen(payload, config_path)
    config = _model_config(payload)
    bundle = load_selection_bundle(config)
    base = load_analysis_config(Path("configs/phase4b_multifactor.json"))
    prepared = prepare_multifactor_frame(bundle, base)
    market, reference_manifest = _reference(Path(str(payload["reference_partition_root"])))
    frame = prepared.frame.merge(market, on="date", how="left", validate="many_to_one")
    candidates = evaluate_candidates(frame, bundle.index, config)
    portfolios = evaluate_internal_portfolios(candidates.predictions, bundle, config)
    selected = portfolios.accepted_candidate or portfolios.diagnostic_best_candidate
    model_payload, model_binary = refit_candidate(selected, frame, bundle.index, config)
    connected = portfolios.metrics.loc[
        portfolios.metrics["period"].eq("internal_validation_2015_2018") & portfolios.metrics["cost_multiplier"].eq(1)
    ].sort_values("net_excess_return", ascending=False, kind="mergesort")
    selection = dict(portfolios.gate)
    selection.update({"experiment_id": payload["experiment_id"], "model_artifact_candidate": selected, "model_artifact_is_trading_candidate": portfolios.accepted_candidate is not None, "model_hash": model_payload["model_hash"]})
    audit = {
        "experiment_id": payload["experiment_id"], **frozen, "stock_partition_role": bundle.partition.get("role"),
        "stock_max_loaded_date": bundle.partition.get("max_date"), "reference_max_loaded_date": reference_manifest.get("max_loaded_date"),
        "research_maximum_date": str(frame["date"].max().date()), "research_rows": len(frame), "stock_features": 21,
        "market_features": 4, "interaction_features": 84, "phase4c_result_based_selection": False,
        "development_test_rows_loaded": 0, "development_test_rows_calculated": 0, "development_test_rows_evaluated": 0,
        "development_test_rows_selected": 0, "post_2018_rows_loaded": 0, "final_oos_accessed": False,
    }
    run_payload = {
        "experiment_id": payload["experiment_id"], "status": portfolios.gate["status"], **frozen,
        "accepted_candidate": portfolios.accepted_candidate, "diagnostic_best_candidate": portfolios.diagnostic_best_candidate,
        "connected_best_net_excess_return": float(connected.iloc[0]["net_excess_return"]),
        "development_test_accessed": False, "final_oos_accessed": False, "run_command": payload["run_command"],
    }
    if output.exists():
        raise FileExistsError("기존 Phase 5H 산출물을 덮어쓸 수 없습니다")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phase5h_", dir=output.parent) as temporary:
        staging = Path(temporary) / output.name
        staging.mkdir()
        _write_csv(staging / "candidate_portfolio_metrics.csv", portfolios.metrics)
        _write_csv(staging / "fold_rank_metrics.csv", candidates.rank_metrics)
        _write_csv(staging / "fold_audit.csv", candidates.fold_audit)
        _write_csv(staging / "connected_candidate_comparison.csv", connected)
        _write_json(staging / "candidate_selection.json", selection)
        _write_json(staging / "diagnostic_model.json", model_payload)
        (staging / "diagnostic_model.pkl").write_bytes(model_binary)
        _write_json(staging / "data_audit.json", audit)
        _write_json(staging / "run.json", run_payload)
        manifest = {path.name: _sha256(path) for path in sorted(staging.iterdir()) if path.is_file()}
        _write_json(staging / "manifest.json", manifest)
        staging.replace(output)
    return run_payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 5H KOSPI 전체 시장상태 상호작용 ranking")
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
