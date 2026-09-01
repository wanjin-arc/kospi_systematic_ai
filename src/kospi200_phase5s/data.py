"""Phase 5S의 물리 입력 경계와 label-독립 score universe 생성."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np
import pandas as pd

from .config import MAXIMUM_PERMITTED_DATE, guard_path


STOCK_FEATURES = (
    "return_1", "return_5", "return_20", "return_60", "volatility_5", "volatility_20",
    "downside_volatility_20", "close_to_ma20", "close_to_ma60", "drawdown_20", "drawdown_60",
    "intraday_range", "volume_ratio_20", "gap_1",
)
INDEX_FEATURES = ("index_return_20", "index_trend_60", "index_volatility_20")
FUNDAMENTAL_FEATURES = (
    "roe", "roa", "operating_margin", "net_margin", "cfo_to_assets",
    "earnings_yield", "book_to_market", "sales_to_market_cap", "cfo_yield", "free_cash_flow_yield",
    "debt_to_equity", "liabilities_to_assets", "current_ratio", "cash_to_assets", "equity_ratio",
    "revenue_growth_yoy", "operating_income_growth_yoy", "net_income_growth_yoy", "assets_growth_yoy",
    "equity_growth_yoy",
)
FUNDAMENTAL_PHASE4F_FEATURES = tuple(f"{name}__phase4e_percentile" for name in FUNDAMENTAL_FEATURES)
# suffix는 변환식 lineage 호환을 위해 유지한다. 실제 새 열 계약은 Phase 4F의
# ``__phase4e_percentile`` 하나뿐이다.
FUNDAMENTAL_PHASE5S_FEATURES = FUNDAMENTAL_PHASE4F_FEATURES
_DATE_NAME = re.compile(r"^(?P<day>\d{8})")


class Phase5SInputs(NamedTuple):
    """NamedTuple이므로 분명한 필드 접근과 7개 tuple unpack을 모두 지원한다."""

    membership: pd.DataFrame
    market: pd.DataFrame
    sessions: tuple[str, ...]
    index: pd.DataFrame
    fundamental: pd.DataFrame
    audit: dict[str, object]
    paths: dict[str, tuple[Path, ...]]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _day_from_path(path: Path) -> date:
    match = _DATE_NAME.match(path.name)
    if match is None:
        raise ValueError(f"날짜를 확인할 수 없는 입력 파일: {path}")
    text = match.group("day")
    return date(int(text[:4]), int(text[4:6]), int(text[6:8]))


def discover_year_partition_files(
    root: Path,
    start: date,
    end: date,
    pattern: str,
) -> tuple[Path, ...]:
    """허용된 연도 디렉터리만 열고 경계 밖 파일은 열지 않는다."""

    root = guard_path(Path(root))
    if end > MAXIMUM_PERMITTED_DATE:
        raise PermissionError("Phase 5S은 2023-12-28 이후 파티션을 열 수 없습니다.")
    selected: list[Path] = []
    for year in range(start.year, end.year + 1):
        year_root = guard_path(root / str(year))
        if not year_root.is_dir():
            continue
        for path in sorted(year_root.glob(pattern)):
            guard_path(path)
            day = _day_from_path(path)
            if start <= day <= end:
                selected.append(path)
    return tuple(selected)


def _normalise_ticker(values: pd.Series) -> pd.Series:
    return values.astype(str).str.replace(r"\D", "", regex=True).str.zfill(6)


def _exact_raw_ticker(values: pd.Series, source: str) -> pd.Series:
    """모델 identity에 쓰는 ticker는 원천의 정확한 6자리 숫자만 허용한다."""

    exact = values.astype(str).str.strip()
    invalid = ~exact.str.fullmatch(r"\d{6}", na=False)
    if bool(invalid.any()):
        examples = exact.loc[invalid].drop_duplicates().head(5).tolist()
        raise ValueError(f"{source}에 비정규 raw ticker가 있습니다: {examples}")
    return exact


def _assert_max_date(frame: pd.DataFrame, maximum: date, source: str) -> None:
    if frame.empty:
        raise ValueError(f"{source} 입력이 비어 있습니다.")
    observed = pd.to_datetime(frame["date"], errors="raise").dt.date.max()
    if observed > maximum:
        raise PermissionError(f"{source} 입력 최대일 {observed} > {maximum}")


def _assert_excluded_absent(frame: pd.DataFrame, config: Any, source: str) -> None:
    ticker_hit = frame.get("ticker", pd.Series(dtype=str)).astype(str).isin(config.excluded_tickers)
    id_hit = frame.get("security_id", pd.Series("", index=frame.index, dtype=str)).astype(str).isin(config.excluded_security_ids)
    if bool(ticker_hit.any() or id_hit.any()):
        raise AssertionError(f"{source}에 삼성전자/SK하이닉스 제외종목이 남아 있습니다.")


def _load_membership(config: Any) -> tuple[pd.DataFrame, tuple[Path, ...]]:
    paths = discover_year_partition_files(config.membership_root, config.data_start, config.data_end, "*.csv")
    if not paths:
        raise FileNotFoundError("Phase 5S PIT KOSPI 200 membership 파티션이 없습니다.")
    pieces: list[pd.DataFrame] = []
    for path in paths:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        if not {"date", "ticker"}.issubset(frame.columns):
            raise ValueError(f"membership 필수 열 누락: {path}")
        frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.date.astype(str)
        expected = _day_from_path(path).isoformat()
        if set(frame["date"]) != {expected}:
            raise ValueError(f"membership 파일명-행 날짜 불일치: {path}")
        frame["ticker"] = _exact_raw_ticker(frame["ticker"], f"membership {path}")
        frame["security_id"] = "KRX_COMMON:" + frame["ticker"]
        keep = ~frame["ticker"].isin(config.excluded_tickers) & ~frame["security_id"].isin(config.excluded_security_ids)
        columns = ["date", "ticker", "security_id"] + (["name"] if "name" in frame.columns else [])
        pieces.append(frame.loc[keep, columns])
    result = pd.concat(pieces, ignore_index=True)
    if result.duplicated(["date", "ticker"]).any():
        raise ValueError("membership에 종목-날짜 중복이 있습니다.")
    result = result.sort_values(["date", "ticker"], kind="mergesort").reset_index(drop=True)
    _assert_max_date(result, config.data_end, "membership")
    _assert_excluded_absent(result, config, "membership")
    return result, paths


def _column(frame: pd.DataFrame, names: tuple[str, ...], required: bool = True) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    if required:
        raise ValueError(f"KRX market 필수 열 누락: {names}")
    return None


def _load_market(
    config: Any,
    tickers: set[str],
) -> tuple[pd.DataFrame, tuple[str, ...], tuple[Path, ...]]:
    all_paths: list[Path] = []
    seen_days: dict[str, Path] = {}
    for root in config.market_roots:
        paths = discover_year_partition_files(root, config.data_start, config.data_end, "*.csv.gz")
        for path in paths:
            day = _day_from_path(path).isoformat()
            if day in seen_days:
                raise ValueError(f"서로 다른 market root에 동일자 중복이 있습니다: {seen_days[day]}, {path}")
            seen_days[day] = path
            all_paths.append(path)
    if not all_paths:
        raise FileNotFoundError("Phase 5S KRX OHLCV 파티션이 없습니다.")
    pieces: list[pd.DataFrame] = []
    for path in sorted(all_paths, key=_day_from_path):
        raw = pd.read_csv(path, compression="gzip", encoding="cp949", dtype=str, keep_default_na=False)
        names = {
            "ticker": _column(raw, ("종목코드", "ISU_SRT_CD")),
            "open": _column(raw, ("시가", "TDD_OPNPRC")),
            "high": _column(raw, ("고가", "TDD_HGPRC")),
            "low": _column(raw, ("저가", "TDD_LWPRC")),
            "close": _column(raw, ("종가", "TDD_CLSPRC")),
            "volume": _column(raw, ("거래량", "ACC_TRDVOL")),
            "trading_value": _column(raw, ("거래대금", "ACC_TRDVAL"), required=False),
            "listed_shares": _column(raw, ("상장주식수", "LIST_SHRS")),
            "market_cap": _column(raw, ("시가총액", "MKTCAP")),
        }
        selected = [value for value in names.values() if value is not None]
        part = raw[selected].copy()
        reverse = {value: key for key, value in names.items() if value is not None}
        part = part.rename(columns=reverse)
        raw_ticker = part["ticker"].astype(str).str.strip()
        canonical = raw_ticker.str.fullmatch(r"\d{6}", na=False)
        normalized = raw_ticker.str.replace(r"\D", "", regex=True).str.zfill(6)
        member_collision = ~canonical & normalized.isin(tickers)
        if bool(member_collision.any()):
            examples = raw_ticker.loc[member_collision].drop_duplicates().head(5).tolist()
            raise ValueError(
                f"market 비정규 raw ticker가 PIT member로 정규화 충돌합니다: {examples}"
            )
        part["ticker"] = raw_ticker
        part = part[canonical & part["ticker"].isin(tickers)].copy()
        for column in ("open", "high", "low", "close", "volume", "trading_value", "listed_shares", "market_cap"):
            if column in part:
                part[column] = pd.to_numeric(part[column].astype(str).str.replace(",", "", regex=False), errors="coerce")
        if "trading_value" not in part:
            part["trading_value"] = part["close"] * part["volume"]
        part["date"] = _day_from_path(path).isoformat()
        part["security_id"] = "KRX_COMMON:" + part["ticker"]
        pieces.append(part[[
            "date", "ticker", "security_id", "open", "high", "low", "close", "volume",
            "trading_value", "listed_shares", "market_cap",
        ]])
    market = pd.concat(pieces, ignore_index=True)
    if market.duplicated(["date", "ticker"]).any():
        raise ValueError("market에 종목-날짜 중복이 있습니다.")
    sessions = tuple(sorted(seen_days))
    session_number = {day: number for number, day in enumerate(sessions)}
    market["_session"] = market["date"].map(session_number)
    market = market.sort_values(["ticker", "date"], kind="mergesort").reset_index(drop=True)
    grouped = market.groupby("ticker", sort=False)
    prior_session = grouped["_session"].shift(1)
    consecutive = market["_session"].sub(prior_session).eq(1)
    prior_shares = grouped["listed_shares"].shift(1)
    current_shares_valid = np.isfinite(market["listed_shares"]) & market["listed_shares"].gt(0)
    prior_shares_valid = np.isfinite(prior_shares) & prior_shares.gt(0)
    valid_share_pair = consecutive & current_shares_valid & prior_shares_valid
    share_ratio = market["listed_shares"] / prior_shares
    safe_share_ratio = share_ratio.where(valid_share_pair)
    threshold = float(config.share_change_gross_ratio_threshold)
    if threshold != 1.20:
        raise ValueError("share-change gross ratio threshold는 1.20으로 동결됩니다.")
    candidate = valid_share_pair & (
        np.abs(np.log(safe_share_ratio)) >= math.log(threshold)
    )
    market["unresolved_share_change_candidate"] = candidate.fillna(False)
    market["listed_shares_observation_gap"] = (
        ~current_shares_valid | (consecutive & ~prior_shares_valid)
    ).fillna(True)
    price_ratio = market["close"] / grouped["close"].shift(1)
    valid_price_ratio = np.isfinite(price_ratio) & price_ratio.gt(0)
    safe_price_ratio = price_ratio.where(valid_price_ratio)
    mechanical = candidate & valid_price_ratio
    mechanical &= (
        np.abs(np.log(safe_share_ratio) + np.log(safe_price_ratio)) <= math.log(1.15)
    )
    market["mechanical_reset"] = mechanical.fillna(False)
    if bool((market["mechanical_reset"] & ~market["unresolved_share_change_candidate"]).any()):
        raise AssertionError("mechanical_reset은 share-change candidate의 부분집합이어야 합니다.")
    finite = np.isfinite(market[["open", "high", "low", "close"]]).all(axis=1)
    market["price_valid"] = (
        finite
        & market[["open", "high", "low", "close"]].gt(0).all(axis=1)
        & market["high"].ge(market[["open", "close"]].max(axis=1))
        & market["low"].le(market[["open", "close"]].min(axis=1))
    )
    market["unresolved_action"] = False
    market = market.drop(columns="_session").sort_values(["date", "ticker"], kind="mergesort").reset_index(drop=True)
    _assert_max_date(market, config.data_end, "market")
    _assert_excluded_absent(market, config, "market")
    return market, sessions, tuple(sorted(all_paths, key=_day_from_path))


def _filing_dates(values: pd.Series) -> pd.Series:
    """DART compact/ISO 날짜를 같은 방식으로 정규화하고 잘못된 행은 거부한다."""

    digits = values.astype(str).str.strip().str.replace(r"\D", "", regex=True)
    invalid = digits.str.len().ne(8)
    parsed = pd.to_datetime(digits, format="%Y%m%d", errors="coerce")
    if bool(invalid.any() or parsed.isna().any()):
        examples = values.loc[invalid | parsed.isna()].astype(str).head(3).tolist()
        raise ValueError(f"corporate action filing_date 형식 오류: {examples}")
    return parsed.dt.normalize()


def audit_unresolved_action_candidates(
    market: pd.DataFrame,
    corporate_action_file: Path,
    maximum_date: date,
) -> tuple[pd.DataFrame, dict[str, object], tuple[Path, ...]]:
    """미확정 기업행동 후보는 감사 증거로만 보존하고 timing에 사용하지 않는다.

    접수 후보 16,151건에는 확정 효력일·배율·PIT security identity가 없다.
    따라서 filing date를 reset, block, 강제청산 또는 membership-spell 경계로
    변환하지 않는다. 실제 기계 reset은 ``_load_market``의 관측 가격/상장주식수
    역관계만 담당하며, 이 함수는 market의 ``unresolved_action``을 항상 거짓으로
    유지한다.
    """

    path = guard_path(Path(corporate_action_file))
    if not path.is_file():
        raise FileNotFoundError(f"미확정 corporate action 입력이 없습니다: {path}")
    actions = pd.read_csv(
        path,
        compression="infer",
        dtype={"ticker": str, "filing_date": str},
        keep_default_na=False,
    )
    required = {"ticker", "filing_date"}
    if not required.issubset(actions.columns):
        raise ValueError(f"corporate action 필수 열 누락: {sorted(required - set(actions.columns))}")
    actions = actions.copy()
    actions["ticker"] = _normalise_ticker(actions["ticker"])
    actions["_filing_date"] = _filing_dates(actions["filing_date"])
    maximum_timestamp = pd.Timestamp(maximum_date)
    in_boundary = actions["_filing_date"].le(maximum_timestamp)
    output = market.copy()
    output["unresolved_action"] = False
    output["unresolved_action"] = output["unresolved_action"].astype(bool)
    bounded = actions.loc[in_boundary]
    event_type_counts = (
        bounded["event_type_candidate"].astype(str).value_counts().sort_index().to_dict()
        if "event_type_candidate" in bounded
        else {}
    )

    audit: dict[str, object] = {
        "corporate_action_source": str(path),
        "corporate_action_source_sha256": sha256(path),
        "corporate_action_source_rows": int(len(actions)),
        "corporate_action_candidate_rows_at_or_before_data_end": int(in_boundary.sum()),
        "corporate_action_candidate_unique_ids_at_or_before_data_end": int(
            bounded["canonical_event_id"].nunique()
            if "canonical_event_id" in bounded
            else len(bounded)
        ),
        "corporate_action_candidate_event_type_counts": {
            str(key): int(value) for key, value in event_type_counts.items()
        },
        "corporate_action_member_on_filing_date_ignored": True,
        "corporate_action_timing_boundaries_emitted": 0,
        "corporate_action_reset_boundaries_emitted": 0,
        "corporate_action_blocked_market_rows": 0,
        "corporate_action_forced_exit_rows": 0,
        "unresolved_action_true_rows": 0,
        "corporate_action_semantics": "UNRESOLVED_FILING_CANDIDATE_EVIDENCE_NOT_TIMING_BOUNDARY",
        "corporate_action_policy": "UNRESOLVED_FILING_CANDIDATE_EVIDENCE_NOT_TIMING_BOUNDARY",
    }
    return output, audit, (path,)


def _load_index(config: Any) -> tuple[pd.DataFrame, tuple[Path, ...]]:
    path = guard_path(config.index_file)
    frame = pd.read_csv(path, compression="infer", dtype={"index_code": str})
    required = {"date", "index_code", "open", "high", "low", "close"}
    if not required.issubset(frame.columns):
        raise ValueError(f"공식 KOSPI 200 지수 열 누락: {sorted(required - set(frame.columns))}")
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.date.astype(str)
    if set(frame["index_code"].astype(str)) != {"1028"}:
        raise ValueError("Phase 5S 공식 지수는 KRX 1028만 허용됩니다.")
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame.duplicated("date").any():
        raise ValueError("공식 KRX 1028에 날짜 중복이 있습니다.")
    _assert_max_date(frame, config.data_end, "official_index")
    if str(frame["date"].max()) != config.data_end.isoformat():
        raise ValueError("공식 KRX 1028 물리 파일의 최대일이 동결 경계와 다릅니다.")
    frame = frame[(frame["date"] >= config.data_start.isoformat()) & (frame["date"] <= config.data_end.isoformat())]
    return frame.sort_values("date", kind="mergesort").reset_index(drop=True), (path,)


def repercentile_fundamental_panel(
    frame: pd.DataFrame,
    excluded_tickers: frozenset[str] | set[str] = frozenset({"005930", "000660"}),
    excluded_security_ids: frozenset[str] | set[str] = frozenset(
        {"KRX_COMMON:005930", "KRX_COMMON:000660"}
    ),
) -> pd.DataFrame:
    """기존 percentile을 폐기하고 제외 후 20개 raw factor를 날짜별로 다시 순위화한다."""

    required = {"date", "ticker", *FUNDAMENTAL_FEATURES}
    if not required.issubset(frame.columns):
        raise ValueError(f"Fundamental raw factor 누락: {sorted(required - set(frame.columns))}")
    output = frame.copy()
    output["date"] = pd.to_datetime(output["date"], errors="raise").dt.date.astype(str)
    output["ticker"] = _normalise_ticker(output["ticker"])
    output["security_id"] = output.get("security_id", "KRX_COMMON:" + output["ticker"])
    output = output[
        ~output["ticker"].isin(excluded_tickers)
        & ~output["security_id"].astype(str).isin(excluded_security_ids)
    ].copy()
    # 입력에 있는 이전 Phase의 percentile/robust-z는 의도적으로 사용하지 않는다.
    old_transforms = [
        column for column in output
        if column.endswith("__percentile") or column.endswith("__robust_z")
    ]
    output = output.drop(columns=old_transforms, errors="ignore")
    for column in FUNDAMENTAL_FEATURES:
        output[column] = pd.to_numeric(output[column], errors="coerce")
        output[f"{column}__phase4e_percentile"] = output.groupby("date", sort=False)[column].rank(
            pct=True, method="average"
        )
    return output


def _load_fundamental(config: Any) -> tuple[pd.DataFrame, tuple[Path, ...]]:
    path = guard_path(config.fundamental_panel)
    manifest_path = guard_path(path.parent / "manifest.json")
    if not manifest_path.is_file():
        raise FileNotFoundError("Fundamental 물리 경계 manifest가 없습니다.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("max_date") != config.data_end.isoformat() or manifest.get("protected_oos_accessed") is not False:
        raise PermissionError("Fundamental manifest의 물리 경계가 Phase 5S 계약과 다릅니다.")
    frame = pd.read_csv(path, compression="infer", dtype={"ticker": str})
    frame = repercentile_fundamental_panel(
        frame,
        config.excluded_tickers,
        config.excluded_security_ids,
    )
    _assert_max_date(frame, config.data_end, "fundamental")
    frame = frame[frame["date"].ge(config.fundamental_start.isoformat())].copy()
    keep = ["date", "ticker", "security_id", *FUNDAMENTAL_FEATURES, *FUNDAMENTAL_PHASE4F_FEATURES]
    for optional in ("statement_year", "statement_quarter", "rank_eligible"):
        if optional in frame:
            keep.append(optional)
    frame = frame[keep].sort_values(["date", "ticker"], kind="mergesort").reset_index(drop=True)
    if frame.duplicated(["date", "ticker"]).any():
        raise ValueError("Fundamental panel에 종목-날짜 중복이 있습니다.")
    _assert_excluded_absent(frame, config, "fundamental")
    return frame, (path, manifest_path)


def _tree_hash(paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda value: value.as_posix()):
        digest.update(path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def load_phase5s_inputs(config: Any) -> Phase5SInputs:
    """Phase 4F/5S duck-type config에서 승인된 2023년 이하 입력만 로드한다."""

    if config.data_end > MAXIMUM_PERMITTED_DATE:
        raise PermissionError("Phase 4F/5S 물리 입력은 2023-12-28을 넘을 수 없습니다.")
    if config.data_start > config.data_end:
        raise ValueError("data_start가 data_end보다 늦습니다.")
    membership, membership_paths = _load_membership(config)
    market, sessions, market_paths = _load_market(config, set(membership["ticker"]))
    market, corporate_action_audit, corporate_action_paths = audit_unresolved_action_candidates(
        market,
        config.corporate_action_file,
        config.data_end,
    )
    index, index_paths = _load_index(config)
    fundamental, fundamental_paths = _load_fundamental(config)
    missing_index_sessions = sorted(set(sessions) - set(index["date"]))
    if missing_index_sessions:
        raise ValueError(f"공식 KRX 1028에 market 세션이 누락됐습니다: {missing_index_sessions[:3]}")
    if max(sessions) > config.data_end.isoformat():
        raise PermissionError("market loader가 설정된 물리 경계 이후 세션을 반환했습니다.")
    paths = {
        "membership": membership_paths,
        "market": market_paths,
        "index": index_paths,
        "fundamental": fundamental_paths,
        "corporate_action": corporate_action_paths,
    }
    audit: dict[str, object] = {
        "maximum_permitted_date": config.data_end.isoformat(),
        "membership_rows": int(len(membership)),
        "membership_min_date": str(membership["date"].min()),
        "membership_max_date": str(membership["date"].max()),
        "market_rows": int(len(market)),
        "market_min_date": str(market["date"].min()),
        "market_max_date": str(market["date"].max()),
        "market_sessions": len(sessions),
        "unresolved_share_change_candidate_rows": int(
            market["unresolved_share_change_candidate"].sum()
        ),
        "listed_shares_observation_gap_rows": int(
            market["listed_shares_observation_gap"].sum()
        ),
        "mechanical_reset_rows": int(market["mechanical_reset"].sum()),
        "mechanical_reset_subset_of_candidate": bool(
            (~market["mechanical_reset"] | market["unresolved_share_change_candidate"]).all()
        ),
        "share_change_gross_ratio_threshold": float(
            config.share_change_gross_ratio_threshold
        ),
        "share_change_candidate_source": "CONSECUTIVE_SESSION_LISTED_SHARES",
        "share_change_candidate_semantics": "CANDIDATE_ONLY_NOT_EXECUTABLE_ACTION",
        "share_change_candidate_uses_price": False,
        "mechanical_reset_semantics": "PRICE_BASED_DIAGNOSTIC_SUBSET_NOT_EXECUTABLE_ACTION",
        "technical_boundary_policy": "RESET_SEGMENT_AT_CANDIDATE_OR_OBSERVATION_GAP",
        "label_boundary_policy": "INVALIDATE_SIGNAL_TO_EXIT_CROSSING",
        "index_rows": int(len(index)),
        "index_min_date": str(index["date"].min()),
        "index_max_date": str(index["date"].max()),
        "fundamental_rows": int(len(fundamental)),
        "fundamental_min_date": str(fundamental["date"].min()),
        "fundamental_max_date": str(fundamental["date"].max()),
        "excluded_rows_returned": 0,
        "final_oos_accessed": False,
        "opened_year_directories": list(range(config.data_start.year, config.data_end.year + 1)),
        "input_tree_sha256": {name: _tree_hash(value) for name, value in paths.items()},
        **corporate_action_audit,
    }
    return Phase5SInputs(membership, market, sessions, index, fundamental, audit, paths)


def _technical_features(market: pd.DataFrame, sessions: tuple[str, ...]) -> pd.DataFrame:
    required_boundaries = {
        "unresolved_share_change_candidate",
        "listed_shares_observation_gap",
        "mechanical_reset",
    }
    missing_boundaries = required_boundaries - set(market)
    if missing_boundaries:
        raise ValueError(f"기술 Feature share-change 경계 열 누락: {sorted(missing_boundaries)}")
    frame = market.sort_values(["ticker", "date"], kind="mergesort").copy()
    session_number = {day: number for number, day in enumerate(sessions)}
    frame["_session"] = frame["date"].map(session_number)
    ticker = frame.groupby("ticker", sort=False)
    gap_reset = frame["_session"].sub(ticker["_session"].shift(1)).ne(1)
    reset = (
        frame["unresolved_share_change_candidate"].astype("boolean").fillna(True).astype(bool)
        | frame["listed_shares_observation_gap"].astype("boolean").fillna(True).astype(bool)
        | gap_reset
    )
    frame["_segment"] = reset.groupby(frame["ticker"], sort=False).cumsum()
    keys = [frame["ticker"], frame["_segment"]]
    group = frame.groupby(keys, sort=False)
    daily_return = group["close"].pct_change(fill_method=None)
    frame["return_1"] = daily_return
    for horizon in (5, 20, 60):
        frame[f"return_{horizon}"] = group["close"].pct_change(horizon, fill_method=None)
    frame["volatility_5"] = daily_return.groupby(keys).rolling(5, min_periods=5).std().reset_index(level=[0, 1], drop=True)
    frame["volatility_20"] = daily_return.groupby(keys).rolling(20, min_periods=20).std().reset_index(level=[0, 1], drop=True)
    downside = daily_return.clip(upper=0)
    frame["downside_volatility_20"] = downside.groupby(keys).rolling(20, min_periods=20).std().reset_index(level=[0, 1], drop=True)
    for horizon in (20, 60):
        mean = group["close"].rolling(horizon, min_periods=horizon).mean().reset_index(level=[0, 1], drop=True)
        peak = group["close"].rolling(horizon, min_periods=horizon).max().reset_index(level=[0, 1], drop=True)
        frame[f"close_to_ma{horizon}"] = frame["close"] / mean - 1.0
        frame[f"drawdown_{horizon}"] = frame["close"] / peak - 1.0
    frame["intraday_range"] = (frame["high"] - frame["low"]) / frame["close"].replace(0, np.nan)
    volume_mean = group["volume"].rolling(20, min_periods=20).mean().reset_index(level=[0, 1], drop=True)
    frame["volume_ratio_20"] = frame["volume"] / volume_mean
    frame["gap_1"] = frame["open"] / group["close"].shift(1) - 1.0
    frame.loc[reset, list(STOCK_FEATURES)] = np.nan
    return frame[["date", "ticker", *STOCK_FEATURES]]


def _index_features(index: pd.DataFrame) -> pd.DataFrame:
    frame = index.sort_values("date", kind="mergesort").copy()
    close = frame["close"].astype(float)
    log_return = np.log(close / close.shift(1))
    frame["index_return_20"] = close.pct_change(20, fill_method=None)
    frame["index_trend_60"] = close / close.rolling(60, min_periods=60).mean() - 1.0
    frame["index_volatility_20"] = log_return.rolling(20, min_periods=20).std() * np.sqrt(252.0)
    return frame[["date", *INDEX_FEATURES]]


def build_score_panel(inputs: Phase5SInputs, minimum_history_sessions: int = 60) -> pd.DataFrame:
    """미래 label의 존재·값을 전혀 보지 않고 당일 score universe를 만든다."""

    if minimum_history_sessions < 60:
        raise ValueError("Agent C return_60을 위해 최소 60세션 history가 필요합니다.")
    membership = inputs.membership.copy()
    market_columns = [
        "date", "ticker", "security_id", "open", "high", "low", "close", "volume", "trading_value",
        "listed_shares", "market_cap", "unresolved_share_change_candidate",
        "listed_shares_observation_gap", "mechanical_reset", "price_valid", "unresolved_action",
    ]
    panel = membership.merge(inputs.market[market_columns], on=["date", "ticker", "security_id"], how="left", validate="one_to_one")
    session_number = {day: number for number, day in enumerate(inputs.sessions)}
    panel["_session"] = panel["date"].map(session_number)
    panel = panel.sort_values(["ticker", "date"], kind="mergesort")
    prior = panel.groupby("ticker", sort=False)["_session"].shift(1)
    new_spell = panel["_session"].sub(prior).ne(1)
    panel["membership_spell_id"] = new_spell.groupby(panel["ticker"], sort=False).cumsum().astype(int)
    panel["membership_history_sessions"] = panel.groupby(["ticker", "membership_spell_id"], sort=False).cumcount() + 1
    technical = _technical_features(inputs.market, inputs.sessions)
    panel = panel.merge(technical, on=["date", "ticker"], how="left", validate="one_to_one")
    panel = panel.merge(_index_features(inputs.index), on="date", how="left", validate="many_to_one")
    fundamental = inputs.fundamental[["date", "ticker", *FUNDAMENTAL_FEATURES]].copy()
    fundamental["fundamental_available"] = 1
    panel = panel.merge(fundamental, on=["date", "ticker"], how="left", validate="one_to_one")
    panel["fundamental_available"] = panel["fundamental_available"].fillna(0).astype(np.int8)
    eligible = (
        panel["price_valid"].astype("boolean").fillna(False)
        & panel["volume"].gt(0)
        & panel["membership_history_sessions"].ge(minimum_history_sessions)
        & ~panel["unresolved_share_change_candidate"].astype("boolean").fillna(True)
        & ~panel["listed_shares_observation_gap"].astype("boolean").fillna(True)
        & ~panel["mechanical_reset"].astype("boolean").fillna(True)
        & ~panel["unresolved_action"].astype("boolean").fillna(True)
        & panel[list(STOCK_FEATURES)].notna().all(axis=1)
        & panel[list(INDEX_FEATURES)].notna().all(axis=1)
    )
    output = panel.loc[eligible].drop(columns="_session")
    # Fundamental 횡단면은 최종 당일 eligible U_t에서 다시 계산한다. 원천 panel의
    # 이전 percentile, 제외 대형주 또는 그 밖의 비적격 행이 순위 분모에 남아
    # 다른 종목 점수를 바꾸는 것을 허용하지 않는다.
    for column in FUNDAMENTAL_FEATURES:
        output[f"{column}__phase4e_percentile"] = (
            output.loc[output["fundamental_available"].eq(1)]
            .groupby("date", sort=False)[column]
            .rank(pct=True, method="average")
            .reindex(output.index)
        )
    output = output.sort_values(["date", "ticker"], kind="mergesort").reset_index(drop=True)
    forbidden_targets = [column for column in output if column.startswith("target_") or column in {"label_valid", "label_invalid_reason"}]
    if forbidden_targets:
        raise AssertionError(f"score universe가 미래 label 열을 참조합니다: {forbidden_targets}")
    if output["ticker"].isin({"005930", "000660"}).any() or output["security_id"].isin({"KRX_COMMON:005930", "KRX_COMMON:000660"}).any():
        raise AssertionError("score universe에 제외 security가 남았습니다.")
    return output
