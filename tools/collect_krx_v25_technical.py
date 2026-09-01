#!/usr/bin/env python3
"""KRX 기술 원천 데이터 수집기 (v25 준비용).

이 스크립트는 투자 신호를 계산하지 않는다. KOSPI 100의 PIT 구성종목,
전종목 일봉, KOSPI 100 지수 및 상장주식수 변화를 원천 자료로 보존한다.
PER/PBR/DIV 등 펀더멘털 조회 경로는 의도적으로 포함하지 않는다.

KRX Cookie는 실행 중 한 번만 ``getpass``로 받고 디스크, 로그, manifest에
기록하지 않는다. 중단 후 같은 명령을 다시 실행하면 완료된 날짜를 건너뛴다.

KOSPI 100 구성종목은 KRX [11006] 지수구성종목 화면과 같은 OTP endpoint를
거래일별로 직접 조회한다. --legacy-membership은 해당 요청이 비어 있거나
일시적으로 실패했을 때만 같은 날짜의 검증된 PIT snapshot을 보조로 쓰며,
현재 구성종목을 과거에 대체하는 fallback은 절대 하지 않는다.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from getpass import getpass
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

import pandas as pd


BASE = "https://data.krx.co.kr"
OTP_URL = f"{BASE}/comm/fileDn/GenerateOTP/generate.cmd"
DOWNLOAD_URL = f"{BASE}/comm/fileDn/download_csv/download.cmd"
MARKET_BLD = "dbms/MDC/STAT/standard/MDCSTAT01501"
INDEX_BLD = "dbms/MDC/STAT/standard/MDCSTAT00301"
MEMBERSHIP_BLD = "dbms/MDC/STAT/standard/MDCSTAT00601"
REFERER = "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201"
KOSPI100_CODE = "1034"
EXPANSION_END = date(2010, 12, 31)


class KRXError(RuntimeError):
    """KRX response is unavailable or violates the expected contract."""


class SessionExpired(KRXError):
    """The supplied browser session is no longer accepted by KRX."""


def clean_cookie(value: str) -> str:
    """Accept a Cookie header or Chrome's copied curl ``-b`` value safely."""
    value = value.strip()
    if value.lower().startswith("cookie:"):
        value = value.split(":", 1)[1].strip()
    match = re.search(r'-b\s+\^?"(.+?)"\^?\s*$', value, flags=re.IGNORECASE)
    if match:
        value = match.group(1)
    value = value.replace("^%", "%").replace('^"', '"').strip().strip('"')
    if "JSESSIONID=" not in value:
        raise KRXError("Cookie에 JSESSIONID가 없습니다. 브라우저에서 Cookie 전체를 복사하세요.")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def decode_krx(raw: bytes) -> str:
    for encoding in ("cp949", "euc-kr", "utf-8-sig", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise KRXError("KRX CSV 인코딩을 판별하지 못했습니다.")


def normalize_ticker(value: object) -> str | None:
    match = re.search(r"\d+", str(value).strip().replace('="', "").replace('"', ""))
    if not match:
        return None
    ticker = match.group(0)
    return ticker.zfill(6) if len(ticker) <= 6 else None


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).str.replace("+", "", regex=False).str.strip(),
        errors="coerce",
    )


def member_flag(series: pd.Series) -> pd.Series:
    """Accept both project booleans (True/False) and export flags (1/0)."""
    return series.astype(str).str.strip().str.casefold().isin({"1", "true", "t", "yes", "y"})


