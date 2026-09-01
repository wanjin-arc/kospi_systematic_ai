"""Phase 5S frozen-model predict-only 포트폴리오 실행기."""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import pickle
import platform
import re
from typing import Any, Iterable

import numpy as np
import pandas as pd
import scipy
import sklearn

from kospi100_backtest.types import Order, Side
from kospi200_phase4f.modeling import (
    FrozenModelBundle,
    PRIMARY_B,
    PRIMARY_C,
    PRIMARY_D,
    SCHEMA_VERSION as PHASE4F_BUNDLE_SCHEMA,
    predict_frozen_bundle,
)

from .benchmarks import ex2_share_reset_sensitivities, official_index_returns
from .config import EXPERIMENT_ID, Phase5SConfig, load_config
from .data import build_score_panel, load_phase5s_inputs, sha256
from .portfolio import (
    build_causal_buy_orders,
    build_neutral_core_targets,
    build_phase5s_targets,
    select_liquidity_core,
)


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "experiments" / "registry.csv"
CODE_PATHS = (
    "src/kospi200_phase4f/__init__.py",
    "src/kospi200_phase4f/modeling.py",
    "src/kospi200_phase5s/__init__.py",
    "src/kospi200_phase5s/benchmarks.py",
    "src/kospi200_phase5s/cli.py",
    "src/kospi200_phase5s/config.py",
    "src/kospi200_phase5s/data.py",
    "src/kospi200_phase5s/labels.py",
    "src/kospi200_phase5s/modeling.py",
    "src/kospi200_phase5s/portfolio.py",
    "src/kospi200_phase5s/runner.py",
    "src/kospi100_backtest/config.py",
    "src/kospi100_backtest/costs.py",
    "src/kospi100_backtest/engine.py",
    "src/kospi100_backtest/io.py",
    "src/kospi100_backtest/types.py",
    "src/kospi200_agent_d/runner.py",
)
SCORE_COLUMNS = {
    PRIMARY_B: "agent_b_percentile",
    PRIMARY_C: "agent_c_percentile",
    PRIMARY_D: "agent_d_percentile",
}


