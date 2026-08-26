#!/usr/bin/env python3
"""KOSPI 200 PIT 구성종목 전용 수집기.

기존 KOSPI 전체 일봉 원천자료의 파일명에서 거래일만 얻고 KRX [11006]과 같은
지수구성종목 endpoint만 거래일별로 조회한다. 기존 OHLCV를 다시 다운로드하지
않는다. KOSPI 200 지수는 필요할 때만 ``--include-index``로 별도 1회 요청한다.
Cookie는 한 번만 입력받고 저장하지 않는다. 2024년 이후 및 기존 봉인 OOS는 이
수집기의 허용 범위가 아니다. 중단 후 재실행하면 완료된 거래일을 건너뛴다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timezone
from getpass import getpass
from pathlib import Path
from typing import Sequence

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_krx_v25_technical as base  # noqa: E402


KOSPI200_CODE = "1028"
MAX_DEVELOPMENT_DATE = date(2023, 12, 31)


def index_params(start: date, end: date) -> dict[str, str]:
    return {
        "strtDd": start.strftime("%Y%m%d"),
        "endDd": end.strftime("%Y%m%d"),
        "indIdx": KOSPI200_CODE[0],
        "indIdx2": KOSPI200_CODE[1:],
    }


def membership_params(session: date) -> dict[str, str]:
    return {
        "trdDd": session.strftime("%Y%m%d"),
        "indIdx": KOSPI200_CODE[0],
        "indIdx2": KOSPI200_CODE[1:],
    }


def parse_membership(raw: bytes, session: date) -> pd.DataFrame:
    frame = base.parse_csv(raw)
    ticker_col = next((c for c in ("종목코드", "ISU_SRT_CD") if c in frame.columns), None)
    name_col = next((c for c in ("종목명", "ISU_ABBRV") if c in frame.columns), None)
    if ticker_col is None:
        raise base.KRXError(f"KOSPI 200 구성종목 코드 열이 없습니다: {list(frame.columns)}")
    result = pd.DataFrame({"date": pd.Timestamp(session), "ticker": frame[ticker_col].map(base.normalize_ticker)})
    result["name"] = frame[name_col].astype(str).str.strip() if name_col else ""
    result = result.dropna(subset=["ticker"]).drop_duplicates(["date", "ticker"]).sort_values("ticker")
    # KRX의 정기·수시 교체 경계에서는 편입 종목이 먼저 반영되어
    # 일시적으로 201~202개가 반환될 수 있다. 공식 응답을 임의 삭제하지
    # 않고 전환 구간을 보존하되, 과도한 응답은 비정상으로 차단한다.
    if len(result) > 205:
        raise base.KRXError(f"{session}: 비정상 KOSPI 200 구성종목 수 {len(result)}")
    return result


def parse_index(raw: bytes) -> pd.DataFrame:
    frame = base.parse_csv(raw)
    aliases = {
        "date": ("일자", "TRD_DD"), "open": ("시가", "OPNPRC_IDX"),
        "high": ("고가", "HGPRC_IDX"), "low": ("저가", "LWPRC_IDX"),
        "close": ("종가", "CLSPRC_IDX"), "volume": ("거래량", "ACC_TRDVOL"),
        "trading_value": ("거래대금", "ACC_TRDVAL"), "market_cap": ("상장시가총액", "MKTCAP"),
    }
    output: dict[str, pd.Series] = {}
    for target, candidates in aliases.items():
        source = next((c for c in candidates if c in frame.columns), None)
        if source is None and target in {"date", "open", "high", "low", "close"}:
            raise base.KRXError(f"KOSPI 200 지수 필수 열 누락: {target}")
        if source is not None:
            output[target] = frame[source]
    result = pd.DataFrame(output)
    result["date"] = pd.to_datetime(result["date"].astype(str).str.replace("/", "-", regex=False), errors="raise")
    for column in set(result.columns) - {"date"}:
        result[column] = base.numeric(result[column])
    result["index_code"] = KOSPI200_CODE
    return result.sort_values("date").reset_index(drop=True)


def sessions_from_existing_ohlcv(roots: Path | Sequence[Path], start: date, end: date) -> list[date]:
    """기존 일봉 파일명만 이용해 KRX 요청 대상 거래일을 확정한다."""
    if isinstance(roots, Path):
        roots = [roots]
    roots = list(roots)
    if not roots:
        raise base.KRXError("sessions-root가 하나 이상 필요합니다.")
    root = roots[0]
    if "sealed" in {part.casefold() for part in root.parts}:
        raise base.KRXError("봉인 OOS 경로를 sessions-root로 사용할 수 없습니다.")
    if not root.exists():
        raise FileNotFoundError(f"기존 KOSPI 일봉 경로가 없습니다: {root}")
    sessions: set[date] = set()
    for root in roots:
        if "sealed" in {part.casefold() for part in root.parts}:
            raise base.KRXError("봉인 OOS 경로를 sessions-root로 사용할 수 없습니다.")
        if not root.exists():
            raise FileNotFoundError(f"기존 KOSPI 일봉 경로가 없습니다: {root}")
        for path in root.rglob("*.csv.gz"):
            match = re.search(r"(\d{8})\.csv\.gz$", path.name)
            if not match:
                continue
            value = datetime.strptime(match.group(1), "%Y%m%d").date()
            if start <= value <= end:
                sessions.add(value)
    if not sessions:
        raise base.KRXError("기존 KOSPI 일봉 파일명에서 요청 기간 거래일을 찾지 못했습니다.")
    return sorted(sessions)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KOSPI 200 PIT 구성종목 전용 수집기")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2004, 1, 2))
    parser.add_argument("--end", type=date.fromisoformat, default=MAX_DEVELOPMENT_DATE)
    parser.add_argument("--output-root", type=Path, default=Path("data/incoming/v2_kospi200_membership_raw"))
    parser.add_argument("--sessions-root-extra", type=Path, action="append", default=[], help="추가 기존 KOSPI 일봉 경로(반복 지정 가능)")
    parser.add_argument("--sessions-root", type=Path, default=Path("data/incoming/v25_kospi_raw/raw/market_stk"), help="이미 보유한 KOSPI 전체 일봉 파일 디렉터리; 파일명 날짜만 사용")
    parser.add_argument("--include-index", action="store_true", help="필요 시 KOSPI 200 지수 1개 CSV를 추가 수집")
    parser.add_argument("--delay", type=float, default=0.9)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.start > args.end:
        raise SystemExit("--start는 --end보다 늦을 수 없습니다.")
    if args.end > MAX_DEVELOPMENT_DATE:
        raise SystemExit("v2 개발 수집기는 2023-12-31 이후 또는 봉인 OOS를 수집하지 않습니다.")

    root = args.output_root
    raw_root = root / "raw"
    normalized = root / "normalized"
    checkpoint = root / "checkpoints" / "completed_sessions.txt"
    skipped_empty = root / "checkpoints" / "skipped_empty_sessions.txt"
    root.mkdir(parents=True, exist_ok=True)
    client = base.KRXClient(getpass("KRX Cookie (입력은 저장·출력되지 않음): "))

    session_roots = [args.sessions_root, *args.sessions_root_extra]
    sessions = sessions_from_existing_ohlcv(session_roots, args.start, args.end)
    completed = base.read_completed(checkpoint)
    skipped = base.read_completed(skipped_empty)

    for number, session in enumerate(sessions, start=1):
        key = session.strftime("%Y%m%d")
        if key in completed or key in skipped:
            continue
        membership_download = client.download_csv(base.MEMBERSHIP_BLD, membership_params(session))
        membership_path = base.save_raw(raw_root, Path("membership_1028") / f"{session:%Y}" / f"{key}.csv.gz", membership_download.raw)
        members = parse_membership(membership_download.raw, session)
        if members.empty:
            base.append_completed(skipped_empty, key)
            print(f"[{number}/{len(sessions)}] {session} members=0 (KRX 빈 응답, 제외 기록)", flush=True)
            time.sleep(args.delay)
            continue

        member_target = normalized / "membership_daily" / f"{session:%Y}" / f"{key}.csv"
        base.write_csv_atomic(member_target, members.to_dict("records"), ["date", "ticker", "name"])
        base.append_completed(checkpoint, key)
        print(f"[{number}/{len(sessions)}] {session} members={len(members)}", flush=True)
        time.sleep(args.delay)

    normalized.mkdir(parents=True, exist_ok=True)
    if args.include_index:
        index_download = client.download_csv(base.INDEX_BLD, index_params(args.start, args.end))
        base.save_raw(raw_root, Path("index_1028") / f"{args.start:%Y%m%d}_{args.end:%Y%m%d}.csv.gz", index_download.raw)
        index = parse_index(index_download.raw)
        base.write_csv_atomic(normalized / "kospi200_index_ohlcv.csv", index.to_dict("records"), list(index.columns))
    files = [
        {"path": str(path.relative_to(root)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": base.sha256_file(path)}
        for path in sorted(raw_root.rglob("*.gz"))
    ]
    manifest = {
        "schema_version": "kospi200-krx-raw-v2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "universe": "KOSPI 200 point-in-time",
        "index_code": KOSPI200_CODE,
        "coverage": {"start": args.start.isoformat(), "end": args.end.isoformat()},
        "session_source": {"paths": [str(path) for path in session_roots], "files_read": False, "sessions": len(sessions)},
        "existing_kospi_ohlcv_reused": True,
        "kospi200_index_collected": bool(args.include_index),
        "protected_oos_accessed": False,
        "cookie_stored": False,
        "raw_files": files,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"완료: {root.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
