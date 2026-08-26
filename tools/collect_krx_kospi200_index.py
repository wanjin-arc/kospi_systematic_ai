#!/usr/bin/env python3
"""KRX [1028] KOSPI 200 일별 지수 OHLCV 수집기.

구성종목 snapshot을 다시 요청하지 않고 KRX 지수 endpoint만 한 번 호출한다.
Cookie는 실행 중에만 사용하며 저장하지 않는다. v2 개발 경계인 2023-12-31
이후 입력은 fail-closed로 거부한다.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from getpass import getpass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_krx_v25_technical as base  # noqa: E402


KOSPI200_CODE = "1028"
MAX_DEVELOPMENT_DATE = date(2023, 12, 31)


def guard_path(path: Path) -> None:
    parts = {part.casefold() for part in path.resolve().parts}
    if "sealed" in parts or "final_oos_v24" in parts:
        raise base.KRXError("봉인 OOS 경로는 지수 입력·출력에 사용할 수 없습니다.")


def index_params(start: date, end: date) -> dict[str, str]:
    return {
        "strtDd": start.strftime("%Y%m%d"),
        "endDd": end.strftime("%Y%m%d"),
        "indIdx": KOSPI200_CODE[0],
        "indIdx2": KOSPI200_CODE[1:],
    }


def _pick(frame: pd.DataFrame, *names: str) -> str | None:
    return next((name for name in names if name in frame.columns), None)


def parse_index(raw: bytes) -> pd.DataFrame:
    frame = base.parse_csv(raw)
    aliases = {
        "date": ("TRD_DD", "TRADE_DATE", "date", "일자"),
        "open": ("OPNPRC_IDX", "OPEN", "open", "시가"),
        "high": ("HGPRC_IDX", "HIGH", "high", "고가"),
        "low": ("LWPRC_IDX", "LOW", "low", "저가"),
        "close": ("CLSPRC_IDX", "CLOSE", "close", "종가"),
        "volume": ("ACC_TRDVOL", "VOLUME", "volume", "거래량"),
        "trading_value": ("ACC_TRDVAL", "TRADING_VALUE", "trading_value", "거래대금"),
        "market_cap": ("MKTCAP", "MARKET_CAP", "market_cap", "시가총액"),
    }
    selected: dict[str, pd.Series] = {}
    for target, names in aliases.items():
        source = _pick(frame, *names)
        if source is not None:
            selected[target] = frame[source]
    # KRX occasionally returns mojibake headers from a copied browser session.
    # The index export column order is fixed; positional fallback is accepted
    # only when the required first five fields are present and parseable.
    if not {"date", "open", "high", "low", "close"}.issubset(selected):
        if len(frame.columns) < 5:
            raise base.KRXError(f"KOSPI 200 지수 필수 열이 없습니다: {list(frame.columns)}")
        for target, source in zip(("date", "open", "high", "low", "close"), frame.columns[:5]):
            selected[target] = frame[source]
        if len(frame.columns) > 5:
            selected["volume"] = frame.iloc[:, 5]
        if len(frame.columns) > 6:
            selected["trading_value"] = frame.iloc[:, 6]
        if len(frame.columns) > 7:
            selected["market_cap"] = frame.iloc[:, 7]
    result = pd.DataFrame(selected)
    raw_dates = result["date"].astype(str).str.replace(r"[^0-9]", "", regex=True)
    result["date"] = pd.to_datetime(raw_dates, format="%Y%m%d", errors="coerce")
    for column in set(result.columns) - {"date"}:
        result[column] = base.numeric(result[column])
    required = ["date", "open", "high", "low", "close"]
    if result[required].isna().any().any() or result.empty:
        raise base.KRXError("KOSPI 200 지수 응답에 날짜 또는 OHLC 결측이 있습니다.")
    if (result[["open", "high", "low", "close"]] <= 0).any().any():
        raise base.KRXError("KOSPI 200 지수 OHLC에 0 이하 값이 있습니다.")
    result["index_code"] = KOSPI200_CODE
    return result.sort_values("date").drop_duplicates("date").reset_index(drop=True)


def _write_gzip_csv(path: Path, frame: pd.DataFrame) -> None:
    payload = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=handle, mtime=0) as compressed:
            compressed.write(payload)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KRX KOSPI 200 지수 OHLCV 수집")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2004, 1, 2))
    parser.add_argument("--end", type=date.fromisoformat, default=MAX_DEVELOPMENT_DATE)
    parser.add_argument("--output-root", type=Path, default=Path("data/incoming/v2_kospi200_index_raw"))
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.start > args.end:
        raise SystemExit("--start는 --end보다 늦을 수 없습니다.")
    if args.end > MAX_DEVELOPMENT_DATE:
        raise SystemExit("v2 개발 수집은 2023-12-31 이후를 허용하지 않습니다.")
    guard_path(args.output_root)
    normalized = args.output_root / "normalized" / "kospi200_index_ohlcv.csv.gz"
    manifest_path = args.output_root / "manifest.json"
    if normalized.exists() and not args.overwrite:
        raise SystemExit(f"기존 산출물이 있습니다. 덮어쓰려면 --overwrite를 사용하세요: {normalized}")
    client = base.KRXClient(getpass("KRX Cookie (입력은 저장·출력되지 않음): "))
    download = client.download_csv(base.INDEX_BLD, index_params(args.start, args.end))
    raw_path = base.save_raw(args.output_root / "raw", Path(f"index_{KOSPI200_CODE}/{args.start:%Y%m%d}_{args.end:%Y%m%d}.csv.gz"), download.raw)
    frame = parse_index(download.raw)
    _write_gzip_csv(normalized, frame)
    manifest = {
        "schema_version": "kospi200-index-krx-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "index_code": KOSPI200_CODE,
        "coverage_requested": {"start": args.start.isoformat(), "end": args.end.isoformat()},
        "coverage_returned": {"start": frame["date"].min().date().isoformat(), "end": frame["date"].max().date().isoformat()},
        "rows": int(len(frame)),
        "raw_file": {"path": str(raw_path.relative_to(args.output_root)).replace("\\", "/"), "bytes": raw_path.stat().st_size, "sha256": _sha256(raw_path)},
        "normalized_file": {"path": str(normalized.relative_to(args.output_root)).replace("\\", "/"), "bytes": normalized.stat().st_size, "sha256": _sha256(normalized)},
        "cookie_stored": False,
        "final_oos_accessed": False,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"output_root": str(args.output_root.resolve()), "index_code": KOSPI200_CODE, "rows": len(frame), "final_oos_accessed": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