def canonical_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Map both KRX Korean CSV headers and JSON-style headers to one schema."""
    aliases = {
        "ticker": ("종목코드", "ISU_SRT_CD"),
        "name": ("종목명", "ISU_ABBRV"),
        "market": ("시장구분", "시장", "MKT_NM", "MKT_ID"),
        "open": ("시가", "TDD_OPNPRC"),
        "high": ("고가", "TDD_HGPRC"),
        "low": ("저가", "TDD_LWPRC"),
        "close": ("종가", "TDD_CLSPRC"),
        "volume": ("거래량", "ACC_TRDVOL"),
        "trading_value": ("거래대금", "ACC_TRDVAL"),
        "market_cap": ("시가총액", "MKTCAP"),
        "listed_shares": ("상장주식수", "LIST_SHRS"),
    }
    result: dict[str, pd.Series] = {}
    for target, candidates in aliases.items():
        source = next((column for column in candidates if column in frame.columns), None)
        if source is not None:
            result[target] = frame[source]
    required = {"ticker", "name", "open", "high", "low", "close", "volume", "trading_value"}
    missing = sorted(required - set(result))
    if missing:
        raise KRXError(f"전종목 CSV 필수 컬럼 누락: {missing}; 실제={list(frame.columns)}")
    output = pd.DataFrame(result)
    output["ticker"] = output["ticker"].map(normalize_ticker)
    output["name"] = output["name"].astype(str).str.strip()
    for column in ("open", "high", "low", "close", "volume", "trading_value", "market_cap", "listed_shares"):
        if column in output:
            output[column] = numeric(output[column])
    if "market" not in output:
        output["market"] = ""
    return output.dropna(subset=["ticker"]).drop_duplicates("ticker").reset_index(drop=True)


def parse_csv(raw: bytes) -> pd.DataFrame:
    text = decode_krx(raw).strip()
    if text.upper() == "LOGOUT":
        raise SessionExpired("KRX가 LOGOUT 응답을 반환했습니다.")
    if not text or "<html" in text[:1000].lower():
        raise KRXError("CSV 대신 빈 응답 또는 HTML을 받았습니다.")
    try:
        frame = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError as exc:
        raise KRXError("KRX가 빈 CSV를 반환했습니다.") from exc
    frame.columns = [str(column).replace("\ufeff", "").strip() for column in frame.columns]
    return frame


@dataclass(frozen=True)
class Download:
    raw: bytes
    url: str
    bld: str
    params: dict[str, str]


class KRXClient:
    def __init__(self, cookie: str, *, timeout_seconds: int = 45) -> None:
        self.cookie = clean_cookie(cookie)
        self.timeout_seconds = timeout_seconds
        self.opener = build_opener()

    def _post(self, url: str, data: dict[str, str], headers: dict[str, str]) -> bytes:
        encoded = urlencode(data).encode("utf-8")
        request = Request(url, data=encoded, headers=headers, method="POST")
        last: Exception | None = None
        for attempt in range(4):
            try:
                with self.opener.open(request, timeout=self.timeout_seconds) as response:
                    if response.status != 200:
                        raise KRXError(f"HTTP {response.status}")
                    return response.read()
            except (HTTPError, URLError, TimeoutError, KRXError) as exc:
                last = exc
                if attempt == 3:
                    break
                time.sleep(min(30.0, 2**attempt + random.uniform(0.15, 0.65)))
        raise KRXError(f"KRX 요청 실패: {last}")

    def download_csv(self, bld: str, params: dict[str, str]) -> Download:
        otp_params = {
            "locale": "ko_KR",
            "csvxls_isNo": "false",
            "name": "fileDown",
            "url": bld,
            **params,
        }
        common = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Cookie": self.cookie,
            "Origin": BASE,
            "Referer": REFERER,
        }
        otp = self._post(
            OTP_URL,
            otp_params,
            {**common, "Accept": "text/plain, */*; q=0.01", "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "X-Requested-With": "XMLHttpRequest"},
        ).decode("utf-8", errors="replace").strip()
        if otp.upper() == "LOGOUT":
            raise SessionExpired("OTP 단계에서 KRX 세션이 만료됐습니다.")
        if not otp or "<html" in otp.lower() or len(otp) < 20:
            raise KRXError(f"비정상 OTP 응답: {otp[:100]!r}")
        raw = self._post(
            DOWNLOAD_URL,
            {"code": otp},
            {**common, "Accept": "text/csv, */*", "Content-Type": "application/x-www-form-urlencoded"},
        )
        return Download(raw=raw, url=DOWNLOAD_URL, bld=bld, params=params)


def save_raw(root: Path, relative: Path, raw: bytes) -> Path:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return target
    with target.open("wb") as raw_handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0) as handle:
            handle.write(raw)
    return target


def load_legacy_membership(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise KRXError(f"legacy membership 파일이 없습니다: {path}")
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.columns = [str(column).replace("\ufeff", "").strip() for column in frame.columns]
    rename = {"기준일": "date", "날짜": "date", "종목코드": "ticker", "종목명": "name"}
    frame = frame.rename(columns={key: value for key, value in rename.items() if key in frame.columns and value not in frame.columns})
    if not {"date", "ticker"}.issubset(frame.columns):
        raise KRXError(f"legacy membership에는 date,ticker가 필요합니다: {list(frame.columns)}")
    if "is_member" in frame:
        frame = frame.loc[member_flag(frame["is_member"])].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame["ticker"] = frame["ticker"].map(normalize_ticker)
    frame["name"] = frame.get("name", "").astype(str).str.strip()
    return frame.dropna(subset=["date", "ticker"]).drop_duplicates(["date", "ticker"]).sort_values(["date", "ticker"])


def dates_between(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        if current.weekday() < 5:
            yield current
        current += timedelta(days=1)


def read_completed(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if re.fullmatch(r"\d{8}", line.strip())}


def append_completed(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{value}\n")


def write_csv_atomic(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def fetch_membership(client: KRXClient, session: date, raw_root: Path) -> pd.DataFrame:
    result = client.download_csv(
        MEMBERSHIP_BLD,
        {"trdDd": session.strftime("%Y%m%d"), "indIdx": KOSPI100_CODE[0], "indIdx2": KOSPI100_CODE[1:]},
    )
    save_raw(raw_root, Path("membership_1034") / f"{session:%Y}" / f"{session:%Y%m%d}.csv.gz", result.raw)
    frame = parse_csv(result.raw)
    ticker_column = next((column for column in ("종목코드", "ISU_SRT_CD") if column in frame.columns), None)
    name_column = next((column for column in ("종목명", "ISU_ABBRV") if column in frame.columns), None)
    if ticker_column is None:
        raise KRXError(f"구성종목 CSV에 종목코드가 없습니다: {list(frame.columns)}")
    output = pd.DataFrame({"date": pd.Timestamp(session), "ticker": frame[ticker_column].map(normalize_ticker)})
    output["name"] = frame[name_column].astype(str).str.strip() if name_column else ""
    return output.dropna(subset=["ticker"]).drop_duplicates(["date", "ticker"])


def legacy_snapshot(legacy: pd.DataFrame, session: date) -> pd.DataFrame:
    """Return an exact-date fallback only; never infer from an adjacent date."""
    return legacy.loc[legacy["date"].eq(pd.Timestamp(session)), ["date", "ticker", "name"]].copy()


def fetch_market(client: KRXClient, session: date, raw_root: Path) -> pd.DataFrame:
    result = client.download_csv(MARKET_BLD, {"trdDd": session.strftime("%Y%m%d"), "mktId": "ALL"})
    save_raw(raw_root, Path("market_all") / f"{session:%Y}" / f"{session:%Y%m%d}.csv.gz", result.raw)
    output = canonical_columns(parse_csv(result.raw))
    output.insert(0, "date", pd.Timestamp(session))
    return output


def fetch_index(client: KRXClient, start: date, end: date, raw_root: Path) -> pd.DataFrame:
    result = client.download_csv(
        INDEX_BLD,
        {"strtDd": start.strftime("%Y%m%d"), "endDd": end.strftime("%Y%m%d"), "indIdx": KOSPI100_CODE[0], "indIdx2": KOSPI100_CODE[1:]},
    )
    raw_file = save_raw(raw_root, Path("index_1034") / f"{start:%Y%m%d}_{end:%Y%m%d}.csv.gz", result.raw)
    frame = parse_csv(result.raw)
    aliases = {"date": ("일자", "TRD_DD"), "open": ("시가", "OPNPRC_IDX"), "high": ("고가", "HGPRC_IDX"), "low": ("저가", "LWPRC_IDX"), "close": ("종가", "CLSPRC_IDX"), "volume": ("거래량", "ACC_TRDVOL"), "trading_value": ("거래대금", "ACC_TRDVAL"), "market_cap": ("상장시가총액", "MKTCAP")}
    result_rows: dict[str, pd.Series] = {}
    for target, candidates in aliases.items():
        source = next((column for column in candidates if column in frame.columns), None)
        if source is None and target in {"date", "open", "high", "low", "close"}:
            raise KRXError(f"KOSPI100 지수 CSV에 {target} 열이 없습니다: {list(frame.columns)}")
        if source is not None:
            result_rows[target] = frame[source]
    output = pd.DataFrame(result_rows)
    output["date"] = pd.to_datetime(output["date"].astype(str).str.replace("/", "-", regex=False), errors="raise")
    for column in set(output.columns) - {"date"}:
        output[column] = numeric(output[column])
    output["index_code"] = KOSPI100_CODE
    output["source_raw_file"] = str(raw_file.relative_to(raw_root)).replace("\\", "/")
    return output.sort_values("date").reset_index(drop=True)


def validate_membership_coverage(membership: pd.DataFrame, sessions: Iterable[pd.Timestamp]) -> None:
    required_sessions = pd.DatetimeIndex(sessions).normalize()
    active = membership.loc[membership["date"].isin(required_sessions)]
    if active.empty:
        raise KRXError("요청 기간의 KOSPI100 구성종목이 하나도 없습니다.")
    counts = active.groupby("date")["ticker"].nunique().reindex(required_sessions, fill_value=0)
    bad = counts.loc[counts != 100]
    if not bad.empty:
        preview = ", ".join(f"{day.date()}={count}" for day, count in bad.head(5).items())
        raise KRXError(f"PIT 구성종목이 정확히 100개가 아닌 날짜가 있습니다: {preview}")


def build_manifest(root: Path, *, start: date, end: date, legacy_membership: Path | None, include_kosdaq: bool) -> None:
    files = []
    for path in sorted((root / "raw").rglob("*.gz")):
        files.append({"path": str(path.relative_to(root)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    payload = {
        "schema_version": "krx-technical-raw-v25-draft",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "coverage": {"start": start.isoformat(), "end": end.isoformat()},
        "universe": "KOSPI 100 point-in-time only",
        "market_raw_coverage": "KOSPI and KOSDAQ when KRX ALL response includes both" if include_kosdaq else "KOSPI only not supported by this ALL snapshot collector",
        "factor_policy": "OHLCV, trading value, KOSPI100 index and PIT KOSPI100 breadth only; no fundamentals collected",
        "legacy_membership": None if legacy_membership is None else {"path": str(legacy_membership), "sha256": sha256_file(legacy_membership)},
        "raw_files": files,
    }
    (root / "manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KRX Cookie 1회 입력 기술 원천 데이터 수집기")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2000, 1, 4))
    parser.add_argument("--end", type=date.fromisoformat, default=EXPANSION_END)
    parser.add_argument("--output-root", type=Path, default=Path("data/incoming/v25_krx_technical_raw"))
    parser.add_argument("--legacy-membership", type=Path, help="KRX [11006] 응답 실패 시 같은 날짜에만 쓸 PIT membership CSV (date,ticker[,name,is_member])")
    parser.add_argument("--delay", type=float, default=0.9, help="성공한 날짜 요청 사이의 최소 대기초")
    parser.add_argument("--skip-kosdaq", action="store_true", help="ALL 시장 스냅샷의 KOSDAQ 행을 정규화 출력에서 제외")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.start > args.end:
        raise SystemExit("--start는 --end보다 늦을 수 없습니다.")
    if args.end > EXPANSION_END:
        raise SystemExit("이 수집기는 기존 v24와 분리된 과거 확장(2010-12-31 이하) 전용입니다.")
    root: Path = args.output_root
    raw_root = root / "raw"
    normalized = root / "normalized"
    checkpoint = root / "checkpoints"
    root.mkdir(parents=True, exist_ok=True)
    cookie = getpass("KRX Cookie (입력은 화면에 표시·저장되지 않음): ")
    client = KRXClient(cookie)

    legacy = load_legacy_membership(args.legacy_membership) if args.legacy_membership else pd.DataFrame(columns=["date", "ticker", "name"])
    membership_rows: list[pd.DataFrame] = [legacy]
    audit: list[dict[str, Any]] = []
    completed = read_completed(checkpoint / "market_all_completed.txt")

    print(f"[시작] {args.start}~{args.end}; 출력={root.resolve()}")
    try:
        index = fetch_index(client, args.start, args.end, raw_root)
        for session in (value.date() for value in index["date"].sort_values().drop_duplicates()):
            key = session.strftime("%Y%m%d")
            if key in completed:
                continue
            market = fetch_market(client, session, raw_root)
            if args.skip_kosdaq and "market" in market:
                market = market.loc[~market["market"].astype(str).str.contains("KOSDAQ|코스닥|KSQ", case=False, regex=True)].copy()
            try:
                members = fetch_membership(client, session, raw_root)
                if len(members) != 100:
                    raise KRXError(
                        f"{session}: KRX [11006] 지수구성종목이 {len(members)}행을 반환했습니다; "
                        "PIT Universe는 정확히 100종목이어야 합니다."
                    )
            except KRXError as exc:
                members = legacy_snapshot(legacy, session)
                if len(members) != 100:
                    raise KRXError(
                        f"{session}: KRX [11006] 지수구성종목 조회 실패 및 같은 날짜 legacy PIT snapshot 부재 또는 100종목 불일치: {exc}"
                    ) from exc
                audit.append({"date": session.isoformat(), "issue": "MEMBERSHIP_KRX_FALLBACK", "detail": str(exc)})
            membership_rows.append(members)
            append_completed(checkpoint / "market_all_completed.txt", key)
            completed.add(key)
            print(f"[완료] {key} market={len(market):,}")
            time.sleep(max(0.0, args.delay) + random.uniform(0.0, 0.12))
    except SessionExpired as exc:
        print(f"[세션 만료] {exc}\n같은 명령을 다시 실행하면 완료 날짜를 건너뜁니다.", file=sys.stderr)
        return 7
    except KeyboardInterrupt:
        print("[중단] 완료 checkpoint는 보존됐습니다.", file=sys.stderr)
        return 130
    except KRXError as exc:
        print(f"[중단] {exc}", file=sys.stderr)
        return 8

    # 재실행 때도 앞선 실행에서 받은 raw 파일까지 다시 읽어 한 번의 완전한 정규화 결과를 만든다.
    market_from_raw: list[pd.DataFrame] = []
    for raw_file in sorted((raw_root / "market_all").rglob("*.csv.gz")):
        stamp = raw_file.stem.removesuffix(".csv")
        session = datetime.strptime(stamp, "%Y%m%d").date()
        if not args.start <= session <= args.end:
            continue
        with gzip.open(raw_file, "rb") as handle:
            frame = canonical_columns(parse_csv(handle.read()))
        frame.insert(0, "date", pd.Timestamp(session))
        market_from_raw.append(frame)
    membership_from_raw: list[pd.DataFrame] = []
    for raw_file in sorted((raw_root / "membership_1034").rglob("*.csv.gz")):
        stamp = raw_file.stem.removesuffix(".csv")
        session = datetime.strptime(stamp, "%Y%m%d").date()
        if not args.start <= session <= args.end:
            continue
        with gzip.open(raw_file, "rb") as handle:
            raw_frame = parse_csv(handle.read())
        ticker_column = next((column for column in ("종목코드", "ISU_SRT_CD") if column in raw_frame.columns), None)
        name_column = next((column for column in ("종목명", "ISU_ABBRV") if column in raw_frame.columns), None)
        if ticker_column is None:
            raise KRXError(f"저장된 구성종목 CSV에 종목코드가 없습니다: {raw_file}")
        frame = pd.DataFrame({"date": pd.Timestamp(session), "ticker": raw_frame[ticker_column].map(normalize_ticker)})
        frame["name"] = raw_frame[name_column].astype(str).str.strip() if name_column else ""
        membership_from_raw.append(frame.dropna(subset=["ticker"]))
    membership = pd.concat([*membership_rows, *membership_from_raw], ignore_index=True).drop_duplicates(["date", "ticker"]).sort_values(["date", "ticker"])
    validate_membership_coverage(membership, index["date"])
    market_all = pd.concat(market_from_raw, ignore_index=True).drop_duplicates(["date", "ticker"]).sort_values(["date", "ticker"])
    write_csv_atomic(normalized / "kospi100_membership_daily.csv", membership.to_dict("records"), ["date", "ticker", "name"])
    write_csv_atomic(normalized / "market_all_ohlcv.csv", market_all.to_dict("records"), list(market_all.columns))
    write_csv_atomic(normalized / "kospi100_index_ohlcv.csv", index.to_dict("records"), list(index.columns))
    write_csv_atomic(root / "audit_issues.csv", audit, ["date", "issue", "detail"])
    build_manifest(root, start=args.start, end=args.end, legacy_membership=args.legacy_membership, include_kosdaq=not args.skip_kosdaq)
    print("[완료] raw, normalized, audit_issues.csv, manifest.json을 작성했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
