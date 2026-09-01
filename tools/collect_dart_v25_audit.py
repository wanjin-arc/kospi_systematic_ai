#!/usr/bin/env python3
"""v25 과거 KOSPI100 자료의 Corporate Action 감사용 DART 원천 수집기.

이 도구는 공시 내용을 투자 Factor로 사용하지 않는다. 분할, 합병, 감자,
증자, 상장폐지 후보를 검증할 수 있도록 Open DART의 원본 응답과 후보 목록만
보존한다. API 키는 실행 중 한 번만 입력받으며 파일에 저장하지 않는다.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import time
import zipfile
from datetime import date
from getpass import getpass
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DART = "https://opendart.fss.or.kr/api"
KEYWORDS = ("분할", "합병", "감자", "증자", "상장폐지", "주식교환", "주식이전", "영업양수")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def get_bytes(url: str, params: dict[str, str]) -> bytes:
    request = Request(f"{url}?{urlencode(params)}", headers={"User-Agent": "kospi100-data-audit/1.0"})
    with urlopen(request, timeout=45) as response:
        return response.read()


def load_pit_tickers(raw_root: Path) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for path in sorted((raw_root / "raw" / "membership_1034").rglob("*.csv.gz")):
        with gzip.open(path, "rt", encoding="cp949", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                ticker = str(row.get("종목코드", "")).strip().strip('"').zfill(6)
                if re.fullmatch(r"\d{6}", ticker):
                    result.setdefault(ticker, set()).add(str(row.get("종목명", "")).strip())
    if not result:
        raise ValueError(f"PIT membership 원천을 찾지 못했습니다: {raw_root}")
    return result


def parse_corp_codes(raw: bytes) -> dict[str, dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        xml_name = next(name for name in archive.namelist() if name.lower().endswith(".xml"))
        xml = archive.read(xml_name).decode("utf-8", errors="replace")
    rows = re.findall(r"<list>(.*?)</list>", xml, flags=re.DOTALL)
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        fields = {key: re.search(fr"<{key}>(.*?)</{key}>", row, flags=re.DOTALL) for key in ("corp_code", "corp_name", "stock_code")}
        ticker = (fields["stock_code"].group(1).strip() if fields["stock_code"] else "")
        if re.fullmatch(r"\d{6}", ticker):
            result[ticker] = {key: (match.group(1).strip() if match else "") for key, match in fields.items()}
    return result


def request_list(key: str, corp_code: str, year: int) -> list[dict[str, str]]:
    common = {"crtfc_key": key, "corp_code": corp_code, "bgn_de": f"{year}0101", "end_de": f"{year}1231", "page_count": "100"}
    first = json.loads(get_bytes(f"{DART}/list.json", {**common, "page_no": "1"}).decode("utf-8"))
    if first.get("status") in {"013", "020"}:
        return []
    if first.get("status") != "000":
        raise RuntimeError(f"DART list 오류 corp={corp_code} year={year}: {first.get('status')} {first.get('message')}")
    rows = list(first.get("list", []))
    pages = int(first.get("total_page", 1))
    for page in range(2, pages + 1):
        payload = json.loads(get_bytes(f"{DART}/list.json", {**common, "page_no": str(page)}).decode("utf-8"))
        if payload.get("status") != "000":
            raise RuntimeError(f"DART pagination 오류 corp={corp_code} year={year} page={page}")
        rows.extend(payload.get("list", []))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="DART Corporate Action 감사 원천 수집기")
    parser.add_argument("--raw-root", type=Path, default=Path("data/incoming/v25_zip_import/krx_v25_technical_raw"))
    parser.add_argument("--output-root", type=Path, default=Path("data/incoming/v25_dart_audit_raw"))
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year", type=int, default=2010)
    parser.add_argument("--delay", type=float, default=0.15)
    args = parser.parse_args()
    if args.start_year > args.end_year:
        raise SystemExit("start-year는 end-year보다 클 수 없습니다.")
    key = getpass("Open DART API key (표시·저장되지 않음): ").strip()
    if not key:
        raise SystemExit("Open DART API key가 필요합니다.")
    tickers = load_pit_tickers(args.raw_root)
    root = args.output_root
    root.mkdir(parents=True, exist_ok=True)
    corp_zip = root / "corp_codes.xml.zip"
    if not corp_zip.exists():
        corp_zip.write_bytes(get_bytes(f"{DART}/corpCode.xml", {"crtfc_key": key}))
    mapping = parse_corp_codes(corp_zip.read_bytes())
    candidates: list[dict[str, str]] = []
    map_rows = []
    for ticker in sorted(tickers):
        corp = mapping.get(ticker)
        map_rows.append({"ticker": ticker, "pit_names": "|".join(sorted(tickers[ticker])), "corp_code": "" if corp is None else corp["corp_code"], "dart_name": "" if corp is None else corp["corp_name"]})
        if corp is None:
            continue
        for year in range(args.start_year, args.end_year + 1):
            target = root / "disclosures" / corp["corp_code"] / f"{year}.json"
            if target.exists():
                rows = json.loads(target.read_text(encoding="utf-8"))
            else:
                rows = request_list(key, corp["corp_code"], year)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(rows, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
                time.sleep(args.delay)
            for row in rows:
                title = str(row.get("report_nm", ""))
                if any(keyword in title for keyword in KEYWORDS):
                    candidates.append({"ticker": ticker, "corp_code": corp["corp_code"], "rcept_no": str(row.get("rcept_no", "")), "rcept_dt": str(row.get("rcept_dt", "")), "report_nm": title, "flr_nm": str(row.get("flr_nm", ""))})
    with (root / "ticker_corp_mapping.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ticker", "pit_names", "corp_code", "dart_name"]); writer.writeheader(); writer.writerows(map_rows)
    with (root / "corporate_action_candidates.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ticker", "corp_code", "rcept_no", "rcept_dt", "report_nm", "flr_nm"]); writer.writeheader(); writer.writerows(candidates)
    manifest = {"purpose": "audit_only_not_factor", "coverage": [args.start_year, args.end_year], "pit_tickers": len(tickers), "dart_mapped_tickers": sum(bool(row["corp_code"]) for row in map_rows), "candidate_rows": len(candidates), "raw_root_sha256_note": "source raw files remain immutable", "files": [{"path": str(path.relative_to(root)).replace('\\\\', '/'), "sha256": sha256(path)} for path in sorted(root.rglob("*.json"))]}
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"pit_tickers": len(tickers), "mapped": sum(bool(row["corp_code"]) for row in map_rows), "candidate_rows": len(candidates), "output": str(root.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
