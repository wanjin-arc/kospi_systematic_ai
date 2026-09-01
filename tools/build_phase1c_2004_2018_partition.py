from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import tempfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from collect_krx_v25_technical import canonical_columns, normalize_ticker, numeric, parse_csv


RAW_START = date(2004, 1, 2)
RAW_END = date(2009, 12, 31)
MAXIMUM_DATE = date(2018, 12, 31)
OUTPUT_ROLE = "phase5i_train_internal_2004_2018"
FILES = {
    "feature_price_panel.csv.gz": "date",
    "full_history_ohlcv.csv.gz": "date",
    "index_ohlcv.csv.gz": "date",
    "corporate_actions.csv.gz": "feature_boundary_date",
    "removal_orders.csv.gz": "execution_date",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_membership(path: Path, session: pd.Timestamp) -> pd.DataFrame:
    with gzip.open(path, "rb") as handle:
        frame = parse_csv(handle.read())
    if frame.shape[1] < 2:
        raise ValueError(f"구성종목 CSV 열 부족: {path}")
    ticker_column = next(
        (column for column in frame.columns if frame[column].map(normalize_ticker).notna().mean() > 0.9),
        frame.columns[0],
    )
    name_column = frame.columns[1]
    result = pd.DataFrame(
        {
            "date": session,
            "ticker": frame[ticker_column].map(normalize_ticker),
            "name": frame[name_column].astype(str).str.strip(),
        }
    )
    return result.dropna(subset=["ticker"]).drop_duplicates(["date", "ticker"])


def _read_market(path: Path, session: pd.Timestamp) -> pd.DataFrame:
    with gzip.open(path, "rb") as handle:
        frame = canonical_columns(parse_csv(handle.read()))
    frame.insert(0, "date", session)
    return frame


def _read_index(path: Path, raw_root: Path) -> pd.DataFrame:
    with gzip.open(path, "rb") as handle:
        frame = parse_csv(handle.read())
    aliases = {
        "date": ("TRD_DD",),
        "open": ("OPNPRC_IDX",),
        "high": ("HGPRC_IDX",),
        "low": ("LWPRC_IDX",),
        "close": ("CLSPRC_IDX",),
        "volume_thousand_shares": ("ACC_TRDVOL",),
        "trading_value_million_krw": ("ACC_TRDVAL",),
        "market_cap_source_field": ("MKTCAP",),
    }
    # KRX Korean export columns are decoded by parse_csv. Position fallback is
    # restricted to the official index export schema and audited below.
    positions = {
        "date": 0,
        "close": 1,
        "open": 4,
        "high": 5,
        "low": 6,
        "volume_thousand_shares": 7,
        "trading_value_million_krw": 8,
        "market_cap_source_field": 9,
    }
    output: dict[str, pd.Series] = {}
    for target, candidates in aliases.items():
        source = next((column for column in candidates if column in frame.columns), None)
        if source is None:
            position = positions[target]
            if position >= len(frame.columns):
                raise ValueError(f"KOSPI100 지수 열 누락: {target}")
            source = frame.columns[position]
        output[target] = frame[source]
    result = pd.DataFrame(output)
    result["date"] = pd.to_datetime(
        result["date"].astype(str).str.replace("/", "-", regex=False), errors="raise"
    )
    for column in result.columns.difference(["date"]):
        result[column] = numeric(result[column])
    result = result.loc[result["date"].between(str(RAW_START), str(RAW_END))].copy()
    result["source_raw_file"] = path.relative_to(raw_root).as_posix()
    return result.sort_values("date", kind="mergesort").reset_index(drop=True)


def _gzip_csv(frame: pd.DataFrame, path: Path) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                frame.to_csv(text, index=False, lineterminator="\n", float_format="%.12g")


def _membership_spells(membership: pd.DataFrame, sessions: pd.DatetimeIndex) -> pd.DataFrame:
    session_index = pd.Series(np.arange(len(sessions)), index=sessions).to_dict()
    work = membership.sort_values(["ticker", "date"], kind="mergesort").copy()
    work["session_index"] = work["date"].map(session_index)
    if work["session_index"].isna().any():
        raise ValueError("구성종목 날짜가 지수 세션에 없습니다")
    new_spell = work.groupby("ticker", sort=False)["session_index"].diff().ne(1)
    work["spell_number"] = new_spell.groupby(work["ticker"], sort=False).cumsum().astype(int)
    work["membership_spell_id"] = work.apply(
        lambda row: f"{row['ticker']}:PRE2010:{int(row['spell_number']):02d}", axis=1
    )
    return work.drop(columns=["session_index", "spell_number"])


def _infer_resets(history: pd.DataFrame, sessions: pd.DatetimeIndex) -> pd.DataFrame:
    work = history.sort_values(["security_id", "date"], kind="mergesort").copy()
    session_index = pd.Series(np.arange(len(sessions)), index=sessions).to_dict()
    work["session_index"] = work["date"].map(session_index)
    previous_index = work.groupby("security_id", sort=False)["session_index"].shift(1)
    consecutive = work["session_index"].sub(previous_index).eq(1)
    previous_close = work.groupby("security_id", sort=False)["close"].shift(1)
    previous_shares = work.groupby("security_id", sort=False)["listed_shares"].shift(1)
    current_tradable = work[["open", "high", "low", "close"]].gt(0).all(axis=1) & work["volume"].fillna(0).gt(0)
    previous_tradable = current_tradable.groupby(work["security_id"], sort=False).shift(1)
    previous_tradable_flag = previous_tradable.astype("boolean").fillna(False).astype(bool)
    overnight_ratio = work["open"] / previous_close
    share_ratio = work["listed_shares"] / previous_shares
    discontinuity = consecutive & (
        (
            current_tradable
            & previous_tradable_flag
            & ((overnight_ratio < 0.75) | (overnight_ratio > 1.25))
        )
        | (
            current_tradable
            & previous_tradable_flag
            & ((share_ratio < 0.80) | (share_ratio > 1.25))
        )
        | current_tradable.ne(previous_tradable).fillna(False)
    ) & previous_close.notna()
    selected = work.loc[discontinuity, ["date", "security_id", "ticker", "name"]].copy()
    columns = [
        "canonical_event_id", "security_id", "ticker", "name", "event_type", "v21_bucket",
        "phase1_data_status", "feature_handling", "feature_boundary_date",
        "feature_boundary_source", "share_multiplier", "price_multiplier",
        "record_date_resolved", "listing_date", "effective_date", "issue_price_resolved",
        "portfolio_handling", "portfolio_terms_status", "confidence", "source_note",
        "first_filing_date", "last_filing_date", "primary_source", "production_reason",
    ]
    rows: list[dict[str, object]] = []
    for row in selected.itertuples(index=False):
        rows.append(
            {
                "canonical_event_id": f"P1C_INFERRED_RESET_{row.date:%Y%m%d}_{row.ticker}",
                "security_id": row.security_id,
                "ticker": row.ticker,
                "name": row.name,
                "event_type": "UNVERIFIED_DISCONTINUITY",
                "v21_bucket": "P1C_FAIL_CLOSED",
                "phase1_data_status": "FEATURE_RESET_ONLY",
                "feature_handling": "RESET_PRICE_CONTINUITY_AT_UNVERIFIED_ACTION",
                "feature_boundary_date": row.date,
                "feature_boundary_source": "RAW_OVERNIGHT_OR_LISTED_SHARES_DISCONTINUITY",
                "portfolio_handling": "ABORT_IF_HELD_UNVERIFIED",
                "portfolio_terms_status": "NOT_USED_BEFORE_2011_VALIDATION",
                "confidence": "CONSERVATIVE_INFERRED_BOUNDARY",
                "source_note": "KRX raw OHLCV/listed-shares discontinuity; no economic terms inferred",
                "primary_source": "KRX_RAW",
                "production_reason": "Prevent feature and forward-label continuity across an unresolved action",
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _manifest_row(path: Path, date_column: str) -> dict[str, object]:
    frame = pd.read_csv(path, usecols=[date_column])
    values = pd.to_datetime(frame[date_column], errors="coerce").dropna()
    if values.empty:
        raise ValueError(f"날짜 행이 없는 출력: {path.name}")
    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "date_column": date_column,
        "min_date": values.min().date().isoformat(),
        "max_date": values.max().date().isoformat(),
        "rows": len(frame),
    }


def build_partition(raw_root: Path, v24_root: Path, output_root: Path) -> dict[str, object]:
    raw_root = raw_root.resolve()
    v24_root = v24_root.resolve()
    output_root = output_root.resolve()
    forbidden = {"sealed", "final_oos_v24", "development"}
    if forbidden & {part.lower() for path in (raw_root, v24_root) for part in path.parts}:
        raise PermissionError("Phase 1C는 허용된 과거 원천과 2018년 이하 파티션만 사용합니다")
    source_partition = json.loads((v24_root / "partition.json").read_text(encoding="utf-8"))
    if source_partition.get("role") != "phase4b_train_internal" or source_partition.get("max_date") != "2018-12-31":
        raise PermissionError("감사된 v24 2018년 이하 파티션이 필요합니다")
    if output_root.exists():
        raise FileExistsError(f"기존 출력은 덮어쓰지 않습니다: {output_root}")

    index_files = sorted((raw_root / "raw" / "index_1034").glob("*.csv.gz"))
    if len(index_files) != 1:
        raise ValueError("2004~2010 KOSPI100 지수 원천 파일은 정확히 하나여야 합니다")
    early_index = _read_index(index_files[0], raw_root / "raw")
    sessions = pd.DatetimeIndex(early_index["date"].drop_duplicates().sort_values())
    membership_frames: list[pd.DataFrame] = []
    market_frames: list[pd.DataFrame] = []
    raw_files_read: list[dict[str, object]] = []
    for session in sessions:
        stamp = session.strftime("%Y%m%d")
        member_path = raw_root / "raw" / "membership_1034" / stamp[:4] / f"{stamp}.csv.gz"
        market_path = raw_root / "raw" / "market_all" / stamp[:4] / f"{stamp}.csv.gz"
        if not member_path.exists() or not market_path.exists():
            raise FileNotFoundError(f"PIT 입력 누락: {stamp}")
        membership_frames.append(_read_membership(member_path, session))
        market_frames.append(_read_market(market_path, session))
        for path in (member_path, market_path):
            raw_files_read.append(
                {"path": path.relative_to(raw_root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
            )
    membership = _membership_spells(pd.concat(membership_frames, ignore_index=True), sessions)
    counts = membership.groupby("date")["ticker"].nunique()
    if (counts < 99).any() or (counts > 100).any():
        raise ValueError("2004~2009 PIT 구성종목 수가 허용된 99~100 범위를 벗어났습니다")
    market = pd.concat(market_frames, ignore_index=True)
    member_tickers = set(membership["ticker"])
    early = market.loc[market["ticker"].isin(member_tickers)].copy()
    early["security_id"] = "KRX_COMMON:" + early["ticker"]
    early = early.merge(
        membership[["date", "ticker", "membership_spell_id"]],
        on=["date", "ticker"], how="left", validate="many_to_one",
    )
    early["is_member"] = early["membership_spell_id"].notna()
    early["eligible_new_entry"] = early["is_member"]
    early["tradable"] = (
        early[["open", "high", "low", "close"]].gt(0).all(axis=1)
        & early["volume"].fillna(0).gt(0)
    )
    early["feature_volume"] = early["volume"]
    early["feature_trading_value"] = early["trading_value"]
    early["price_usage_role"] = np.where(early["is_member"], "PIT_MEMBER_FEATURE_AND_EXECUTION", "HISTORY_OR_EXECUTION_ONLY")
    early["warmup_for_spell_ids"] = ""
    early["model_price_role"] = np.where(early["is_member"], "MODEL_ELIGIBLE", "PRE_ENTRY_WARMUP_ONLY")
    early["rank_eligible"] = early["is_member"] & early["tradable"]

    panel_columns = pd.read_csv(v24_root / "feature_price_panel.csv.gz", nrows=0).columns.tolist()
    full_columns = pd.read_csv(v24_root / "full_history_ohlcv.csv.gz", nrows=0).columns.tolist()
    early_panel = early.reindex(columns=panel_columns)
    early_full = early.reindex(columns=full_columns)
    old_panel = pd.read_csv(v24_root / "feature_price_panel.csv.gz", low_memory=False)
    old_full = pd.read_csv(v24_root / "full_history_ohlcv.csv.gz", low_memory=False)
    old_index = pd.read_csv(v24_root / "index_ohlcv.csv.gz", low_memory=False)
    old_actions = pd.read_csv(v24_root / "corporate_actions.csv.gz", low_memory=False)
    old_removals = pd.read_csv(v24_root / "removal_orders.csv.gz", low_memory=False)
    for frame in (old_panel, old_full, old_index):
        frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    old_panel = old_panel.loc[old_panel["date"].ge("2010-01-01")].copy()
    old_full = old_full.loc[old_full["date"].ge("2010-01-01")].copy()
    old_index = old_index.loc[old_index["date"].ge("2010-01-01")].copy()
    panel = pd.concat([early_panel, old_panel], ignore_index=True).sort_values(["date", "security_id"], kind="mergesort")
    full = pd.concat([early_full, old_full], ignore_index=True).sort_values(["date", "security_id"], kind="mergesort")
    if panel.duplicated(["date", "security_id"]).any() or full.duplicated(["date", "security_id"]).any():
        raise ValueError("2004~2018 결합 후 종목-날짜 중복이 있습니다")
    early_index_out = early_index.reindex(columns=old_index.columns)
    index = pd.concat([early_index_out, old_index], ignore_index=True).sort_values("date", kind="mergesort")
    inferred_actions = _infer_resets(early, sessions)
    actions = pd.concat([inferred_actions, old_actions], ignore_index=True).reindex(columns=old_actions.columns)
    for column in ("feature_boundary_date", "record_date_resolved", "listing_date", "effective_date", "first_filing_date", "last_filing_date"):
        actions[column] = pd.to_datetime(actions[column], errors="coerce").dt.strftime("%Y-%m-%d")

    output_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phase1c_", dir=output_root.parent) as temporary:
        staging = Path(temporary) / output_root.name
        staging.mkdir()
        outputs = {
            "feature_price_panel.csv.gz": panel,
            "full_history_ohlcv.csv.gz": full,
            "index_ohlcv.csv.gz": index,
            "corporate_actions.csv.gz": actions,
            "removal_orders.csv.gz": old_removals,
        }
        rows: list[dict[str, object]] = []
        for name, frame in outputs.items():
            _gzip_csv(frame, staging / name)
            rows.append(_manifest_row(staging / name, FILES[name]))
        with (staging / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["file", "bytes", "sha256", "date_column", "min_date", "max_date", "rows"], lineterminator="\n")
            writer.writeheader()
            writer.writerows(sorted(rows, key=lambda row: str(row["file"])))
        material = "\n".join(f"{row['file']}:{row['sha256']}" for row in sorted(rows, key=lambda row: str(row["file"])))
        data_hash = hashlib.sha256(material.encode("utf-8")).hexdigest()
        partition = {
            "version": "phase1c-2004-2018-partition-v1",
            "role": OUTPUT_ROLE,
            "min_date": RAW_START.isoformat(),
            "max_date": MAXIMUM_DATE.isoformat(),
            "data_hash": data_hash,
            "source": {
                "krx_raw_root": raw_root.as_posix(),
                "krx_index_sha256": sha256_file(index_files[0]),
                "v24_partition_data_hash": source_partition["data_hash"],
            },
            "selection": {"post_2021_rows_loaded": 0, "post_2018_rows_in_output": 0, "development_test_partition_created": False},
            "audit": {
                "actual_loaded_min_date": early_index["date"].min().date().isoformat(),
                "actual_loaded_max_early_date": early_index["date"].max().date().isoformat(),
                "raw_files_read": len(raw_files_read) + 1,
                "raw_file_inventory_sha256": hashlib.sha256(json.dumps(raw_files_read, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
                "membership_count_distribution": {str(int(key)): int(value) for key, value in counts.value_counts().sort_index().items()},
                "inferred_fail_closed_resets": len(inferred_actions),
                "corporate_action_terms_inferred": False,
                "filter_applied_after_model_load": False,
                "development_test_input_loaded": False,
                "final_oos_accessed": False,
            },
        }
        (staging / "partition.json").write_text(json.dumps(partition, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        staging.replace(output_root)
    return {"status": "PASS", "output_root": output_root.as_posix(), "data_hash": data_hash, "files": rows, "audit": partition["audit"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="2004~2010 KRX 원천과 v24를 결합한 2004~2018 내부 학습 파티션")
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--v24-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_partition(args.raw_root, args.v24_root, args.output_root), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
