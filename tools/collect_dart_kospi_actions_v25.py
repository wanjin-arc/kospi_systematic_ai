#!/usr/bin/env python3
"""KOSPI 전종목의 DART 기업행동 감사 원천자료 수집기.

공시 내용은 투자 Factor로 사용하지 않는다. 이 스크립트는 KRX 일봉에서 확인된
종목코드에 대하여 공시 목록, 기업행동 후보의 원문 XML 및 OpenDART 구조화 응답을
보존한다. 최종적으로 가격/수량 보정을 결정하지 않으며, 사람의 감사 없이는
corporate_actions 테이블을 만들지 않는다.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
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
ACTION_WORDS = ("분할", "합병", "감자", "증자", "주식교환", "주식 이전", "상장폐지", "상장 폐지")
# Structured endpoints are supporting evidence only. Several cover recent years only;
# list.json plus document.xml remains the canonical raw record for older filings.
STRUCTURED_ENDPOINTS = {
    "paid_or_bonus_issue": "pifricDecsn.json",
    "capital_reduction": "crDecsn.json",
    "merger": "cmpMgDecsn.json",
    "company_split": "cmpDvDecsn.json",
    "split_merger": "cmpDvMgDecsn.json",
    "share_exchange_transfer": "stkExtrDecsn.json",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def request_bytes(url: str, params: dict[str, str], *, timeout: int = 60) -> bytes:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "kospi-systematic-ai audit collector/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def request_json(endpoint: str, key: str, **params: str) -> dict:
    raw = request_bytes(f"{BASE}/{endpoint}", {"crtfc_key": key, **params})
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"DART {endpoint} JSON 응답을 해석하지 못했습니다.") from exc


def load_krx_tickers(raw_root: Path) -> set[str]:
    """Read only KOSPI raw files produced by collect_krx_kospi_v25_raw.py."""
    market_root = raw_root / "raw" / "market_stk"
    if not market_root.exists():
        raise FileNotFoundError(f"KRX KOSPI raw 경로가 없습니다: {market_root}")
    cache = raw_root / "ticker_universe.csv"
    if cache.exists():
        with cache.open("r", encoding="utf-8", newline="") as handle:
            cached = {row["ticker"].strip().zfill(6) for row in csv.DictReader(handle) if row.get("ticker", "").strip()}
        if cached:
            print(f"[로컬 재사용] KRX 종목코드 {len(cached)}개: {cache}", flush=True)
            return cached
    tickers: set[str] = set()
    paths = sorted(market_root.rglob("*.csv.gz"))
    print(f"[로컬 스캔 시작] KRX 파일 {len(paths)}개에서 종목코드를 읽습니다.", flush=True)
    for number, path in enumerate(paths, start=1):
        with gzip.open(path, "rt", encoding="cp949", newline="") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            for row in reader:
                if row and row[0].strip().isdigit() and len(row[0].strip()) <= 6:
                    tickers.add(row[0].strip().zfill(6))
        if number % 100 == 0 or number == len(paths):
            print(f"[로컬 스캔] {number}/{len(paths)} files, tickers={len(tickers)}", flush=True)
    if not tickers:
        raise RuntimeError("KRX 원시 파일에서 KOSPI 종목코드를 찾지 못했습니다.")
    with cache.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ticker"])
        writer.writeheader()
        writer.writerows({"ticker": ticker} for ticker in sorted(tickers))
    print(f"[로컬 저장] KRX 종목코드 {len(tickers)}개: {cache}", flush=True)
    return tickers


def download_corp_codes(key: str, output_root: Path) -> dict[str, dict[str, str]]:
    target = output_root / "corp_codes.xml.zip"
    if not target.exists():
        target.write_bytes(request_bytes(f"{BASE}/corpCode.xml", {"crtfc_key": key}))
    with zipfile.ZipFile(target) as archive:
        xml_name = next(name for name in archive.namelist() if name.lower().endswith(".xml"))
        root = ElementTree.fromstring(archive.read(xml_name))
    mapping: dict[str, dict[str, str]] = {}
    for node in root.findall("list"):
        stock_code = (node.findtext("stock_code") or "").strip()
        if stock_code.isdigit() and len(stock_code) <= 6:
            mapping[stock_code.zfill(6)] = {
                "corp_code": (node.findtext("corp_code") or "").strip(),
                "corp_name": (node.findtext("corp_name") or "").strip(),
                "modify_date": (node.findtext("modify_date") or "").strip(),
            }
    return mapping


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def list_filings(key: str, corp_code: str, year: int) -> list[dict]:
    payload = request_json(
        "list.json", key, corp_code=corp_code, bgn_de=f"{year}0101", end_de=f"{year}1231", page_count="100"
    )
    if payload.get("status") in {"013", "020"}:  # no data / no recent data
        return []
    if payload.get("status") != "000":
        raise RuntimeError(f"DART list.json {corp_code}/{year}: {payload.get('status')} {payload.get('message')}")
    return list(payload.get("list") or [])


def is_action_candidate(item: dict) -> bool:
    text = " ".join(str(item.get(key, "")) for key in ("report_nm", "rm")).replace("·", " ")
    return any(word.replace(" ", "") in text.replace(" ", "") for word in ACTION_WORDS)


def save_document(key: str, receipt_no: str, output_root: Path) -> tuple[str, str, str]:
    """Archive an original filing when available without discarding its candidate.

    Older or corrected DART filings can legally return an API error payload instead
    of a ZIP.  That is an audit finding, not a reason to lose all later filings.
    """
    target = output_root / "documents" / f"{receipt_no}.zip"
    if target.exists():
        return str(target.relative_to(output_root)).replace("\\", "/"), "DOCUMENT_ARCHIVED", ""
    error_path = output_root / "document_errors" / f"{receipt_no}.json"
    if error_path.exists():
        return "", "DOCUMENT_UNAVAILABLE", str(error_path.relative_to(output_root)).replace("\\", "/")
    raw = request_bytes(f"{BASE}/document.xml", {"crtfc_key": key, "rcept_no": receipt_no})
    if raw[:2] == b"PK":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        return str(target.relative_to(output_root)).replace("\\", "/"), "DOCUMENT_ARCHIVED", ""
    write_json(
        error_path,
        {
            "receipt_no": receipt_no,
            "status": "DOCUMENT_UNAVAILABLE",
            "response": raw.decode("utf-8", errors="replace"),
        },
    )
    return "", "DOCUMENT_UNAVAILABLE", str(error_path.relative_to(output_root)).replace("\\", "/")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KOSPI DART 기업행동 감사 원천자료 수집기")
    parser.add_argument("--krx-raw-root", type=Path, default=Path("data/incoming/v25_kospi_raw"))
    parser.add_argument("--start-year", type=int, default=2011)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--output-root", type=Path, default=Path("data/incoming/v25_kospi_dart_audit_raw"))
    parser.add_argument("--structured", action="store_true", help="후보 법인·연도에 대해 OpenDART 구조화 주요사항 API 응답도 보존")
    parser.add_argument("--delay", type=float, default=0.15)
    args = parser.parse_args(argv)
    if args.start_year > args.end_year:
        raise SystemExit("--start-year는 --end-year보다 클 수 없습니다.")

    key = getpass("OpenDART API key (입력은 저장·출력되지 않음): ").strip()
    if len(key) != 40:
        raise SystemExit("OpenDART API key는 40자리여야 합니다.")
    root = args.output_root
    root.mkdir(parents=True, exist_ok=True)
    print("[1/4] 기존 KRX 원시자료 확인 중...", flush=True)
    tickers = load_krx_tickers(args.krx_raw_root)
    print("[2/4] DART 법인코드 확인 중...", flush=True)
    corp_codes = download_corp_codes(key, root)
    mapping_rows = []
    for ticker in sorted(tickers):
        current = corp_codes.get(ticker, {})
        mapping_rows.append({"ticker": ticker, **current, "mapping_status": "CURRENT_CODE_ONLY" if current else "UNMAPPED"})
    with (root / "ticker_corp_mapping.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ticker", "corp_code", "corp_name", "modify_date", "mapping_status"])
        writer.writeheader(); writer.writerows(mapping_rows)
    print(f"[3/4] 공시목록 수집 시작: {len(mapping_rows)} tickers, 기존 파일은 재사용", flush=True)

    candidates: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    structured_done: set[tuple[str, int]] = set()
    for row in mapping_rows:
        if not row.get("corp_code"):
            continue
        for year in range(args.start_year, args.end_year + 1):
            disclosure_path = root / "disclosures" / row["corp_code"] / f"{year}.json"
            if disclosure_path.exists():
                listing = list(json.loads(disclosure_path.read_text(encoding="utf-8")).get("list") or [])
            else:
                listing = list_filings(key, row["corp_code"], year)
                write_json(disclosure_path, {"ticker": row["ticker"], "corp_code": row["corp_code"], "year": year, "list": listing})
            for item in listing:
                receipt_no = str(item.get("rcept_no", "")).strip()
                if not receipt_no or not is_action_candidate(item) or (row["ticker"], receipt_no) in seen:
                    continue
                seen.add((row["ticker"], receipt_no))
                document_path, document_status, document_error_path = save_document(key, receipt_no, root)
                candidates.append({
                    "ticker": row["ticker"], "corp_code": row["corp_code"], "rcept_no": receipt_no,
                    "rcept_dt": str(item.get("rcept_dt", "")), "report_nm": str(item.get("report_nm", "")),
                    "rm": str(item.get("rm", "")), "document_zip": document_path,
                    "document_status": document_status, "document_error_json": document_error_path,
                    "classification": "UNREVIEWED_CANDIDATE_NOT_A_MECHANICAL_ACTION",
                })
                if args.structured and (row["corp_code"], year) not in structured_done:
                    structured_done.add((row["corp_code"], year))
                    for label, endpoint in STRUCTURED_ENDPOINTS.items():
                        structured_path = root / "structured" / label / row["corp_code"] / f"{year}.json"
                        if not structured_path.exists():
                            response = request_json(endpoint, key, corp_code=row["corp_code"], bgn_de=f"{year}0101", end_de=f"{year}1231")
                            write_json(structured_path, response)
                        time.sleep(args.delay)
            time.sleep(args.delay)
    with (root / "corporate_action_candidates.csv").open("w", encoding="utf-8", newline="") as handle:
        columns = ["ticker", "corp_code", "rcept_no", "rcept_dt", "report_nm", "rm", "document_zip", "document_status", "document_error_json", "classification"]
        writer = csv.DictWriter(handle, fieldnames=columns); writer.writeheader(); writer.writerows(sorted(candidates, key=lambda x: (x["rcept_dt"], x["ticker"], x["rcept_no"])))
    print("[4/4] manifest 작성 중...", flush=True)
    files = [{"path": str(path.relative_to(root)).replace("\\", "/"), "sha256": sha256_file(path), "bytes": path.stat().st_size} for path in sorted(root.rglob("*")) if path.is_file()]
    write_json(root / "manifest.json", {"schema_version": "dart-kospi-actions-audit-v25-draft", "generated_at_utc": datetime.now(timezone.utc).isoformat(), "coverage": [args.start_year, args.end_year], "krx_raw_root": str(args.krx_raw_root), "unique_krx_tickers": len(tickers), "mapped_current_dart_codes": sum(bool(row.get("corp_code")) for row in mapping_rows), "candidate_rows": len(candidates), "purpose": "audit_only_not_factor", "limitations": ["DART stock_code mapping is current-code metadata, not point-in-time identity proof.", "Original documents and structured responses require human/mechanical audit before any adjustment."], "files": files})
    print(f"완료: {root.resolve()} candidates={len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
