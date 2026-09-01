"""Phase 4F용 2020-12-30 물리 입력 release를 결정론적으로 생성한다.

이 모듈은 원천을 수정하지 않는다. 2023년까지 포함할 수 있는 기존 개발 원천을
읽어 Phase 4F 전용 새 processed 디렉터리에 2020-12-30 이하 행만 기록한다.
기업행동 자료는 미확정 후보 증거일 뿐이며 timing 경계·reset·block·강제청산을
생성하지 않는다.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from kospi200_phase5s.config import guard_path


SCHEMA_VERSION = "v2-phase4f-share-change-safe-physical-release-v1"
PHYSICAL_CUTOFF = date(2020, 12, 30)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tree_hash(items: Mapping[str, Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    for name in sorted(items):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(items[name]["sha256"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _source_paths(config: Any) -> dict[str, Path]:
    payload = getattr(config, "payload", None)
    if not isinstance(payload, Mapping):
        raise ValueError("Phase 4F config payload가 없습니다.")
    values = payload.get("materialization_sources")
    if not isinstance(values, Mapping):
        raise ValueError("Phase 4F materialization_sources가 없습니다.")
    required = {
        "fundamental_panel",
        "fundamental_manifest",
        "index_file",
        "corporate_action_file",
        "corporate_action_manifest",
    }
    if not required.issubset(values):
        raise ValueError(f"Phase 4F materialization source 누락: {sorted(required - set(values))}")
    result = {name: guard_path(Path(str(values[name]))) for name in sorted(required)}
    missing = [str(path) for path in result.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Phase 4F materialization source가 없습니다: {missing}")
    return result


def _output_paths(config: Any, output_root: Path | None) -> dict[str, Path]:
    configured = {
        "fundamental_panel": guard_path(Path(config.fundamental_panel)),
        "index_file": guard_path(Path(config.index_file)),
        "corporate_action_file": guard_path(Path(config.corporate_action_file)),
        "manifest": guard_path(Path(config.data_release_manifest)),
    }
    if configured["corporate_action_file"].name != "corporate_action_candidates.csv.gz":
        raise ValueError("Phase 4F 기업행동 출력 파일은 corporate_action_candidates.csv.gz여야 합니다.")
    if output_root is None:
        parents = {path.parent.resolve(strict=False) for path in configured.values()}
        if len(parents) != 1:
            raise ValueError("Phase 4F release 출력은 하나의 새 processed 디렉터리여야 합니다.")
        return configured
    root = guard_path(Path(output_root))
    return {name: guard_path(root / path.name) for name, path in configured.items()}


def _read_json(path: Path, label: str) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} manifest가 JSON object가 아닙니다.")
    return payload


def _normalise_dates(frame: pd.DataFrame, column: str, label: str) -> pd.Series:
    if column not in frame:
        raise ValueError(f"{label} 날짜 열 누락: {column}")
    values = frame[column].astype(str).str.strip()
    if column == "filing_date":
        values = values.str.replace(r"\D", "", regex=True)
        invalid = values.str.len().ne(8)
        parsed = pd.to_datetime(values, format="%Y%m%d", errors="coerce")
    else:
        invalid = values.eq("")
        parsed = pd.to_datetime(values, errors="coerce")
    if bool(invalid.any() or parsed.isna().any()):
        examples = frame.loc[invalid | parsed.isna(), column].astype(str).head(3).tolist()
        raise ValueError(f"{label} 날짜 형식 오류: {examples}")
    return parsed.dt.normalize()


def _sort(frame: pd.DataFrame, candidates: tuple[str, ...]) -> pd.DataFrame:
    columns = [column for column in candidates if column in frame]
    if not columns:
        return frame.reset_index(drop=True)
    return frame.sort_values(columns, kind="mergesort").reset_index(drop=True)


def _write_gzip(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as raw:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=9,
            fileobj=raw,
            mtime=0,
        ) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                frame.to_csv(text, index=False, lineterminator="\n")
    temporary.replace(path)


def _write_json(payload: Mapping[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def materialize_phase4f_release(
    config: Any,
    *,
    output_root: Path | None = None,
) -> dict[str, object]:
    """2020-12-30 이하의 Phase 4F 전용 physical release를 만든다.

    ``output_root``는 합성 테스트나 별도 재현 디렉터리에만 쓰는 선택 인자다.
    실제 실행에서는 config가 가리키는 새 processed 경로가 사용된다.
    """

    data_start = getattr(config, "data_start", None)
    data_end = getattr(config, "data_end", None)
    if data_start != date(2004, 1, 2) or data_end != PHYSICAL_CUTOFF:
        raise PermissionError("Phase 4F physical release 경계는 2004-01-02~2020-12-30입니다.")
    sources = _source_paths(config)
    outputs = _output_paths(config, output_root)
    source_resolved = {path.resolve(strict=True) for path in sources.values()}
    source_parents = {path.parent.resolve(strict=True) for path in sources.values()}
    collisions = [str(path) for path in outputs.values() if path.resolve(strict=False) in source_resolved]
    if collisions:
        raise PermissionError(f"원천 파일을 출력으로 덮어쓸 수 없습니다: {collisions}")
    if any(path.parent.resolve(strict=False) in source_parents for path in outputs.values()):
        raise PermissionError("Phase 4F release는 원천과 분리된 새 processed 디렉터리에 써야 합니다.")
    source_hashes_before = {name: sha256(path) for name, path in sources.items()}

    fundamental_manifest = _read_json(sources["fundamental_manifest"], "fundamental")
    if fundamental_manifest.get("protected_oos_accessed") is not False:
        raise PermissionError("Fundamental 원천이 protected OOS 비접근을 증명하지 못합니다.")
    source_fundamental_max = pd.to_datetime(
        fundamental_manifest.get("max_date"), errors="coerce"
    )
    if pd.isna(source_fundamental_max) or source_fundamental_max.date() < PHYSICAL_CUTOFF:
        raise ValueError("Fundamental 원천 manifest가 2020-12-30 coverage를 증명하지 못합니다.")
    claimed_fundamental_hash = fundamental_manifest.get("output_sha256")
    if claimed_fundamental_hash is not None and claimed_fundamental_hash != source_hashes_before["fundamental_panel"]:
        raise PermissionError("Fundamental 원천 manifest hash가 실제 파일과 다릅니다.")
    action_manifest = _read_json(sources["corporate_action_manifest"], "corporate action")
    promoted = action_manifest.get(
        "promoted_mechanical_adjustments",
        action_manifest.get("automatic_adjustments_emitted"),
    )
    if promoted != 0:
        raise ValueError("미확정 corporate action 원천에 승인되지 않은 자동 조정이 있습니다.")
    if action_manifest.get("status") != "BLOCKED_PENDING_VERIFIED_TERMS":
        raise ValueError("corporate action 원천이 검증 대기 중인 미확정 후보 상태가 아닙니다.")
    claimed_action_hash = action_manifest.get("output_sha256")
    if claimed_action_hash is not None and claimed_action_hash != source_hashes_before["corporate_action_file"]:
        raise PermissionError("corporate action 원천 manifest hash가 실제 파일과 다릅니다.")

    fundamental = pd.read_csv(
        sources["fundamental_panel"], compression="infer", dtype=str, keep_default_na=False
    )
    fundamental_dates = _normalise_dates(fundamental, "date", "fundamental")
    fundamental = fundamental.loc[
        fundamental_dates.between(pd.Timestamp(data_start), pd.Timestamp(data_end))
    ].copy()
    fundamental["date"] = pd.to_datetime(fundamental["date"], errors="raise").dt.date.astype(str)
    fundamental = _sort(fundamental, ("date", "ticker", "security_id"))
    if fundamental.empty or fundamental["date"].max() != data_end.isoformat():
        raise ValueError("Fundamental release가 2020-12-30에 물리적으로 끝나지 않습니다.")

    index = pd.read_csv(sources["index_file"], compression="infer", dtype=str, keep_default_na=False)
    required_index = {"date", "index_code", "open", "high", "low", "close"}
    if not required_index.issubset(index):
        raise ValueError(f"KOSPI200 index 열 누락: {sorted(required_index - set(index))}")
    index_dates = _normalise_dates(index, "date", "index")
    index = index.loc[index_dates.between(pd.Timestamp(data_start), pd.Timestamp(data_end))].copy()
    index["date"] = pd.to_datetime(index["date"], errors="raise").dt.date.astype(str)
    index = _sort(index, ("date",))
    if index.empty or index["date"].max() != data_end.isoformat():
        raise ValueError("KOSPI200 index release가 2020-12-30에 물리적으로 끝나지 않습니다.")
    if set(index["index_code"].astype(str)) != {"1028"}:
        raise ValueError("Phase 4F 공식 지수는 KRX 1028만 허용됩니다.")

    actions = pd.read_csv(
        sources["corporate_action_file"],
        compression="infer",
        dtype={"ticker": str, "filing_date": str},
        keep_default_na=False,
    )
    if not {"ticker", "filing_date"}.issubset(actions):
        raise ValueError("corporate action 원천에 ticker/filing_date가 없습니다.")
    filing_dates = _normalise_dates(actions, "filing_date", "corporate action")
    actions = actions.loc[filing_dates.le(pd.Timestamp(data_end))].copy()
    actions["filing_date"] = (
        pd.to_datetime(actions["filing_date"].astype(str).str.replace(r"\D", "", regex=True), format="%Y%m%d")
        .dt.strftime("%Y%m%d")
    )
    actions["materialized_action_semantics"] = (
        "UNRESOLVED_FILING_CANDIDATE_EVIDENCE_NOT_TIMING_BOUNDARY"
    )
    actions = _sort(actions, ("filing_date", "ticker", "canonical_event_id"))

    _write_gzip(fundamental, outputs["fundamental_panel"])
    _write_gzip(index, outputs["index_file"])
    _write_gzip(actions, outputs["corporate_action_file"])

    source_hashes_after = {name: sha256(path) for name, path in sources.items()}
    if source_hashes_after != source_hashes_before:
        raise AssertionError("Phase 4F materialization 중 원천 파일이 변경됐습니다.")
    source_entries = {
        name: {"path": str(path), "bytes": path.stat().st_size, "sha256": source_hashes_before[name]}
        for name, path in sorted(sources.items())
    }
    output_frames = {
        "fundamental_panel": fundamental,
        "index_file": index,
        "corporate_action_file": actions,
    }
    output_entries: dict[str, dict[str, object]] = {}
    for name, frame in output_frames.items():
        path = outputs[name]
        date_column = "filing_date" if name == "corporate_action_file" else "date"
        output_entries[name] = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "rows": int(len(frame)),
            "min_date": None if frame.empty else str(frame[date_column].min()),
            "max_date": None if frame.empty else str(frame[date_column].max()),
        }
    output_tree_sha256 = _tree_hash(output_entries)
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "data_release_id": str(config.data_release_id),
        "data_start": data_start.isoformat(),
        "data_end": data_end.isoformat(),
        "min_date": str(index["date"].min()),
        "max_date": data_end.isoformat(),
        "protected_oos_accessed": False,
        "raw_modified": False,
        "source_files": source_entries,
        "source_tree_sha256": _tree_hash(source_entries),
        "outputs": output_entries,
        "output_tree_sha256": output_tree_sha256,
        "output_sha256": output_tree_sha256,
        "post_cutoff_rows_written": 0,
        "corporate_action_rows": int(len(actions)),
        "corporate_action_member_on_filing_date_trusted": False,
        "corporate_action_candidate_evidence_only": True,
        "corporate_action_timing_boundaries_emitted": 0,
        "corporate_action_reset_boundaries_emitted": 0,
        "corporate_action_blocked_rows": 0,
        "corporate_action_forced_exit_rows": 0,
        "corporate_action_semantics": "UNRESOLVED_FILING_CANDIDATE_EVIDENCE_NOT_TIMING_BOUNDARY",
    }
    _write_json(manifest, outputs["manifest"])
    result = dict(manifest)
    result["manifest_path"] = str(outputs["manifest"])
    result["manifest_sha256"] = sha256(outputs["manifest"])
    return result


__all__ = ["PHYSICAL_CUTOFF", "SCHEMA_VERSION", "materialize_phase4f_release", "sha256"]
