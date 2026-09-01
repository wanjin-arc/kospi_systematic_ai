#!/usr/bin/env python3
"""KOSPI 200용 OpenDART 분기 재무제표 원천 수집기.

표준 전체 재무제표 API가 제공되는 2015년 이후만 수집한다. 응답의 접수번호를
공시목록의 접수일과 결합해 ``available_from``을 기록하며, 접수일을 확인하지
못한 응답은 모델 입력 가능 상태로 만들지 않는다. 중단 후 재실행과 요청 상한을
지원하고 API key는 저장하지 않는다.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path
from xml.etree import ElementTree


BASE = "https://opendart.fss.or.kr/api"
REPORT_CODES = ("11013", "11012", "11014", "11011")
MIN_STANDARD_YEAR = 2015
MAX_DEVELOPMENT_YEAR = 2023


class RequestLimitReached(RuntimeError):
    """정상 checkpoint 종료를 위한 실행별 요청 상한 신호."""


def request_bytes(endpoint: str, key: str, **params: str) -> bytes:
    query = urllib.parse.urlencode({"crtfc_key": key, **params})
    request = urllib.request.Request(f"{BASE}/{endpoint}?{query}", headers={"User-Agent": "kospi200-fundamental-research/2.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def request_json(endpoint: str, key: str, **params: str) -> dict:
    return json.loads(request_bytes(endpoint, key, **params).decode("utf-8"))


def load_tickers(membership_root: Path) -> set[str]:
    paths = sorted(membership_root.rglob("*.csv"))
    if not paths:
        raise FileNotFoundError(f"KOSPI 200 membership CSV가 없습니다: {membership_root}")
    tickers: set[str] = set()
    for path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                value = str(row.get("ticker", "")).strip()
                if value.isdigit() and len(value) <= 6:
                    tickers.add(value.zfill(6))
    if not tickers:
        raise RuntimeError("membership에서 종목코드를 찾지 못했습니다.")
    return tickers


def corp_code_mapping(key: str, root: Path) -> dict[str, dict[str, str]]:
    target = root / "corp_codes.xml.zip"
    if not target.exists():
        target.write_bytes(request_bytes("corpCode.xml", key))
    with zipfile.ZipFile(target) as archive:
        xml_name = next(name for name in archive.namelist() if name.lower().endswith(".xml"))
        document = ElementTree.fromstring(archive.read(xml_name))
    result: dict[str, dict[str, str]] = {}
    for node in document.findall("list"):
        ticker = (node.findtext("stock_code") or "").strip()
        if ticker.isdigit():
            result[ticker.zfill(6)] = {
                "corp_code": (node.findtext("corp_code") or "").strip(),
                "corp_name": (node.findtext("corp_name") or "").strip(),
                "modify_date": (node.findtext("modify_date") or "").strip(),
            }
    return result


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def disclosure_dates(payload: dict) -> dict[str, str]:
    if payload.get("status") in {"013", "020"}:
        return {}
    if payload.get("status") != "000":
        raise RuntimeError(f"DART 공시목록 오류: {payload.get('status')} {payload.get('message')}")
    return {
        str(row.get("rcept_no", "")): str(row.get("rcept_dt", ""))
        for row in payload.get("list", [])
        if row.get("rcept_no") and row.get("rcept_dt")
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KOSPI 200 OpenDART PIT 재무제표 수집기")
    parser.add_argument("--membership-root", type=Path, default=Path("data/incoming/v2_kospi200_membership_raw/normalized/membership_daily"))
    parser.add_argument("--output-root", type=Path, default=Path("data/incoming/v2_kospi200_dart_fundamentals_raw"))
    parser.add_argument("--start-year", type=int, default=MIN_STANDARD_YEAR)
    parser.add_argument("--end-year", type=int, default=MAX_DEVELOPMENT_YEAR)
    parser.add_argument("--max-requests", type=int, default=35000, help="0이면 실행 자체 상한 없음; DART 일일 한도는 별도 적용")
    parser.add_argument("--delay", type=float, default=0.18)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.start_year < MIN_STANDARD_YEAR:
        raise SystemExit("OpenDART 표준 전체 재무제표는 2015년 이후만 허용합니다.")
    if args.end_year > MAX_DEVELOPMENT_YEAR:
        raise SystemExit("v2 개발 수집기는 2023년 이후 또는 봉인 OOS를 수집하지 않습니다.")
    if args.start_year > args.end_year or args.max_requests < 0:
        raise SystemExit("연도 또는 --max-requests가 올바르지 않습니다.")

    key = getpass("OpenDART API key (입력은 저장·출력되지 않음): ").strip()
    if len(key) != 40:
        raise SystemExit("OpenDART API key는 40자리여야 합니다.")
    root = args.output_root
    root.mkdir(parents=True, exist_ok=True)
    tickers = load_tickers(args.membership_root)
    mapping = corp_code_mapping(key, root)
    requests_made = 0
    rows: list[dict[str, str]] = []

    def can_request() -> bool:
        return args.max_requests == 0 or requests_made < args.max_requests

    limit_reached = False
    try:
      for ticker in sorted(tickers):
        company = mapping.get(ticker)
        if not company:
            rows.append({"ticker": ticker, "status": "UNMAPPED_CURRENT_STOCK_CODE"})
            continue
        corp_code = company["corp_code"]
        for year in range(args.start_year, args.end_year + 1):
            list_path = root / "disclosures" / corp_code / f"{year}.json"
            if list_path.exists():
                listing = json.loads(list_path.read_text(encoding="utf-8"))
            else:
                if not can_request():
                    raise RequestLimitReached
                listing = request_json("list.json", key, corp_code=corp_code, bgn_de=f"{year}0101", end_de=f"{year}1231", page_count="100")
                requests_made += 1
                write_json(list_path, listing)
                time.sleep(args.delay)
            dates = disclosure_dates(listing)

            for report_code in REPORT_CODES:
                target = root / "financial_statements" / corp_code / str(year) / f"{report_code}.json"
                if target.exists():
                    payload = json.loads(target.read_text(encoding="utf-8"))
                else:
                    if not can_request():
                        raise RequestLimitReached
                    payload = request_json(
                        "fnlttSinglAcntAll.json", key, corp_code=corp_code,
                        bsns_year=str(year), reprt_code=report_code, fs_div="CFS",
                    )
                    requests_made += 1
                    if payload.get("status") == "013":
                        if not can_request():
                            raise RequestLimitReached
                        payload = request_json(
                            "fnlttSinglAcntAll.json", key, corp_code=corp_code,
                            bsns_year=str(year), reprt_code=report_code, fs_div="OFS",
                        )
                        requests_made += 1
                    receipt_numbers = sorted({str(item.get("rcept_no", "")) for item in payload.get("list", []) if item.get("rcept_no")})
                    availability = [dates[number] for number in receipt_numbers if number in dates]
                    payload["_audit"] = {
                        "ticker": ticker,
                        "corp_code": corp_code,
                        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                        "receipt_numbers": receipt_numbers,
                        "available_from": max(availability) if availability and len(availability) == len(receipt_numbers) else None,
                        "availability_status": "RESOLVED" if availability and len(availability) == len(receipt_numbers) else "UNRESOLVED_NOT_MODEL_ELIGIBLE",
                    }
                    write_json(target, payload)
                    time.sleep(args.delay)
                audit = payload.get("_audit", {})
                rows.append({
                    "ticker": ticker, "corp_code": corp_code, "year": str(year), "report_code": report_code,
                    "status": str(payload.get("status", "")), "available_from": str(audit.get("available_from") or ""),
                    "availability_status": str(audit.get("availability_status") or "LEGACY_FILE_REQUIRES_REPAIR"),
                    "path": str(target.relative_to(root)).replace("\\", "/"),
                })
                if requests_made and requests_made % 50 == 0:
                    print(f"requested={requests_made} ticker={ticker} year={year}", flush=True)
    except RequestLimitReached:
        limit_reached = True
        print(f"요청 상한 도달: {requests_made}; 저장 후 정상 종료합니다.", flush=True)

    with (root / "collection_audit.csv").open("w", encoding="utf-8", newline="") as handle:
        columns = ["ticker", "corp_code", "year", "report_code", "status", "available_from", "availability_status", "path"]
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    write_json(root / "manifest.json", {
        "schema_version": "kospi200-dart-fundamentals-raw-v2",
        "coverage": {"start_year": args.start_year, "end_year": args.end_year},
        "tickers": len(tickers), "requests_this_run": requests_made, "request_limit_reached": limit_reached,
        "api_key_stored": False, "protected_oos_accessed": False,
        "point_in_time_rule": "financial facts become eligible only on resolved DART receipt date",
        "limitations": ["Standard full-financial API coverage starts in 2015.", "Current stock-code mapping is not historical identity proof."],
    })
    print(f"완료: {root.resolve()} requests={requests_made} limit_reached={limit_reached}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
