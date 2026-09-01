from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import RankingConfig


REQUIRED_FILES = {
    "feature_price_panel.csv.gz": "date",
    "full_history_ohlcv.csv.gz": "date",
    "index_ohlcv.csv.gz": "date",
    "corporate_actions.csv.gz": "feature_boundary_date",
    "removal_orders.csv.gz": "execution_date",
}


@dataclass(frozen=True)
class SelectionBundle:
    feature_panel: pd.DataFrame
    full_history: pd.DataFrame
    index: pd.DataFrame
    corporate_actions: pd.DataFrame
    removal_orders: pd.DataFrame
    partition: dict[str, object]
    data_hash: str
    audit: dict[str, object]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    values = series.astype(str).str.strip().str.lower()
    if (~values.isin({"true", "false", "1", "0"})).any():
        raise ValueError("boolean 열에 허용되지 않은 값이 있습니다")
    return values.isin({"true", "1"})


def load_selection_bundle(config: RankingConfig) -> SelectionBundle:
    root = config.data_root.resolve()
    parts = {part.lower() for part in root.parts}
    if "sealed" in parts or "final_oos_v24" in parts:
        raise PermissionError("Selection에서 봉인 경로를 읽을 수 없습니다")

    partition_path = root / "partition.json"
    manifest_path = root / "manifest.csv"
    partition = json.loads(partition_path.read_text(encoding="utf-8"))
    if partition.get("role") != config.required_partition_role:
        raise PermissionError("Selection 파티션 역할이 사전등록 값과 다릅니다")
    if partition.get("max_date") != config.maximum_permitted_date.isoformat():
        raise PermissionError("Selection 파티션 최대일이 2021-12-31이 아닙니다")
    if partition.get("selection", {}).get("post_2021_rows_loaded") != 0:
        raise PermissionError("Selection 파티션 생성 감사에 2022년 이후 로드가 기록되어 있습니다")

    manifest = pd.read_csv(manifest_path, dtype={"file": str, "sha256": str, "date_column": str})
    if set(manifest["file"]) != set(REQUIRED_FILES):
        raise ValueError("Selection manifest 파일 집합이 허용된 입력과 다릅니다")
    ordered_manifest = manifest.sort_values("file", kind="mergesort")
    for row in ordered_manifest.itertuples(index=False):
        name = str(row.file)
        if str(row.date_column) != REQUIRED_FILES[name]:
            raise ValueError(f"manifest 날짜 열 불일치: {name}")
        if pd.Timestamp(row.max_date).date() > config.maximum_permitted_date:
            raise PermissionError(f"데이터 reader 호출 전 날짜 경계 거부: {name}")
    input_audit: list[dict[str, object]] = []
    hashes: dict[str, str] = {}
    for row in ordered_manifest.itertuples(index=False):
        name = str(row.file)
        path = root / name
        if path.stat().st_size != int(row.bytes):
            raise ValueError(f"입력 bytes 불일치: {name}")
        actual_hash = _sha256(path)
        if actual_hash != str(row.sha256):
            raise ValueError(f"입력 hash 불일치: {name}")
        hashes[name] = actual_hash
        input_audit.append(
            {
                "file": name,
                "bytes": int(row.bytes),
                "sha256": actual_hash,
                "date_column": str(row.date_column),
                "manifest_min_date": str(row.min_date),
                "manifest_max_date": str(row.max_date),
                "manifest_rows": int(row.rows),
            }
        )

    feature = pd.read_csv(root / "feature_price_panel.csv.gz", low_memory=False)
    full = pd.read_csv(root / "full_history_ohlcv.csv.gz", low_memory=False)
    index = pd.read_csv(root / "index_ohlcv.csv.gz", low_memory=False)
    actions = pd.read_csv(root / "corporate_actions.csv.gz", low_memory=False)
    removals = pd.read_csv(root / "removal_orders.csv.gz", low_memory=False)
    frames = {
        "feature_price_panel.csv.gz": feature,
        "full_history_ohlcv.csv.gz": full,
        "index_ohlcv.csv.gz": index,
        "corporate_actions.csv.gz": actions,
        "removal_orders.csv.gz": removals,
    }
    for frame in (feature, full, index):
        frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    for column in ("is_member", "eligible_new_entry", "tradable", "rank_eligible"):
        if column in feature:
            feature[column] = _parse_bool(feature[column])
    for column in ("is_member", "eligible_new_entry", "tradable"):
        if column in full:
            full[column] = _parse_bool(full[column])
    for column in ("feature_boundary_date", "effective_date", "first_filing_date", "last_filing_date"):
        if column in actions:
            actions[column] = pd.to_datetime(actions[column], errors="coerce")
    for column in ("signal_date", "execution_date"):
        removals[column] = pd.to_datetime(removals[column], errors="raise")

    actual_maximum = pd.Timestamp.min
    for item in input_audit:
        frame = frames[str(item["file"])]
        date_column = str(item["date_column"])
        values = pd.to_datetime(frame[date_column], errors="coerce").dropna()
        actual_min = values.min().date().isoformat()
        actual_max = values.max().date().isoformat()
        if len(frame) != int(item["manifest_rows"]):
            raise ValueError(f"로드 행 수 불일치: {item['file']}")
        if actual_min != item["manifest_min_date"] or actual_max != item["manifest_max_date"]:
            raise ValueError(f"로드 날짜 범위 불일치: {item['file']}")
        if pd.Timestamp(actual_max).date() > config.maximum_permitted_date:
            raise PermissionError(f"2022년 이후 행이 실제 입력에 포함됨: {item['file']}")
        item["loaded_rows"] = len(frame)
        item["loaded_min_date"] = actual_min
        item["loaded_max_date"] = actual_max
        item["rows_filtered_after_load"] = 0
        actual_maximum = max(actual_maximum, values.max())

    material = "\n".join(f"{name}:{hashes[name]}" for name in sorted(hashes))
    data_hash = hashlib.sha256(material.encode("utf-8")).hexdigest()
    if data_hash != partition.get("data_hash"):
        raise ValueError("파티션 data hash 불일치")
    audit = {
        "experiment_id": config.experiment_id,
        "partition_role": partition["role"],
        "partition_root": root.as_posix(),
        "data_hash": data_hash,
        "inputs": input_audit,
        "maximum_loaded_date": actual_maximum.date().isoformat(),
        "filter_applied_after_load": False,
        "train_validation_input_loaded": True,
        "development_test_input_loaded": False,
        "development_test_rows_loaded": 0,
        "development_test_rows_calculated": 0,
        "development_test_rows_evaluated": 0,
        "development_test_rows_selected": 0,
        "final_oos_accessed": False,
    }
    return SelectionBundle(feature, full, index, actions, removals, partition, data_hash, audit)
