#!/usr/bin/env python3
"""OpenDART 원천을 receipt-date 기준 PIT long-form facts로 정규화한다.

사업연도와 DART 접수연도는 다를 수 있다. 원천 응답의 임시 감사값 대신 별도
receipt override와 실제 KRX 세션을 검증하며, 접수일의 다음 세션 전에는 어떠한
fact도 model eligible이 될 수 없다.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


def numeric(value: object) -> str:
    text = str(value or "").replace(",", "").strip()
    if not text or text == "-":
        return ""
    try:
        return format(Decimal(text), "f")
    except InvalidOperation:
        return ""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_source(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def parse_receipt_day(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def load_membership_sessions(root: Path) -> list[date]:
    """snapshot 파일명만으로 실제 KRX 세션 목록을 만든다."""
    sessions: set[date] = set()
    for path in root.rglob("*.csv"):
        try:
            sessions.add(datetime.strptime(path.stem, "%Y%m%d").date())
        except ValueError:
            continue
    if not sessions:
        raise FileNotFoundError(f"KRX membership session CSV가 없습니다: {root}")
    return sorted(sessions)


def next_session(receipt_day: date | None, sessions: list[date]) -> str:
    """receipt 당일을 포함하지 않는 다음 실제 KRX 세션을 반환한다."""
    if receipt_day is None:
        return ""
    position = bisect.bisect_right(sessions, receipt_day)
    return sessions[position].isoformat() if position < len(sessions) else ""


def statement_scope(payload: dict) -> str:
    """재무제표 행의 범위 표기만으로 연결/별도 provenance를 확인한다.

    수집 당시 요청 파라미터가 원천에 기록되지 않은 과거 파일에는 이 긍정 증거가
    없으면 ``UNKNOWN``을 반환한다. 빈 값을 OFS로 추정하지 않는다.
    """
    details = " ".join(str(item.get("account_detail") or "") for item in payload.get("list") or [])
    if "연결재무제표" in details or "Consolidated" in details:
        return "CFS_EVIDENCED"
    if "별도재무제표" in details or "개별재무제표" in details or "Separate" in details:
        return "OFS_EVIDENCED"
    return "UNKNOWN_NOT_MODEL_ELIGIBLE"


def load_receipt_overrides(path: Path, raw_root: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"receipt override가 없습니다: {path}")
    records: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            source = str(row.get("source_file") or "")
            if not source or source in records:
                raise ValueError(f"receipt override source_file이 비었거나 중복입니다: {source}")
            records[source] = {key: str(value or "") for key, value in row.items()}
    expected = {canonical_source(item, raw_root) for item in (raw_root / "financial_statements").rglob("*.json")}
    if set(records) != expected:
        missing, extra = sorted(expected - set(records)), sorted(set(records) - expected)
        raise ValueError(f"receipt override가 원천과 일치하지 않습니다: missing={missing[:3]} extra={extra[:3]}")
    for source, row in records.items():
        if sha256(raw_root / source) != row.get("source_sha256"):
            raise ValueError(f"receipt override source hash 불일치: {source}")
    return records


def resolve_availability(
    path: Path, root: Path, overrides: dict[str, dict[str, str]] | None, sessions: list[date] | None,
) -> tuple[str, str, str, bool]:
    """receipt date, availability date, status, eligibility를 fail-closed로 반환한다."""
    if overrides is None or sessions is None:
        audit = json.loads(path.read_text(encoding="utf-8")).get("_audit") or {}
        available = str(audit.get("available_from") or "")
        status = str(audit.get("availability_status") or "UNRESOLVED_NOT_MODEL_ELIGIBLE")
        return "", available, status, status == "RESOLVED" and bool(available)
    override = overrides[canonical_source(path, root)]
    receipt = str(override.get("receipt_date") or "")
    if override.get("availability_status") != "RESOLVED":
        return receipt, "", "UNRESOLVED_NOT_MODEL_ELIGIBLE", False
    available = next_session(parse_receipt_day(receipt), sessions)
    if not available:
        return receipt, "", "RESOLVED_OUTSIDE_DEVELOPMENT_SESSIONS_NOT_MODEL_ELIGIBLE", False
    return receipt, available, "RESOLVED_NEXT_KRX_SESSION", True


def normalize_file(
    path: Path, root: Path, overrides: dict[str, dict[str, str]] | None = None, sessions: list[date] | None = None,
) -> tuple[list[dict[str, str]], dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    audit = payload.get("_audit") or {}
    receipt_date, available_from, status, eligible = resolve_availability(path, root, overrides, sessions)
    scope = statement_scope(payload)
    if eligible and scope == "UNKNOWN_NOT_MODEL_ELIGIBLE":
        available_from = ""
        status = "RESOLVED_NEXT_KRX_SESSION_SCOPE_UNKNOWN_NOT_MODEL_ELIGIBLE"
        eligible = False
    elif eligible:
        status = f"{status}_{scope}"
    rows: list[dict[str, str]] = []
    for item in payload.get("list") or []:
        rows.append({
            "ticker": str(audit.get("ticker") or item.get("stock_code") or "").zfill(6),
            "corp_code": str(item.get("corp_code") or audit.get("corp_code") or ""),
            "rcept_no": str(item.get("rcept_no") or ""),
            "receipt_date": receipt_date,
            "available_from": available_from,
            "availability_status": status,
            "statement_scope": scope,
            "model_eligible": str(eligible).lower(),
            "business_year": str(item.get("bsns_year") or ""),
            "report_code": str(item.get("reprt_code") or ""),
            "fs_div": str(item.get("fs_div") or ""),
            "statement_div": str(item.get("sj_div") or ""),
            "account_id": str(item.get("account_id") or ""),
            "account_name": str(item.get("account_nm") or ""),
            "account_detail": str(item.get("account_detail") or ""),
            "currency": str(item.get("currency") or "KRW"),
            "current_amount": numeric(item.get("thstrm_amount")),
            "current_period_name": str(item.get("thstrm_nm") or ""),
            "current_period_start": str(item.get("thstrm_dt") or ""),
            "prior_amount": numeric(item.get("frmtrm_amount")),
            "source_file": canonical_source(path, root),
        })
    return rows, {
        "path": canonical_source(path, root), "rows": len(rows), "sha256": sha256(path), "eligible": eligible,
        "receipt_date": receipt_date, "available_from": available_from, "availability_status": status, "statement_scope": scope,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenDART KOSPI 200 PIT 재무 fact 정규화")
    parser.add_argument("--raw-root", type=Path, default=Path("data/incoming/v2_kospi200_dart_fundamentals_raw"))
    parser.add_argument("--receipt-overrides", type=Path, required=True)
    parser.add_argument("--membership-root", type=Path, default=Path("data/incoming/v2_kospi200_membership_raw/normalized/membership_daily"))
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/v2_kospi200_fundamentals_receipt_corrected"))
    args = parser.parse_args(argv)
    paths = sorted((args.raw_root / "financial_statements").rglob("*.json"))
    if not paths:
        raise FileNotFoundError("수집된 financial_statements JSON이 없습니다.")
    overrides = load_receipt_overrides(args.receipt_overrides, args.raw_root)
    sessions = load_membership_sessions(args.membership_root)
    rows: list[dict[str, str]] = []
    files: list[dict[str, object]] = []
    for path in paths:
        current, audit = normalize_file(path, args.raw_root, overrides, sessions)
        rows.extend(current); files.append(audit)
    args.output_root.mkdir(parents=True, exist_ok=True)
    columns = [
        "ticker", "corp_code", "rcept_no", "receipt_date", "available_from", "availability_status", "statement_scope", "model_eligible", "business_year", "report_code",
        "fs_div", "statement_div", "account_id", "account_name", "account_detail", "currency", "current_amount",
        "current_period_name", "current_period_start", "prior_amount", "source_file",
    ]
    target = args.output_root / "financial_facts_pit.csv"
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader(); writer.writerows(sorted(rows, key=lambda x: (x["available_from"], x["ticker"], x["account_id"])))
    manifest = {
        "schema_version": "kospi200-financial-facts-pit-v2-receipt-corrected",
        "receipt_override": {"path": str(args.receipt_overrides), "sha256": sha256(args.receipt_overrides)},
        "membership_sessions": {"root": str(args.membership_root), "count": len(sessions), "min": sessions[0].isoformat(), "max": sessions[-1].isoformat()},
        "input_files": files,
        "rows": len(rows), "eligible_rows": sum(row["model_eligible"] == "true" for row in rows),
        "output_sha256": sha256(target), "future_fill_allowed": False,
        "availability_rule": "DART_RECEIPT_DATE_NEXT_KRX_SESSION", "raw_modified": False,
    }
    (args.output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"완료: {target} rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