def _digest_paths(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted((Path(value) for value in paths), key=lambda value: value.as_posix()):
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\n")
    return digest.hexdigest()


def code_hash() -> str:
    paths = tuple(ROOT / value for value in CODE_PATHS)
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Phase 5S code hash 파일 누락: {missing}")
    return _digest_paths(paths)


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if np.isfinite(number) else None
    if isinstance(value, Decimal):
        return str(value)
    return value


def _json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(_safe(value), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _runtime_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
        "scikit_learn": sklearn.__version__,
    }


def _artifact_tree_sha256(manifest_path: Path, bundle_path: Path) -> str:
    manifest = Path(manifest_path).resolve(strict=True)
    bundle = Path(bundle_path).resolve(strict=True)
    root = manifest.parent
    if bundle.parent != root:
        raise PermissionError("Phase 4F bundle과 manifest는 같은 artifact root에 있어야 합니다.")
    paths = sorted(
        (path for path in root.rglob("*") if path.is_file() and path.resolve() != manifest),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    if not paths or bundle not in [path.resolve() for path in paths]:
        raise PermissionError("Phase 4F canonical artifact tree에 bundle이 없습니다.")
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\n")
    return digest.hexdigest()


def _require_phase4f_release_contract(
    config: Phase5SConfig,
    manifest: dict[str, Any],
    bundle: FrozenModelBundle,
) -> None:
    if manifest.get("schema_version") != "v2-phase4f-share-change-safe-model-release-v1":
        raise PermissionError("Phase 4F manifest schema가 새 안전 계약과 다릅니다.")
    if bundle.schema_version != PHASE4F_BUNDLE_SCHEMA:
        raise PermissionError("Phase 4F bundle schema가 새 안전 계약과 다릅니다.")
    if str(manifest.get("decision", "")).startswith("SUPERSEDED"):
        raise PermissionError("폐기된 Phase 4F release는 Phase 5S 입력으로 사용할 수 없습니다.")
    if not isinstance(manifest.get("phase4f_model_gate_pass"), bool):
        raise PermissionError("Phase 4F model gate 상태가 manifest에 없습니다.")
    if manifest.get("phase5s_predict_only_diagnostic_allowed") is not True:
        raise PermissionError("Phase 4F release가 Phase 5S predict-only 진단을 허용하지 않습니다.")
    for key in ("fit_max_date", "fit_max_exit_date"):
        value = str(manifest.get(key, ""))
        try:
            observed = date.fromisoformat(value)
        except ValueError as error:
            raise PermissionError(f"Phase 4F {key}가 유효한 ISO 날짜가 아닙니다.") from error
        if observed > date(2020, 12, 30):
            raise PermissionError(f"Phase 4F {key}가 2020-12-30을 초과합니다.")

    expected_b = tuple(
        f"{name}{config.payload['agent_b']['feature_suffix']}"
        for name in config.payload["agent_b"]["features"]
    )
    expected_c = tuple(config.payload["agent_c"]["features"])
    expected_d = ("agent_b_percentile", "agent_c_percentile", "fundamental_available")
    feature_contracts = {
        "agent_b_features": (tuple(bundle.agent_b_features), expected_b),
        "agent_c_features": (tuple(bundle.agent_c_features), expected_c),
        "agent_d_features": (tuple(bundle.agent_d_features), expected_d),
    }
    for key, (actual, expected) in feature_contracts.items():
        if actual != expected or tuple(manifest.get(key, ())) != expected:
            raise PermissionError(f"Phase 4F {key} 순서가 동결 계약과 다릅니다.")

    # sklearn estimator를 pickle에서 읽은 뒤 다시 pickle한 bytes는 동일한
    # 학습 상태에서도 달라질 수 있다. 생성 시점 component hash를 재직렬화
    # 결과와 비교하지 않고, config에 고정한 bundle SHA-256과 전체 artifact
    # tree SHA-256으로 실제 동결 모델 bytes의 무결성을 검증한다.
    component_hashes = manifest.get("component_sha256")
    if not isinstance(component_hashes, dict) or set(component_hashes) != {
        "agent_b",
        "agent_c",
        "agent_d",
    }:
        raise PermissionError("Phase 4F component model-state hash 계약이 잘못됐습니다.")
    if any(
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        for value in component_hashes.values()
    ):
        raise PermissionError("Phase 4F component model-state hash 형식이 잘못됐습니다.")
    recorded_model_state_hash = manifest.get("model_state_hash")
    if (
        not isinstance(recorded_model_state_hash, str)
        or len(recorded_model_state_hash) != 64
        or any(
            character not in "0123456789abcdef"
            for character in recorded_model_state_hash
        )
    ):
        raise PermissionError("Phase 4F model-state hash 형식이 잘못됐습니다.")
    state = {
        "component_sha256": component_hashes,
        "model_state_hash": recorded_model_state_hash,
    }
    if manifest.get("component_sha256") != state["component_sha256"]:
        raise PermissionError("Phase 4F component model-state hash가 다릅니다.")
    model_state_hash = state["model_state_hash"]
    if manifest.get("model_state_hash") != model_state_hash:
        raise PermissionError("Phase 4F model-state hash가 manifest와 다릅니다.")
    if manifest.get("model_hash") != model_state_hash or config.phase4f_model_hash != model_state_hash:
        raise PermissionError("Phase 4F 기존 model hash와 model-state hash가 일치하지 않습니다.")

    recorded_versions = manifest.get("input_hashes", {}).get("runtime_versions")
    if recorded_versions != _runtime_versions():
        raise PermissionError("Phase 4F 학습 runtime version과 현재 predict runtime이 다릅니다.")


def load_frozen_bundle(config: Phase5SConfig) -> tuple[FrozenModelBundle, dict[str, Any]]:
    if not config.phase4_hashes_resolved:
        raise PermissionError("Phase 4F hash가 config에 동결되지 않았습니다.")
    if not config.phase4f_bundle.is_file() or not config.phase4f_manifest.is_file():
        raise FileNotFoundError("Phase 4F model release 파일이 없습니다.")
    manifest_hash = sha256(config.phase4f_manifest)
    if manifest_hash != config.phase4f_manifest_sha256:
        raise PermissionError("Phase 4F manifest hash가 config와 다릅니다.")
    manifest = json.loads(config.phase4f_manifest.read_text(encoding="utf-8"))
    bundle_hash = sha256(config.phase4f_bundle)
    if bundle_hash != config.phase4f_bundle_sha256:
        raise PermissionError("Phase 4F bundle hash가 config와 다릅니다.")
    if manifest.get("bundle_sha256") != bundle_hash:
        raise PermissionError("Phase 4F manifest bundle hash가 다릅니다.")
    if manifest.get("experiment_id") != config.phase4f_experiment_id:
        raise PermissionError("Phase 4F Experiment ID가 다릅니다.")
    tree_hash = _artifact_tree_sha256(config.phase4f_manifest, config.phase4f_bundle)
    if tree_hash != config.phase4f_artifact_tree_sha256:
        raise PermissionError("Phase 4F canonical artifact tree hash가 config와 다릅니다.")
    if manifest.get("artifact_tree_sha256") != tree_hash:
        raise PermissionError("Phase 4F manifest artifact tree hash가 다릅니다.")
    bundle = pickle.loads(config.phase4f_bundle.read_bytes())
    if not isinstance(bundle, FrozenModelBundle):
        raise TypeError("Phase 4F bundle 객체 형식이 다릅니다.")
    if bundle.primary_agent != manifest.get("primary_agent"):
        raise PermissionError("Phase 4F primary agent가 manifest와 다릅니다.")
    _require_phase4f_release_contract(config, manifest, bundle)
    return bundle, manifest


def _data_version(config: Phase5SConfig, audit: dict[str, object]) -> str:
    return _canonical_hash(
        {
            "input_tree_sha256": audit["input_tree_sha256"],
            "maximum_loaded_date": audit["maximum_permitted_date"],
            "corporate_action_policy": audit.get("corporate_action_semantics"),
            "share_change_gross_ratio_threshold": config.share_change_gross_ratio_threshold,
            "share_change_candidate_source": audit.get("share_change_candidate_source"),
            "share_change_candidate_uses_price": audit.get("share_change_candidate_uses_price"),
            "share_change_candidate_semantics": audit.get("share_change_candidate_semantics"),
            "technical_boundary_policy": audit.get("technical_boundary_policy"),
            "label_boundary_policy": audit.get("label_boundary_policy"),
            "phase4f_manifest_sha256": config.phase4f_manifest_sha256,
            "phase4f_artifact_tree_sha256": config.phase4f_artifact_tree_sha256,
            "phase4f_bundle_sha256": config.phase4f_bundle_sha256,
            "phase4f_model_hash": config.phase4f_model_hash,
            "engine_config_sha256": sha256(config.engine_config),
            "cost_schedule_sha256": sha256(config.cost_schedule),
            "runtime_versions": _runtime_versions(),
        }
    )


def preflight_values(config_path: Path) -> tuple[dict[str, Any], Any, FrozenModelBundle]:
    config = load_config(config_path, require_resolved_phase4_hashes=True)
    bundle, manifest = load_frozen_bundle(config)
    inputs = load_phase5s_inputs(config)
    values = {
        "experiment_id": EXPERIMENT_ID,
        "code_hash": code_hash(),
        "config_hash": config.config_hash,
        "data_version": _data_version(config, inputs.audit),
        "phase4f_manifest_sha256": config.phase4f_manifest_sha256,
        "phase4f_artifact_tree_sha256": config.phase4f_artifact_tree_sha256,
        "phase4f_bundle_sha256": config.phase4f_bundle_sha256,
        "phase4f_model_hash": config.phase4f_model_hash,
        "phase4f_primary_agent": bundle.primary_agent,
        "phase4f_decision": manifest.get("decision"),
        "phase4f_model_gate_pass": manifest.get("phase4f_model_gate_pass"),
        "engine_config_sha256": sha256(config.engine_config),
        "cost_schedule_sha256": sha256(config.cost_schedule),
        "runtime_versions": _runtime_versions(),
        "maximum_loaded_date": inputs.audit["maximum_permitted_date"],
        "final_oos_accessed": False,
    }
    return values, inputs, bundle


def _registry_row() -> dict[str, str]:
    with REGISTRY.open(encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["experiment_id"] == EXPERIMENT_ID]
    if len(rows) != 1:
        raise ValueError(f"registry에 {EXPERIMENT_ID}가 정확히 한 행이어야 합니다.")
    return rows[0]


def verify_preregistration(values: dict[str, Any]) -> None:
    row = _registry_row()
    expected = {
        "status": "preregistered",
        "code_hash": values["code_hash"],
        "config_hash": values["config_hash"],
        "data_version": values["data_version"],
        "model_hash": values["phase4f_model_hash"],
        "final_oos_accessed": "false",
    }
    mismatches = {key: (row.get(key), value) for key, value in expected.items() if row.get(key) != value}
    if mismatches:
        raise PermissionError(f"Phase 5S registry hash freeze 불일치: {mismatches}")


def _rebalance_signal_dates(sessions: list[str], step: int, horizon: int) -> list[str]:
    return [
        sessions[index]
        for index in range(0, len(sessions), int(step))
        if index + int(horizon) + 1 < len(sessions)
    ]


def _phase5s_share_reset_candidates(
    market: pd.DataFrame,
    membership: pd.DataFrame,
    sessions: Iterable[str] | None = None,
    *,
    share_change_gross_ratio_threshold: float,
) -> tuple[dict[str, Any], ...]:
    """주식수 급변을 실행 불가 후보로만 기록한다.

    관측 가격·주식수는 PIT identity, 권위 있는 권리 조건과 배율, 효력일,
    KRX 동일배율 교차검증을 대신할 수 없다. 따라서 이 함수는 어떤
    ``CorporateAction``도 만들지 않으며 후보 여부도 당일 종가로 판정하지 않는다.
    """

    required = {
        "date", "ticker", "open", "close", "listed_shares",
        "unresolved_share_change_candidate", "listed_shares_observation_gap",
    }
    missing = sorted(required - set(market.columns))
    if missing:
        raise ValueError(f"Phase 5S share-reset 후보 입력 열 누락: {missing}")
    if not {"date", "ticker"}.issubset(membership.columns):
        raise ValueError("Phase 5S membership 후보 입력 열 누락")
    frame = market.sort_values(["ticker", "date"], kind="stable").copy()
    if frame.empty:
        return ()
    session_values = (
        tuple(str(day) for day in sessions)
        if sessions is not None
        else tuple(sorted(frame["date"].astype(str).unique()))
    )
    if len(session_values) != len(set(session_values)):
        raise ValueError("Phase 5S share-reset 후보 거래일에 중복이 있습니다.")
    session_number = {day: index for index, day in enumerate(session_values)}
    frame["_session"] = frame["date"].astype(str).map(session_number)
    if frame["_session"].isna().any():
        raise ValueError("Phase 5S share-reset 후보 market 일자가 거래일 목록에 없습니다.")
    group = frame.groupby("ticker", sort=False)
    prior_session = group["_session"].shift(1)
    prior_date = group["date"].shift(1)
    prior_close = group["close"].shift(1)
    prior_shares = group["listed_shares"].shift(1)
    share_ratio = frame["listed_shares"] / prior_shares
    open_ratio = frame["open"] / prior_close
    close_ratio = frame["close"] / prior_close
    consecutive = frame["_session"].sub(prior_session).eq(1)
    valid_pair = (
        consecutive
        & np.isfinite(frame["listed_shares"])
        & frame["listed_shares"].gt(0)
        & np.isfinite(prior_shares)
        & prior_shares.gt(0)
    )
    safe_share_ratio = share_ratio.where(valid_pair)
    recomputed = valid_pair & (
        np.abs(np.log(safe_share_ratio)) >= np.log(share_change_gross_ratio_threshold)
    )
    recorded = (
        frame["unresolved_share_change_candidate"]
        .astype("boolean")
        .fillna(True)
        .astype(bool)
    )
    if not recorded.equals(recomputed.fillna(False).astype(bool)):
        raise AssertionError("Phase 5S loader와 runner의 share-change candidate 집합이 다릅니다.")
    mask = recorded

    members = {
        (str(row.date), str(row.ticker))
        for row in membership[["date", "ticker"]].itertuples(index=False)
    }
    audit: list[dict[str, Any]] = []
    for index in frame.index[mask]:
        row = frame.loc[index]
        previous_day = str(prior_date.loc[index])
        effective_day = str(row["date"])
        ticker = str(row["ticker"])
        ratio = float(share_ratio.loc[index])
        adjusted_open = (
            ratio * float(open_ratio.loc[index])
            if np.isfinite(open_ratio.loc[index]) and open_ratio.loc[index] > 0
            else None
        )
        adjusted_close = (
            ratio * float(close_ratio.loc[index])
            if np.isfinite(close_ratio.loc[index]) and close_ratio.loc[index] > 0
            else None
        )
        prior_member = (previous_day, ticker) in members
        current_member = (effective_day, ticker) in members
        audit.append(
            {
                "candidate_id": f"OBSERVED-SHARE-CHANGE:{effective_day}:{ticker}",
                "previous_date": previous_day,
                "effective_date_candidate": effective_day,
                "ticker": ticker,
                "security_id": str(row.get("security_id", f"KRX_COMMON:{ticker}")),
                "prior_listed_shares": float(prior_shares.loc[index]),
                "current_listed_shares": float(row["listed_shares"]),
                "observed_share_ratio": ratio,
                "prior_close": float(prior_close.loc[index]),
                "effective_open": float(row["open"]),
                "effective_close": float(row["close"]),
                "share_adjusted_open_ratio_diagnostic": adjusted_open,
                "share_adjusted_close_ratio_diagnostic": adjusted_close,
                "prior_member": prior_member,
                "current_member": current_member,
                "member_both_sessions": prior_member and current_member,
                "observed_mechanical_reset": bool(row.get("mechanical_reset", False)),
                "resolution_status": "UNRESOLVED_MISSING_EFFECTIVE_DATE_RATIO_PIT_IDENTITY",
                "authoritative_effective_date_available": False,
                "authoritative_holder_terms_available": False,
                "stable_identity_available": False,
                "krx_same_ratio_crosscheck_complete": False,
                "safe_for_position_accounting": False,
                "executable_corporate_action_created": False,
                "candidate_decision_uses_effective_day_close": False,
                "share_change_gross_ratio_threshold": float(
                    share_change_gross_ratio_threshold
                ),
            }
        )
    return tuple(audit)


def _raw_ticker_identity_audit(
    paths: dict[str, tuple[Path, ...]],
    *,
    evaluation_start: date,
    member_tickers: set[str],
) -> dict[str, Any]:
    """원천 단축코드가 6자리 숫자인지 읽기 전용으로 검증한다."""

    ticker_aliases = {
        "membership": ("ticker", "종목코드", "ISU_SRT_CD"),
        "market": ("종목코드", "ISU_SRT_CD", "ticker"),
    }
    share_aliases = ("상장주식수", "LIST_SHRS", "listed_shares")
    normalized_to_raw: dict[str, set[str]] = {}
    member_normalized_to_raw: dict[str, set[str]] = {}
    source_rows: dict[str, int] = {}
    source_noncanonical_rows: dict[str, int] = {}
    opened_files: dict[str, int] = {}
    noncanonical_examples: set[str] = set()
    prior_exact_market_shares: dict[str, tuple[int, float]] = {}
    raw_exact_ticker_share_reset_candidates = 0
    market_session = -1

    for source in ("membership", "market"):
        rows = 0
        noncanonical_rows = 0
        file_count = 0
        def path_key(value: Path) -> tuple[str, str]:
            day = re.match(r"^(\d{8})", value.name)
            return (day.group(1) if day else "99999999", value.as_posix())

        for path in sorted(paths.get(source, ()), key=path_key):
            match = re.match(r"^(\d{8})", path.name)
            if match and date.fromisoformat(
                f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:8]}"
            ) < evaluation_start:
                continue
            frame: pd.DataFrame | None = None
            last_error: Exception | None = None
            for encoding in (("cp949", "utf-8-sig") if source == "market" else ("utf-8-sig", "cp949")):
                try:
                    frame = pd.read_csv(
                        path,
                        compression="infer",
                        encoding=encoding,
                        dtype=str,
                        keep_default_na=False,
                        usecols=lambda column: column in ticker_aliases[source]
                        or (source == "market" and column in share_aliases),
                    )
                    break
                except UnicodeDecodeError as error:
                    last_error = error
            if frame is None:
                assert last_error is not None
                raise last_error
            columns = [column for column in ticker_aliases[source] if column in frame.columns]
            if len(columns) != 1:
                raise ValueError(f"{source} 원천 ticker 열 계약 위반: {path}")
            share_columns = [column for column in share_aliases if column in frame.columns]
            if source == "market" and len(share_columns) != 1:
                raise ValueError(f"market 원천 listed_shares 열 계약 위반: {path}")
            file_count += 1
            values = frame[columns[0]].astype(str).str.strip()
            rows += len(values)
            canonical = values.str.fullmatch(r"\d{6}", na=False)
            noncanonical_rows += int((~canonical).sum())
            noncanonical_examples.update(values.loc[~canonical].unique().tolist())
            for raw in values.unique():
                digits = re.sub(r"\D", "", raw)
                if not digits or len(digits) > 6:
                    continue
                normalized = digits.zfill(6)
                normalized_to_raw.setdefault(normalized, set()).add(raw)
                if normalized in member_tickers:
                    member_normalized_to_raw.setdefault(normalized, set()).add(raw)
            if source == "market":
                market_session += 1
                listed_shares = pd.to_numeric(
                    frame[share_columns[0]].astype(str).str.replace(",", "", regex=False),
                    errors="coerce",
                )
                for raw, shares in zip(values, listed_shares, strict=True):
                    if not re.fullmatch(r"\d{6}", raw) or not np.isfinite(shares) or shares <= 0:
                        continue
                    prior = prior_exact_market_shares.get(raw)
                    if prior is not None and prior[0] == market_session - 1:
                        ratio = float(shares / prior[1])
                        if abs(float(np.log(ratio))) >= float(np.log(1.20)):
                            raw_exact_ticker_share_reset_candidates += 1
                    prior_exact_market_shares[raw] = (market_session, float(shares))
        source_rows[source] = rows
        source_noncanonical_rows[source] = noncanonical_rows
        opened_files[source] = file_count

    collisions = [
        {"normalized_ticker": ticker, "raw_values": sorted(values)}
        for ticker, values in sorted(normalized_to_raw.items())
        if len(values) > 1 and any(not re.fullmatch(r"\d{6}", value) for value in values)
    ]
    member_collisions = [
        {"normalized_ticker": ticker, "raw_values": sorted(values)}
        for ticker, values in sorted(member_normalized_to_raw.items())
        if len(values) > 1 and any(not re.fullmatch(r"\d{6}", value) for value in values)
    ]
    return {
        "schema_version": "phase5s-share-change-safe-raw-ticker-identity-audit-v1",
        "evaluation_start": evaluation_start.isoformat(),
        "opened_files": opened_files,
        "source_rows": source_rows,
        "source_noncanonical_ticker_rows": source_noncanonical_rows,
        "noncanonical_ticker_row_count": int(sum(source_noncanonical_rows.values())),
        "noncanonical_examples": sorted(noncanonical_examples)[:20],
        "raw_ticker_normalization_collisions": collisions[:20],
        "raw_ticker_normalization_collision_count": len(collisions),
        "member_ticker_normalization_collisions": member_collisions[:20],
        "member_ticker_normalization_collision_count": len(member_collisions),
        "raw_exact_ticker_share_reset_candidate_count": raw_exact_ticker_share_reset_candidates,
        "raw_share_reset_semantics": "CANDIDATE_ONLY_NOT_EXECUTABLE_ACTION",
        "canonical_raw_ticker_contract_complete": not noncanonical_examples and not collisions,
        "stable_identity_contract_complete": False,
        "identity_contract": "TICKER_DERIVED_NOT_HISTORICALLY_RESOLVED",
        "security_id_construction": "KRX_COMMON_PREFIX_PLUS_NORMALIZED_TICKER",
        "position_accounting_allowed": False,
    }


