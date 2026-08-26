#!/usr/bin/env python3
"""검증된 2011~2014 구형 DART 수치 후보만 canonical account long-form으로 승격한다."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


FORBIDDEN_PATH_PARTS = {"sealed", "final_oos_v24"}
REPORT_CODES = {"03": "11013", "06": "11012", "09": "11014", "12": "11011"}


def guard(path: Path) -> None:
    if FORBIDDEN_PATH_PARTS.intersection(part.casefold() for part in path.parts):
        raise ValueError(f"금지된 OOS 경로입니다: {path}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def report_fields(period_end: str) -> tuple[str, str] | None:
    if len(period_end) != 10 or period_end[4] != "-" or period_end[7] != "-":
        return None
    year, month = period_end[:4], period_end[5:7]
    code = REPORT_CODES.get(month)
    return (year, code) if code else None


def build(selected_path: Path, contract_path: Path, output_root: Path) -> dict[str, object]:
    for path in (selected_path, contract_path, output_root):
        guard(path)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    required_accounts = set(contract["accounts"])
    minimum = contract["source_period"]["min_report_period_end"]
    maximum = contract["source_period"]["max_report_period_end"]
    rows: list[dict[str, str]] = []
    rejected: Counter[str] = Counter()
    seen: dict[tuple[str, str], str] = {}
    with selected_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for source in csv.DictReader(handle):
            account = str(source.get("canonical_candidate") or "")
            period_end = str(source.get("report_period_end") or "")
            if account not in required_accounts:
                rejected["unlisted_account"] += 1; continue
            if not (minimum <= period_end <= maximum):
                rejected["outside_ifrs_legacy_period"] += 1; continue
            fiscal = report_fields(period_end)
            if fiscal is None:
                rejected["non_quarter_period"] += 1; continue
            if source.get("selection_status") != "UNAMBIGUOUS_CURRENT_FILING_CANDIDATE_NOT_MODEL_ELIGIBLE":
                rejected["ambiguous_same_filing"] += 1; continue
            if source.get("latest_logical_filing") != "true":
                rejected["superseded_filing"] += 1; continue
            if source.get("identity_model_eligible") != "true":
                rejected["unresolved_identity"] += 1; continue
            if source.get("statement_scope") != contract["required_statement_scope"]:
                rejected["non_cfs_scope"] += 1; continue
            amount = str(source.get("amount_krw_candidate") or "")
            if not amount or not str(source.get("reported_unit") or ""):
                rejected["unknown_unit"] += 1; continue
            key = (str(source.get("rcept_no") or ""), account)
            previous = seen.get(key)
            if previous is not None and previous != amount:
                raise ValueError(f"같은 공시의 canonical account 값 충돌: {key}")
            seen[key] = amount
            year, report_code = fiscal
            rows.append({
                "ticker": str(source.get("ticker") or "").zfill(6),
                "corp_code": str(source.get("corp_code") or ""),
                "receipt_date": str(source.get("rcept_dt") or ""),
                "available_from": str(source.get("available_from") or ""),
                "statement_scope": str(source.get("statement_scope") or ""),
                "business_year": year, "report_code": report_code,
                "canonical_account": account, "amount": amount,
                "source_account_id": "LEGACY_EXACT_TOP_LEVEL_LABEL",
                "source_account_name": str(source.get("source_label") or ""),
                "source_file": str(source.get("document_path") or ""),
                "source_sha256": str(source.get("source_sha256") or ""),
                "legacy_unit": str(source.get("reported_unit") or ""),
            })
    unique = {(row["rcept_no"] if "rcept_no" in row else row["source_file"], row["canonical_account"]): row for row in rows}
    rows = sorted(unique.values(), key=lambda row: (row["available_from"], row["ticker"], row["source_file"], row["canonical_account"]))
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / "canonical_financial_accounts_legacy.csv"
    columns = ["ticker", "corp_code", "receipt_date", "available_from", "statement_scope", "business_year", "report_code", "canonical_account", "amount", "source_account_id", "source_account_name", "source_file", "source_sha256", "legacy_unit"]
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    coverage = Counter(row["canonical_account"] for row in rows)
    result = {
        "schema_version": "kospi200-legacy-canonical-fundamentals-v1",
        "status": "PASS_LEGACY_CANONICAL_MODEL_NOT_STARTED" if coverage else "FAIL_NO_ELIGIBLE_LEGACY_ACCOUNTS",
        "selected_sha256": sha256(selected_path), "contract_sha256": sha256(contract_path),
        "output_sha256": sha256(target), "output_rows": len(rows), "account_rows": dict(sorted(coverage.items())),
        "rejected_rows": dict(sorted(rejected.items())), "raw_modified": False,
        "protected_oos_accessed": False, "model_started": False,
    }
    (output_root / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KOSPI 200 legacy DART canonical fundamentals")
    parser.add_argument("--selected", type=Path, default=Path("data/processed/v2_kospi200_legacy_dart_numeric_audit_v2/legacy_financial_selected.csv"))
    parser.add_argument("--contract", type=Path, default=Path("configs/kospi200_legacy_dart_account_contract_v1.json"))
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/v2_kospi200_legacy_canonical_fundamentals"))
    args = parser.parse_args(argv)
    result = build(args.selected, args.contract, args.output_root)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
