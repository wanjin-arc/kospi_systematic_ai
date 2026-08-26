#!/usr/bin/env python3
"""KOSPI 200 과거 DART 재무제표 원문 보존 수집기.

OpenDART의 표준 전체 재무제표 API는 이 저장소의 계약상 2015년부터만 사용한다.
이 도구는 그 이전(2011--2014)의 사업ㆍ반기ㆍ분기보고서 **원문 ZIP과 접수 메타데이터만**
재개 가능하게 내려받는다. 원문 텍스트를 Factor로 해석하거나 모델을 학습하지 않는다.

현재 stock_code -> corp_code 연결은 역사적 동일성 증명이 아니므로, 이 도구의 결과는
후속 identityㆍ계정 taxonomy 감사 전에는 모델 입력으로 사용할 수 없다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path
from xml.etree import ElementTree


BASE = "https://opendart.fss.or.kr/api"
MIN_LEGACY_YEAR = 2011
MAX_LEGACY_YEAR = 2014
FINANCIAL_WORDS = ("사업보고서", "반기보고서", "분기보고서")


class RequestLimitReached(RuntimeError):
    """The per-run request budget was exhausted after safe checkpoints."""


@dataclass(frozen=True)
class HttpResult:
    raw: bytes
    requests: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def looks_like_zip(raw: bytes) -> bool:
    return raw[:2] == b"PK"


def request_bytes(endpoint: str, key: str, *, retries: int = 3, **params: str) -> HttpResult:
    """Fetch one OpenDART endpoint and retry only transient transport failures.

    A response from OpenDART, including a quota/error JSON response, counts as one
    request. Credentials appear only in the in-memory query string and are never
    written to output files or error messages.
    """
    query = urllib.parse.urlencode({"crtfc_key": key, **params})
    request = urllib.request.Request(
        f"{BASE}/{endpoint}?{query}",
        headers={"User-Agent": "kospi200-legacy-dart-raw-collector/1.0"},
    )
    made = 0
    for attempt in range(retries):
        try:
            made += 1
            with urllib.request.urlopen(request, timeout=60) as response:
                return HttpResult(response.read(), made)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt + 1 == retries:
                raise RuntimeError(f"OpenDART 통신 실패({endpoint}): {exc.reason if isinstance(exc, urllib.error.URLError) else exc}") from exc
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def request_json(endpoint: str, key: str, **params: str) -> tuple[dict, int]:
    result = request_bytes(endpoint, key, **params)
    try:
        return json.loads(result.raw.decode("utf-8")), result.requests
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"OpenDART {endpoint} 응답이 JSON이 아닙니다.") from exc


def load_membership_tickers(root: Path, start_year: int, end_year: int) -> set[str]:
    paths = sorted(root.rglob("*.csv"))
    if not paths:
        raise FileNotFoundError(f"KOSPI 200 membership CSV가 없습니다: {root}")
    tickers: set[str] = set()
    for path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                day = str(row.get("date") or "")[:10]
                if not day or not day[:4].isdigit() or not start_year <= int(day[:4]) <= end_year:
                    continue
                ticker = str(row.get("ticker") or "").strip()
                if ticker.isdigit() and len(ticker) <= 6:
                    tickers.add(ticker.zfill(6))
    if not tickers:
        raise RuntimeError("지정한 기간의 membership에서 종목코드를 찾지 못했습니다.")
    return tickers


def load_or_download_corp_codes(key: str, root: Path, can_request) -> tuple[dict[str, dict[str, str]], int]:
    target = root / "corp_codes.xml.zip"
    made = 0
    if not target.exists():
        if not can_request():
            raise RequestLimitReached
        result = request_bytes("corpCode.xml", key)
        made += result.requests
        if not looks_like_zip(result.raw):
            raise RuntimeError("OpenDART corpCode.xml이 ZIP을 반환하지 않았습니다.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(result.raw)
    with zipfile.ZipFile(target) as archive:
        member = next(name for name in archive.namelist() if name.lower().endswith(".xml"))
        document = ElementTree.fromstring(archive.read(member))
    mapping: dict[str, dict[str, str]] = {}
    for node in document.findall("list"):
        ticker = (node.findtext("stock_code") or "").strip()
        if ticker.isdigit() and len(ticker) <= 6:
            mapping[ticker.zfill(6)] = {
                "corp_code": (node.findtext("corp_code") or "").strip(),
                "corp_name": (node.findtext("corp_name") or "").strip(),
                "modify_date": (node.findtext("modify_date") or "").strip(),
            }
    return mapping, made


def is_financial_report(row: dict) -> bool:
    name = str(row.get("report_nm") or "").replace(" ", "")
    return any(word in name for word in FINANCIAL_WORDS) and bool(str(row.get("rcept_no") or "").strip())


def report_kind(row: dict) -> str:
    name = str(row.get("report_nm") or "")
    if "사업보고서" in name:
        return "ANNUAL"
    if "반기보고서" in name:
        return "HALF"
    return "QUARTERLY"


def load_listing_or_fetch(key: str, root: Path, ticker: str, corp_code: str, year: int, can_request) -> tuple[list[dict], int, bool]:
    target = root / "disclosures" / corp_code / f"{year}.json"
    if target.exists():
        payload = json.loads(target.read_text(encoding="utf-8"))
        return list(payload.get("list") or []), 0, True
    if not can_request():
        raise RequestLimitReached
    payload, made = request_json(
        "list.json", key, corp_code=corp_code, bgn_de=f"{year}0101", end_de=f"{year}1231", pblntf_ty="A", page_count="100",
    )
    status = str(payload.get("status") or "")
    if status in {"013", "020"}:
        rows: list[dict] = []
    elif status == "000":
        rows = list(payload.get("list") or [])
    else:
        raise RuntimeError(f"OpenDART list.json 오류 {corp_code}/{year}: {status} {payload.get('message', '')}")
    write_json(target, {"ticker": ticker, "corp_code": corp_code, "year": year, "payload": payload, "list": rows})
    return rows, made, False


def document_target(root: Path, year: int, corp_code: str, receipt_no: str) -> Path:
    return root / "documents" / str(year) / corp_code / f"{receipt_no}.zip"


def fetch_document(key: str, target: Path, receipt_no: str, can_request) -> tuple[str, int, str]:
    if target.exists():
        with target.open("rb") as handle:
            if looks_like_zip(handle.read(4)):
                return "EXISTING_DOCUMENT", 0, ""
    if not can_request():
        raise RequestLimitReached
    result = request_bytes("document.xml", key, rcept_no=receipt_no)
    if looks_like_zip(result.raw):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(result.raw)
        return "DOWNLOADED_DOCUMENT", result.requests, ""
    # Preserve a bounded, credential-free diagnostic. Do not claim a failed payload is a document.
    error_path = target.with_suffix(".error.json")
    write_json(error_path, {
        "receipt_no": receipt_no,
        "status": "DOCUMENT_NONZIP_RESPONSE",
        "response_sha256": hashlib.sha256(result.raw).hexdigest(),
        "response_bytes": len(result.raw),
        "response_preview": result.raw[:500].decode("utf-8", errors="replace"),
    })
    return "DOCUMENT_NONZIP_RESPONSE", result.requests, str(error_path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KOSPI 200 2011~2014 DART 재무보고서 원문 수집기")
    parser.add_argument("--membership-root", type=Path, default=Path("data/incoming/v2_kospi200_membership_raw/normalized/membership_daily"))
    parser.add_argument("--output-root", type=Path, default=Path("data/incoming/v2_kospi200_dart_legacy_originals_raw"))
    parser.add_argument("--start-year", type=int, default=MIN_LEGACY_YEAR)
    parser.add_argument("--end-year", type=int, default=MAX_LEGACY_YEAR)
    parser.add_argument("--max-requests", type=int, default=3000, help="이번 실행의 새 HTTP 요청 상한(0은 금지)")
    parser.add_argument("--delay", type=float, default=0.25)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.start_year < MIN_LEGACY_YEAR or args.end_year > MAX_LEGACY_YEAR:
        raise SystemExit(f"이 수집기는 {MIN_LEGACY_YEAR}~{MAX_LEGACY_YEAR} 원문 전용입니다. 2015년 이후는 표준 수집기를 사용하십시오.")
    if args.start_year > args.end_year or args.max_requests <= 0 or args.delay < 0:
        raise SystemExit("연도, --max-requests 또는 --delay가 올바르지 않습니다.")

    key = getpass("OpenDART API key (입력은 저장·출력되지 않음): ").strip()
    if len(key) != 40:
        raise SystemExit("OpenDART API key는 40자리여야 합니다.")

    root = args.output_root
    root.mkdir(parents=True, exist_ok=True)
    tickers = load_membership_tickers(args.membership_root, args.start_year, args.end_year)
    requests_made = 0
    def can_request() -> bool:
        return requests_made < args.max_requests

    mapping, made = load_or_download_corp_codes(key, root, can_request)
    requests_made += made
    mapping_rows = []
    for ticker in sorted(tickers):
        item = mapping.get(ticker, {})
        mapping_rows.append({
            "ticker": ticker, **item,
            "mapping_status": "CURRENT_STOCK_CODE_MAPPING_NOT_PIT_CONFIRMED" if item else "UNMAPPED_CURRENT_STOCK_CODE",
        })
    with (root / "ticker_corp_mapping.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["ticker", "corp_code", "corp_name", "modify_date", "mapping_status"]
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(mapping_rows)

    audit_rows: list[dict[str, str]] = []
    reused_listings = downloaded = existing = nonzip = 0
    stopped = False
    try:
        for mapping_row in mapping_rows:
            corp_code = mapping_row.get("corp_code", "")
            if not corp_code:
                continue
            for year in range(args.start_year, args.end_year + 1):
                listing, made, reused = load_listing_or_fetch(key, root, mapping_row["ticker"], corp_code, year, can_request)
                requests_made += made
                reused_listings += int(reused)
                for row in sorted((item for item in listing if is_financial_report(item)), key=lambda item: str(item.get("rcept_no") or "")):
                    receipt_no = str(row["rcept_no"]).strip()
                    target = document_target(root, year, corp_code, receipt_no)
                    status, made, error_path = fetch_document(key, target, receipt_no, can_request)
                    requests_made += made
                    downloaded += int(status == "DOWNLOADED_DOCUMENT")
                    existing += int(status == "EXISTING_DOCUMENT")
                    nonzip += int(status == "DOCUMENT_NONZIP_RESPONSE")
                    audit_rows.append({
                        "ticker": mapping_row["ticker"], "corp_code": corp_code, "year": str(year), "rcept_no": receipt_no,
                        "rcept_dt": str(row.get("rcept_dt") or ""), "report_nm": str(row.get("report_nm") or ""),
                        "report_kind": report_kind(row), "is_correction": str("정정" in str(row.get("report_nm") or "")).lower(),
                        "document_status": status, "document_path": str(target.relative_to(root)).replace("\\", "/") if status != "DOCUMENT_NONZIP_RESPONSE" else "",
                        "error_path": str(Path(error_path).relative_to(root)).replace("\\", "/") if error_path else "",
                        "factor_usage": "FORBIDDEN_UNTIL_IDENTITY_AND_NUMERIC_ACCOUNT_AUDIT",
                    })
                    if made:
                        time.sleep(args.delay)
                if made:
                    time.sleep(args.delay)
    except RequestLimitReached:
        stopped = True

    audit_rows.sort(key=lambda row: (row["rcept_dt"], row["ticker"], row["rcept_no"]))
    audit_path = root / "document_audit.csv"
    fields = ["ticker", "corp_code", "year", "rcept_no", "rcept_dt", "report_nm", "report_kind", "is_correction", "document_status", "document_path", "error_path", "factor_usage"]
    with audit_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(audit_rows)
    files = [
        {"path": str(path.relative_to(root)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(root.rglob("*")) if path.is_file()
    ]
    write_json(root / "manifest.json", {
        "schema_version": "kospi200-legacy-dart-originals-raw-v1",
        "purpose": "raw_document_collection_only_not_factor_or_model_input",
        "coverage": {"start_year": args.start_year, "end_year": args.end_year},
        "tickers_in_historical_membership": len(tickers), "current_corp_code_mapped": sum(bool(row.get("corp_code")) for row in mapping_rows),
        "requests_this_run": requests_made, "request_budget": args.max_requests, "request_limit_reached": stopped,
        "reused_listing_files": reused_listings, "downloaded_documents": downloaded, "existing_documents_reused": existing, "nonzip_document_responses": nonzip,
        "api_key_stored": False, "protected_oos_accessed": False,
        "identity_status": "CURRENT_CODE_MAPPING_NOT_PIT_CONFIRMED",
        "factor_usage": "FORBIDDEN_UNTIL_FOLLOWUP_NUMERIC_ACCOUNT_NORMALIZATION_AND_PIT_AUDIT",
        "files": files,
    })
    print(json.dumps({
        "output_root": str(root.resolve()), "requests_this_run": requests_made, "request_limit_reached": stopped,
        "downloaded_documents": downloaded, "existing_documents_reused": existing, "nonzip_document_responses": nonzip,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