def _order_intent_frame(
    strategy_orders: Iterable[Order],
    neutral_orders: Iterable[Order],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for strategy, orders in (("PRIMARY", strategy_orders), ("NEUTRAL", neutral_orders)):
        for order in orders:
            rows.append(
                {
                    "strategy": strategy,
                    "order_id": order.order_id,
                    "signal_date": order.signal_date.isoformat(),
                    "execute_date": order.execute_date.isoformat(),
                    "security_id": order.security_id,
                    "side": order.side.value,
                    "quantity": order.quantity,
                    "cash_budget": str(order.cash_budget) if order.cash_budget is not None else None,
                    "target_weight": str(order.target_weight) if order.target_weight is not None else None,
                    "priority": order.priority,
                    "limit_price": str(order.limit_price) if order.limit_price is not None else None,
                    "max_holding_sessions": order.max_holding_sessions,
                    "reason": order.reason,
                    "execution_status": "BLOCKED_NOT_SUBMITTED",
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["execute_date", "strategy", "priority", "order_id"], kind="mergesort"
    ).reset_index(drop=True)


def _integrity_decision(
    phase4_manifest: dict[str, Any],
    identity_audit: dict[str, Any],
    share_reset_candidates: tuple[dict[str, Any], ...],
    ex2_audit: dict[str, Any],
) -> tuple[dict[str, bool], str]:
    resolved_candidates = all(
        row.get("safe_for_position_accounting") is True for row in share_reset_candidates
    )
    gates = {
        "phase4f_model_gate": phase4_manifest.get("phase4f_model_gate_pass") is True,
        "stable_identity_contract_complete": identity_audit.get(
            "stable_identity_contract_complete"
        )
        is True,
        "corporate_action_terms_complete": resolved_candidates,
        "canonical_ex2_return_evaluable": ex2_audit.get(
            "canonical_ex2_return_evaluable"
        )
        is True,
    }
    decision = (
        "INTEGRITY_CONTRACT_COMPLETE_NEW_EXPERIMENT_REQUIRED"
        if all(gates.values())
        else "REJECT_PHASE5S_UNRESOLVED_CA_AND_IDENTITY_CONTRACT"
    )
    return gates, decision


def _forced_action_exit_orders(
    market: pd.DataFrame,
    sessions: list[str],
    strategy: str,
) -> tuple[Order, ...]:
    """미해결 공시 block 시작일 시가에 기존 보유를 인지 즉시 fail-closed 청산한다."""

    if "unresolved_action" not in market:
        return ()
    session_index = {day: index for index, day in enumerate(sessions)}
    work = market.sort_values(["ticker", "date"], kind="stable").copy()
    prior = work.groupby("ticker", sort=False)["unresolved_action"].shift(1, fill_value=False)
    starts = work["unresolved_action"].astype(bool) & ~prior.astype(bool)
    orders: list[Order] = []
    for row in work.loc[starts, ["date", "ticker"]].itertuples(index=False):
        index = session_index.get(str(row.date))
        if index is None or index == 0:
            continue
        orders.append(
            Order(
                order_id=f"P5R:{strategy}:ACTION_EXIT:{row.date}:{row.ticker}",
                signal_date=date.fromisoformat(sessions[index - 1]),
                execute_date=date.fromisoformat(str(row.date)),
                security_id=str(row.ticker),
                side=Side.SELL,
                quantity=None,
                priority=-30_000,
                reason="UNRESOLVED_ACTION_FAIL_CLOSED_EXIT",
            )
        )
    return tuple(orders)


def _build_orders(
    config: Phase5SConfig,
    inputs: Any,
    score_panel: pd.DataFrame,
    predicted: pd.DataFrame,
    sessions: list[str],
) -> tuple[tuple[Order, ...], tuple[Order, ...], dict[str, Any]]:
    score_column = SCORE_COLUMNS[str(predicted["primary_agent"].iloc[0])]
    score_map = predicted[["date", "ticker", score_column]].copy()
    eligible_membership = score_panel[["date", "ticker", "security_id"]].copy()
    market_index = inputs.market.set_index(["date", "ticker"])
    session_index = {day: index for index, day in enumerate(inputs.sessions)}
    strategy_orders: list[Order] = []
    neutral_orders: list[Order] = []
    core_rows: list[dict[str, Any]] = []
    for signal_day in _rebalance_signal_dates(
        sessions,
        int(config.payload["portfolio"]["rebalance_sessions"]),
        int(config.payload["portfolio"]["maximum_holding_sessions"]),
    ):
        global_index = session_index[signal_day]
        execute_day = inputs.sessions[global_index + 1]
        core = select_liquidity_core(inputs.market, eligible_membership, signal_day)
        day_scores = score_map.loc[score_map["date"].eq(signal_day), ["ticker", score_column]]
        targets = build_phase5s_targets(core, day_scores, score_column=score_column)
        neutral = build_neutral_core_targets(core)
        closes = (
            inputs.market.loc[inputs.market["date"].eq(signal_day), ["date", "ticker", "close"]]
            .loc[lambda frame: frame["ticker"].isin(set(core["ticker"]))]
        )
        strategy_orders.extend(
            build_causal_buy_orders(
                targets,
                closes,
                signal_date=date.fromisoformat(signal_day),
                execute_date=date.fromisoformat(execute_day),
                strategy_name="PRIMARY",
            )
        )
        neutral_orders.extend(
            build_causal_buy_orders(
                neutral,
                closes,
                signal_date=date.fromisoformat(signal_day),
                execute_date=date.fromisoformat(execute_day),
                strategy_name="NEUTRAL",
            )
        )
        core_rows.append(
            {
                "signal_date": signal_day,
                "execute_date": execute_day,
                "core_count": int(len(core)),
                "score_count": int(len(day_scores)),
                "signal_market_rows": int(sum((signal_day, ticker) in market_index.index for ticker in core["ticker"])),
            }
        )
    forced_primary = _forced_action_exit_orders(inputs.market, sessions, "PRIMARY")
    forced_neutral = _forced_action_exit_orders(inputs.market, sessions, "NEUTRAL")
    return (
        tuple(strategy_orders) + forced_primary,
        tuple(neutral_orders) + forced_neutral,
        {
            "rebalance_count": len(core_rows),
            "core_audit": core_rows,
            "forced_action_exit_orders_primary": len(forced_primary),
            "forced_action_exit_orders_neutral": len(forced_neutral),
        },
    )


def run(config_path: Path, output_root: Path) -> dict[str, Any]:
    config = load_config(config_path, require_resolved_phase4_hashes=True)
    output_root = Path(output_root)
    if output_root.exists():
        raise FileExistsError(f"Phase 5S output이 이미 존재합니다: {output_root}")
    values, inputs, bundle = preflight_values(config_path)
    verify_preregistration(values)
    phase4_manifest = json.loads(config.phase4f_manifest.read_text(encoding="utf-8"))
    score_panel = build_score_panel(inputs, minimum_history_sessions=60)
    eval_panel = score_panel.loc[
        score_panel["date"].between(config.evaluation_start.isoformat(), config.data_end.isoformat())
    ].copy()
    predicted = predict_frozen_bundle(bundle, eval_panel, include_controls=False)
    if len(predicted) != len(eval_panel):
        raise AssertionError("Phase 5S predict가 score universe 행 수를 변경했습니다.")
    if predicted["ticker"].isin(config.excluded_tickers).any():
        raise AssertionError("Phase 5S 점수에 제외 종목이 있습니다.")
    sessions = [
        day
        for day in inputs.sessions
        if config.evaluation_start.isoformat() <= day <= config.data_end.isoformat()
    ]
    strategy_orders, neutral_orders, order_audit = _build_orders(
        config, inputs, eval_panel, predicted, sessions
    )
    eval_market = inputs.market.loc[
        inputs.market["date"].isin(sessions)
    ].copy()
    eval_membership = inputs.membership.loc[
        inputs.membership["date"].isin(sessions)
    ].copy()
    share_reset_candidates = _phase5s_share_reset_candidates(
        eval_market,
        eval_membership,
        sessions,
        share_change_gross_ratio_threshold=config.share_change_gross_ratio_threshold,
    )
    identity_audit = _raw_ticker_identity_audit(
        inputs.paths,
        evaluation_start=config.evaluation_start,
        member_tickers=set(inputs.membership["ticker"]),
    )
    official_reference = official_index_returns(
        inputs.index.loc[inputs.index["date"].isin(sessions)].copy()
    )
    ex2_price_unit, ex2_issuer_cap_value, ex2_audit = ex2_share_reset_sensitivities(
        eval_market,
        eval_membership,
        share_reset_gross_ratio_threshold=config.share_change_gross_ratio_threshold,
    )
    integrity_gates, decision = _integrity_decision(
        phase4_manifest,
        identity_audit,
        share_reset_candidates,
        ex2_audit,
    )
    order_intents = _order_intent_frame(strategy_orders, neutral_orders)
    performance_gate_status = {
        key: "NOT_EVALUATED_PRE_EXECUTION_INTEGRITY_BLOCK"
        for key in config.payload["development_gate"]
    }
    ex2_audit_summary = {
        key: value for key, value in ex2_audit.items() if key != "event_ledger"
    }

    output_root.mkdir(parents=True, exist_ok=False)
    predicted.to_csv(
        output_root / "scores.csv.gz",
        index=False,
        compression={"method": "gzip", "mtime": 0},
        float_format="%.12g",
        lineterminator="\n",
    )
    pd.DataFrame(share_reset_candidates).to_csv(
        output_root / "share_reset_candidates.csv",
        index=False,
        float_format="%.12g",
        lineterminator="\n",
    )
    order_intents.to_csv(
        output_root / "order_intents_blocked.csv",
        index=False,
        lineterminator="\n",
    )
    pd.DataFrame(ex2_audit["event_ledger"]).to_csv(
        output_root / "ex2_share_reset_events.csv",
        index=False,
        float_format="%.12g",
        lineterminator="\n",
    )
    for name, frame in (
        ("official_krx1028_reference.csv", official_reference),
        ("ex2_price_unit_sensitivity.csv", ex2_price_unit),
        ("ex2_issuer_cap_value_sensitivity.csv", ex2_issuer_cap_value),
    ):
        frame.to_csv(output_root / name, index=False, float_format="%.12g", lineterminator="\n")
    _json(
        output_root / "audit.json",
        {
            "run_mode": "PREDICT_AND_PRE_EXECUTION_INTEGRITY_AUDIT",
            "input": inputs.audit,
            "score_panel_rows": int(len(score_panel)),
            "evaluation_score_rows": int(len(eval_panel)),
            "predicted_rows": int(len(predicted)),
            "primary_agent": bundle.primary_agent,
            "fit_calls": 0,
            "fit_allowed": False,
            "excluded_score_rows": 0,
            "order": order_audit,
            "strategy_orders": len(strategy_orders),
            "neutral_orders": len(neutral_orders),
            "order_intent_rows": int(len(order_intents)),
            "share_reset_candidate_count": len(share_reset_candidates),
            "share_change_gross_ratio_threshold": config.share_change_gross_ratio_threshold,
            "share_change_candidate_uses_price": False,
            "member_both_session_share_reset_candidate_count": sum(
                row["member_both_sessions"] for row in share_reset_candidates
            ),
            "executable_corporate_actions_created": 0,
            "identity": identity_audit,
            "ex2_sensitivity": ex2_audit_summary,
            "portfolio_engine_called": False,
            "portfolio_accounting_evaluable": False,
            "performance_metrics_observed": False,
            "external_orders_submitted": 0,
            "final_oos_accessed": False,
        },
    )
    _json(
        output_root / "decision.json",
        {
            "experiment_id": EXPERIMENT_ID,
            "primary_agent": bundle.primary_agent,
            "integrity_gates": integrity_gates,
            "phase5_gate_pass": False,
            "performance_gates": performance_gate_status,
            "performance_metrics_observed": False,
            "portfolio_engine_called": False,
            "ex2_gate_status": "NOT_EVALUABLE_UNRESOLVED_ACTION_AND_IDENTITY_CONTRACT",
            "ex2_sensitivity_audit": ex2_audit_summary,
            "sensitivity_interpretation": "NON_SELF_FINANCING_DIAGNOSTIC_NOT_RETURN_BOUND",
            "decision": decision,
            "evidence_status": "CONSUMED_DEVELOPMENT_NOT_OOS",
        },
    )
    output_files = sorted(
        path for path in output_root.rglob("*") if path.is_file() and path.name != "manifest.json"
    )
    manifest = {
        "schema_version": "v2-phase5s-share-change-safe-integrity-release-v1",
        "experiment_id": EXPERIMENT_ID,
        "decision": decision,
        "primary_agent": bundle.primary_agent,
        "phase4f_manifest_sha256": config.phase4f_manifest_sha256,
        "phase4f_artifact_tree_sha256": config.phase4f_artifact_tree_sha256,
        "phase4f_bundle_sha256": config.phase4f_bundle_sha256,
        "phase4f_model_hash": config.phase4f_model_hash,
        "input_hashes": values,
        "output_sha256": {
            path.relative_to(output_root).as_posix(): sha256(path) for path in output_files
        },
        "fit_calls": 0,
        "portfolio_engine_called": False,
        "performance_metrics_observed": False,
        "external_orders_submitted": 0,
        "final_oos_accessed": False,
    }
    _json(output_root / "manifest.json", manifest)
    return manifest


__all__ = ["code_hash", "load_frozen_bundle", "preflight_values", "run"]
