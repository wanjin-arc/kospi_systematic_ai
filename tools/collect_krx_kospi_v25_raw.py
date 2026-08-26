#!/usr/bin/env python3
"""KRX 유가증권시장(STK) 일봉 원천자료 수집기.

이 스크립트는 KOSPI 전체 상장종목의 일별 원시 OHLCV와 KOSPI 지수를
수집한다. 수집 결과는 연구 입력이나 Factor가 아니며, 원본 그대로
``data/incoming`` 아래에 보존한다. KRX Cookie는 한 번만 묻고 저장하지 않는다.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import sys
from datetime import date, datetime, timezone
from getpass import getpass
from pathlib import Path
from types import ModuleType
from typing import Any

import pandas as pd


KOSPI_INDEX_CODE = "1001"
DEFAULT_START = date(2011, 1, 1)
DEFAULT_END = date(2025, 12, 31)


def _load_shared() -> ModuleType:
    """Load the sibling KRX transport implementation without package installation."""
    path = Path(__file__).with_name("collect_krx_v25_technical.py")
    spec = importlib.util.spec_from_file_location("krx_v25_shared", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"공통 KRX 수집기를 불러올 수 없습니다: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _completed(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip().isdigit()}


def _mark_completed(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(value + "\n")


def _fetch_index(shared: ModuleType, client: Any, start: date, end: date, raw_root: Path) -> pd.DataFrame:
    result = client.download_csv(
        shared.INDEX_BLD,
        {"strtDd": start.strftime("%Y%m%d"), "endDd": end.strftime("%Y%m%d"), "indIdx": "1", "indIdx2": "001"},
    )
    raw_path = shared.save_raw(raw_root, Path("index_1001") / f"{start:%Y%m%d}_{end:%Y%m%d}.csv.gz", result.raw)
    frame = shared.parse_csv(result.raw)
    aliases = {
        "date": ("일자", "TRD_DD"), "open": ("시가", "OPNPRC_IDX"), "high": ("고가", "HGPRC_IDX"),
        "low": ("저가", "LWPRC_IDX"), "close": ("종가", "CLSPRC_IDX"),
        "volume": ("거래량", "ACC_TRDVOL"), "trading_value": ("거래대금", "ACC_TRDVAL"),
    }
    values: dict[str, pd.Series] = {}
    for target, candidates in aliases.items():
        source = next((column for column in candidates if column in frame.columns), None)
        if source is None and target in {"date", "open", "high", "low", "close"}:
            raise shared.KRXError(f"KOSPI 지수 응답에 {target} 열이 없습니다: {list(frame.columns)}")
        if source is not None:
            values[target] = frame[source]
    output = pd.DataFrame(values)
    output["date"] = pd.to_datetime(output["date"].astype(str).str.replace("/", "-", regex=False), errors="raise")
    output["index_code"] = KOSPI_INDEX_CODE
    output["source_raw_file"] = str(raw_path.relative_to(raw_root)).replace("\\", "/")
    return output.sort_values("date").reset_index(drop=True)


def _fetch_kospi_market(shared: ModuleType, client: Any, session: date, raw_root: Path) -> int:
    result = client.download_csv(shared.MARKET_BLD, {"trdDd": session.strftime("%Y%m%d"), "mktId": "STK"})
    relative = Path("market_stk") / f"{session:%Y}" / f"{session:%Y%m%d}.csv.gz"
    shared.save_raw(raw_root, relative, result.raw)
    frame = shared.canonical_columns(shared.parse_csv(result.raw))
    if frame.empty:
        raise shared.KRXError(f"{session}: KOSPI 일별 시세가 비어 있습니다.")
    return len(frame)


def _write_manifest(root: Path, *, start: date, end: date, session_rows: dict[str, int]) -> None:
    raw_root = root / "raw"
    files = [
        {"path": str(path.relative_to(root)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": _sha256(path)}
        for path in sorted(raw_root.rglob("*.gz"))
    ]
    payload = {
        "schema_version": "krx-kospi-raw-v25-draft",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "coverage_requested": {"start": start.isoformat(), "end": end.isoformat()},
        "market": "KOSPI / KRX mktId=STK",
        "index": {"name": "KOSPI", "code": KOSPI_INDEX_CODE},
        "purpose": "raw_audit_and_optional_out_of_universe_research_only",
        "factor_policy": "Not an automatic KOSPI100 factor input; no fundamentals.",
        "session_row_counts": session_rows,
        "raw_files": files,
    }
    (root / "manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KRX KOSPI 전체 일봉 원천자료 수집기")
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START)
    parser.add_argument("--end", type=date.fromisoformat, default=DEFAULT_END)
    parser.add_argument("--output-root", type=Path, default=Path("data/incoming/v25_kospi_raw"))
    parser.add_argument("--delay", type=float, default=0.9)
    args = parser.parse_args(argv)
    if args.start > args.end:
        raise SystemExit("--start는 --end보다 늦을 수 없습니다.")

    shared = _load_shared()
    root = args.output_root
    raw_root = root / "raw"
    checkpoint = root / "checkpoints" / "market_stk_completed.txt"
    root.mkdir(parents=True, exist_ok=True)
    cookie = getpass("KRX Cookie (입력은 저장·출력되지 않음): ")
    client = shared.KRXClient(cookie)
    index = _fetch_index(shared, client, args.start, args.end, raw_root)
    sessions = [value.date() for value in index["date"].drop_duplicates().sort_values()]
    done = _completed(checkpoint)
    session_rows: dict[str, int] = {}
    for number, session in enumerate(sessions, start=1):
        key = session.strftime("%Y%m%d")
        if key in done:
            continue
        session_rows[key] = _fetch_kospi_market(shared, client, session, raw_root)
        _mark_completed(checkpoint, key)
        if number % 25 == 0:
            print(f"[진행] {number}/{len(sessions)} {session} rows={session_rows[key]}")
        if args.delay > 0:
            shared.time.sleep(args.delay)
    _write_manifest(root, start=args.start, end=args.end, session_rows=session_rows)
    print(f"완료: {root.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
