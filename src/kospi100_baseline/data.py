from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import BaselineConfig


@dataclass(frozen=True)
class DevelopmentBundle:
    feature_panel: pd.DataFrame
    full_history: pd.DataFrame
    index: pd.DataFrame
    corporate_actions: pd.DataFrame
    removals: pd.DataFrame
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
    invalid = ~values.isin({"true", "false", "1", "0"})
    if invalid.any():
        raise ValueError(f"invalid boolean values: {sorted(values[invalid].unique())}")
    return values.isin({"true", "1"})


def load_development_bundle(config: BaselineConfig) -> DevelopmentBundle:
    root = config.data_root.resolve()
    lowered_parts = {part.lower() for part in root.parts}
    if "sealed" in lowered_parts or "final_oos_v24" in lowered_parts:
        raise PermissionError("sealed final OOS paths are forbidden in Phase 3")

    partition_path = root / "partition.json"
    partition = json.loads(partition_path.read_text(encoding="utf-8"))
    if partition.get("role") != "development":
        raise PermissionError("Phase 3 requires a development-role partition")
    if partition.get("max_date") != config.maximum_permitted_date.isoformat():
        raise ValueError("partition maximum date does not match the frozen Phase-3 boundary")

    manifest = pd.read_csv(root / "manifest.csv")
    required_files = {
        "feature_price_panel.csv.gz",
        "full_history_ohlcv.csv.gz",
        "index_ohlcv.csv.gz",
        "corporate_actions.csv.gz",
        "removal_execution.csv.gz",
    }
    manifest_files = set(manifest["file"].astype(str))
    if not required_files.issubset(manifest_files):
        raise ValueError(f"development manifest missing: {sorted(required_files - manifest_files)}")
    verified_hashes: dict[str, str] = {}
    for row in manifest.itertuples(index=False):
        path = root / str(row.file)
        actual = _sha256(path)
        if actual != str(row.sha256):
            raise ValueError(f"development file hash mismatch: {row.file}")
        verified_hashes[str(row.file)] = actual

    feature = pd.read_csv(root / "feature_price_panel.csv.gz", low_memory=False)
    full = pd.read_csv(root / "full_history_ohlcv.csv.gz", low_memory=False)
    index = pd.read_csv(root / "index_ohlcv.csv.gz", low_memory=False)
    actions = pd.read_csv(root / "corporate_actions.csv.gz", low_memory=False)
    removals = pd.read_csv(root / "removal_execution.csv.gz", low_memory=False)

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
    for column in ("last_member_date", "first_nonmember_session", "execution_date"):
        removals[column] = pd.to_datetime(removals[column], errors="raise")

    for name, frame in (("feature_panel", feature), ("full_history", full), ("index", index)):
        maximum = frame["date"].max().date()
        if maximum > config.maximum_permitted_date:
            raise PermissionError(f"{name} crosses the Phase-3 date boundary")

    hash_material = "\n".join(f"{key}:{verified_hashes[key]}" for key in sorted(verified_hashes))
    data_hash = hashlib.sha256(hash_material.encode("utf-8")).hexdigest()
    audit = {
        "partition_role": partition["role"],
        "maximum_loaded_date": max(feature["date"].max(), full["date"].max(), index["date"].max()).date().isoformat(),
        "final_oos_accessed": False,
        "manifest_files_verified": len(verified_hashes),
        "feature_rows": int(len(feature)),
        "full_history_rows": int(len(full)),
        "index_rows": int(len(index)),
        "corporate_action_rows": int(len(actions)),
        "removal_rows": int(len(removals)),
        "data_hash": data_hash,
    }
    return DevelopmentBundle(feature, full, index, actions, removals, partition, data_hash, audit)
