#!/usr/bin/env python3
"""KRX 날짜별 KOSPI 업종분류 PIT 스냅샷 수집기.

기존 KOSPI 전종목 일봉 파일의 날짜만 사용하고, OHLCV를 다시 받지 않는다.
KRX 업종분류 현황(MDCSTAT03901)을 같은 날짜로 요청해 ticker·업종코드·업종명을
raw와 normalized 결과로 보존한다. 현재 분류를 과거 날짜에 소급하지 않으며,
중단 후 checkpoint를 이용해 재개한다.

주의: 2004~2023 전체 거래일을 요청하면 수천 건의 KRX 요청이 발생한다.
Cookie는 입력 중 저장·출력하지 않는다. 2024년 이후와 봉인 OOS 경로는 거부한다.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_krx_v25_technical as base  # noqa: E402
from collect_krx_kospi200_v2 import sessions_from_existing_ohlcv  # noqa: E402


SECTOR_BLD = "dbms/MDC/STAT/standard/MDCSTAT03901"
MAX_DATE = date(2023, 12, 31)


def guard_path(path: Path) -> None:
    """Reject sealed/OOS paths before touching any input or output."""
    parts = {part.casefold() for part in path.resolve().parts}
    if "sealed" in parts or "final_oos_v24" in parts:
        raise base.KRXError("Final OOS 경로는 수집기의 입력·출력으로 사용할 수 없습니다.")


def sector_params(session: date) -> dict[str, str]:
    return {"mktId": "STK", "trdDd": session.strftime("%Y%m%d"), "money": "1"}


def _column(frame: pd.DataFrame, candidates: tuple[str, ...], label: str) -> str:
    source = next((name for name in candidates if name in frame.columns), None)
    if source is None:
        raise base.KRXError(f"업종분류 응답에 {label} 열이 없습니다: {list(frame.columns)}")
    return source


def parse_sector(raw: bytes, session: date) -> pd.DataFrame:
    frame = base.parse_csv(raw)
    ticker_col = _column(frame, ("종목코드", "ISU_SRT_CD"), "종목코드")
    name_col = next((name for name in ("종목명", "ISU_ABBRV") if name in frame.columns), None)
    code_col = next((name for name in ("업종코드", "IDX_IND_CD", "SECT_TP_CD") if name in frame.columns), None)
    sector_col = _column(frame, ("업종", "업종명", "IDX_IND_NM", "SECT_TP_NM"), "업종명")
    # KRX's historical export commonly omits an industry code and returns
    # only 업종명.  Use the normalized name as a deterministic fallback; the
    # source flag makes it explicit that this is not an official KRX code.
    sector_values = frame[sector_col].astype(str).str.strip()
    if code_col is None:
        code_values = sector_values
        code_source = "derived_from_sector_name"
    else:
        code_values = frame[code_col].astype(str).str.strip()
        code_source = "krx"
    result = pd.DataFrame(
        {
            "date": session.isoformat(),
            "ticker": frame[ticker_col].map(base.normalize_ticker),
            "name": frame[name_col].astype(str).str.strip() if name_col else "",
            "sector_code": code_values,
            "sector_code_source": code_source,
            "sector": sector_values,
        }
    )
    result = result.dropna(subset=["ticker"])
    result = result.loc[(result["sector_code"] != "") & (result["sector"] != "")]
    result = result.drop_duplicates(["date", "ticker"], keep="last")
    if result.empty:
        raise base.KRXError(f"{session}: 업종분류 응답에 유효한 종목이 없습니다.")
    return result.sort_values("ticker", kind="mergesort").reset_index(drop=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KRX KOSPI 날짜별 업종분류 PIT 수집기")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--sessions-root", type=Path, default=Path("data/incoming/v25_kospi_raw/raw/market_stk"))
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.start > args.end or args.end > MAX_DATE:
        raise SystemExit(f"허용 기간은 시작일<=종료일이며 종료일은 {MAX_DATE} 이하여야 합니다.")
    guard_path(args.sessions_root)
    guard_path(args.output_root)
    if not args.sessions_root.exists():
        raise FileNotFoundError(f"sessions-root가 없습니다: {args.sessions_root}")

    sessions = sessions_from_existing_ohlcv(args.sessions_root, args.start, args.end)
    output_root = args.output_root
    raw_root = output_root / "raw"
    checkpoint = output_root / "checkpoints" / "completed_dates.txt"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    completed = {line.strip() for line in checkpoint.read_text(encoding="utf-8").splitlines()} if checkpoint.exists() else set()
    cookie = base.getpass("KRX Cookie (입력은 저장·출력되지 않음): ")
    client = base.KRXClient(cookie)
    normalized: list[pd.DataFrame] = []
    raw_files: list[Path] = []
    errors: list[dict[str, str]] = []
    for index, session in enumerate(sessions, 1):
        key = session.isoformat()
        if key in completed:
            path = raw_root / f"{session:%Y}" / f"{session:%Y%m%d}.csv.gz"
            if path.exists():
                raw_files.append(path)
                try:
                    # Re-parse the original compressed bytes so resume runs use
                    # exactly the same KRX encoding and parser path as fresh
                    # downloads.  Re-serializing a DataFrame can alter column
                    # names/quoting and would make the audit non-reproducible.
                    with gzip.open(path, "rb") as handle:
                        normalized.append(parse_sector(handle.read(), session))
                except Exception:
                    pass
            continue
        try:
            download = client.download_csv(SECTOR_BLD, sector_params(session))
            raw_path = base.save_raw(output_root, Path("raw") / f"{session:%Y}" / f"{session:%Y%m%d}.csv.gz", download.raw)
            parsed = parse_sector(download.raw, session)
            raw_files.append(raw_path)
            normalized.append(parsed)
            with checkpoint.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(key + "\n")
            completed.add(key)
            print(f"[{index}/{len(sessions)}] {key} rows={len(parsed)}", flush=True)
        except Exception as exc:
            errors.append({"date": key, "error": str(exc)})
            print(f"[{index}/{len(sessions)}] {key} ERROR={exc}", file=sys.stderr, flush=True)

    if normalized:
        combined = pd.concat(normalized, ignore_index=True).drop_duplicates(["date", "ticker"], keep="last")
        combined = combined.sort_values(["date", "ticker"], kind="mergesort")
        combined.to_csv(output_root / "sector_daily.csv.gz", index=False, compression={"method": "gzip", "mtime": 0}, lineterminator="\n")
    manifest = {
        "schema_version": "krx-kospi200-sector-pit-v1",
        "source_bld": SECTOR_BLD,
        "market": "KOSPI",
        "start": args.start.isoformat(),
        "end": args.end.isoformat(),
        "sessions_planned": len(sessions),
        "sessions_completed": len(completed),
        "normalized_rows": int(sum(len(frame) for frame in normalized)),
        "errors": errors,
        "final_oos_accessed": False,
        "raw_files": [{"file": str(path.relative_to(output_root).as_posix()), "sha256": _sha256(path), "bytes": path.stat().st_size} for path in sorted(set(raw_files))],
    }
    _write_json(output_root / "manifest.json", manifest)
    if errors:
        raise SystemExit(f"{len(errors)}개 날짜가 실패했습니다. checkpoint를 확인하고 재실행하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
