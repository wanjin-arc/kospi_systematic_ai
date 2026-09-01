#!/usr/bin/env python3
"""PIT facts를 동결된 표준 XBRL taxonomy의 canonical 계정으로 축약한다."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path


FORBIDDEN_PATH_PARTS = {"sealed", "final_oos_v24"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def guard_path(path: Path) -> None:
    if FORBIDDEN_PATH_PARTS.intersection(part.casefold() for part in path.parts):
        raise ValueError(f"금지된 OOS 경로입니다: {path}")


def top_level_detail(value: str) -> bool:
    text = str(value or "").strip()
    if text in {"", "-"}:
        return True
    return "|" not in text and any(marker in text for marker in ("연결재무제표", "별도재무제표", "개별재무제표", "Consolidated", "Separate"))


def load_identity(path: Path) -> set[str]:
    confirmed: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("model_eligible") == "true":
                confirmed.add(str(row.get("ticker") or "").zfill(6))
    if not confirmed:
        raise ValueError("확정된 identity ticker가 없습니다.")
    return confirmed


def build(facts_path: Path, identity_path: Path, taxonomy_path: Path, output_root: Path) -> dict[str, object]:
    for path in (facts_path, identity_path, taxonomy_path, output_root):
        guard_path(path)
    taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    if taxonomy.get("manual_account_name_fallbacks") != {}:
        raise ValueError("taxonomy v1은 account-name fallback을 허용하지 않습니다.")
    confirmed = load_identity(identity_path)
    lookup: dict[tuple[str, str], tuple[str, int]] = {}
    for canonical, rule in taxonomy["accounts"].items():
        for priority, account_id in enumerate(rule["account_ids"]):
            lookup[(str(account_id), canonical)] = (canonical, priority)
    candidates_by_id: dict[str, list[tuple[str, int, set[str]]]] = defaultdict(list)
    for canonical, rule in taxonomy["accounts"].items():
        for priority, account_id in enumerate(rule["account_ids"]):
            candidates_by_id[str(account_id)].append((canonical, priority, set(rule["statement_div"])))

    selected: dict[tuple[str, str], dict[str, str]] = {}
    ambiguous: set[tuple[str, str]] = set()
    input_rows = eligible_input_rows = 0
    with facts_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            input_rows += 1
            ticker = str(row.get("ticker") or "").zfill(6)
            if row.get("model_eligible") != "true" or ticker not in confirmed:
                continue
            eligible_input_rows += 1
            account_id = str(row.get("account_id") or "")
            rules = candidates_by_id.get(account_id, [])
            if not rules or not top_level_detail(str(row.get("account_detail") or "")):
                continue
            for canonical, priority, divisions in rules:
                if str(row.get("statement_div") or "") not in divisions or not str(row.get("current_amount") or ""):
                    continue
                key = (str(row.get("source_file") or ""), canonical)
                candidate = {
                    "ticker": ticker, "corp_code": str(row.get("corp_code") or ""),
                    "receipt_date": str(row.get("receipt_date") or ""), "available_from": str(row.get("available_from") or ""),
                    "statement_scope": str(row.get("statement_scope") or ""), "business_year": str(row.get("business_year") or ""),
                    "report_code": str(row.get("report_code") or ""), "canonical_account": canonical,
                    "amount": str(row.get("current_amount") or ""), "source_account_id": account_id,
                    "source_account_name": str(row.get("account_name") or ""), "source_file": str(row.get("source_file") or ""),
                    "_priority": str(priority),
                }
                previous = selected.get(key)
                if previous is None or priority < int(previous["_priority"]):
                    selected[key] = candidate
                    ambiguous.discard(key)
                elif priority == int(previous["_priority"]) and candidate["amount"] != previous["amount"]:
                    ambiguous.add(key)
    for key in ambiguous:
        selected.pop(key, None)
    rows = sorted(selected.values(), key=lambda row: (row["available_from"], row["ticker"], row["source_file"], row["canonical_account"]))
    for row in rows:
        row.pop("_priority", None)
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / "canonical_financial_accounts.csv"
    columns = list(rows[0])
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    account_counts: dict[str, int] = defaultdict(int)
    account_tickers: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        account_counts[row["canonical_account"]] += 1
        account_tickers[row["canonical_account"]].add(row["ticker"])
    missing_accounts = sorted(set(taxonomy["accounts"]) - set(account_counts))
    result = {
        "schema_version": "kospi200-canonical-fundamental-accounts-v1",
        "status": "PASS_CANONICAL_ACCOUNTS_MODEL_NOT_STARTED" if not missing_accounts else "FAIL_MISSING_CANONICAL_ACCOUNT",
        "facts_sha256": sha256(facts_path), "identity_sha256": sha256(identity_path), "taxonomy_sha256": sha256(taxonomy_path),
        "input_rows": input_rows, "identity_eligible_input_rows": eligible_input_rows,
        "output_rows": len(rows), "ambiguous_statement_accounts_excluded": len(ambiguous),
        "account_rows": dict(sorted(account_counts.items())),
        "account_ticker_coverage": {key: len(value) for key, value in sorted(account_tickers.items())},
        "missing_accounts": missing_accounts, "output_sha256": sha256(target),
        "raw_modified": False, "protected_oos_accessed": False, "model_started": False,
    }
    (output_root / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KOSPI 200 canonical fundamental account panel")
    parser.add_argument("--facts", type=Path, default=Path("data/processed/v2_kospi200_fundamentals_receipt_corrected/financial_facts_pit.csv"))
    parser.add_argument("--identity", type=Path, default=Path("data/processed/v2_kospi200_identity_frozen/identity_spells.csv"))
    parser.add_argument("--taxonomy", type=Path, default=Path("configs/kospi200_fundamental_account_taxonomy_v1.json"))
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/v2_kospi200_canonical_fundamentals"))
    args = parser.parse_args(argv)
    result = build(args.facts, args.identity, args.taxonomy, args.output_root)
    print(json.dumps({key: result[key] for key in ("status", "output_rows", "ambiguous_statement_accounts_excluded", "missing_accounts", "output_sha256")}, ensure_ascii=False))
    return 0 if result["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
