#!/usr/bin/env python3
"""KOSPI 200 PIT 종목명과 OpenDART 법인코드의 보수적 동일성을 동결한다."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree


FORBIDDEN_PATH_PARTS = {"sealed", "final_oos_v24"}
DESIGNATORS = ("주식회사", "(주)", "㈜", "co.,ltd.", "co.ltd.", "coltd", "inc.")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def guard_path(path: Path) -> None:
    if FORBIDDEN_PATH_PARTS.intersection(part.casefold() for part in path.parts):
        raise ValueError(f"금지된 OOS 경로입니다: {path}")


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    for token in DESIGNATORS:
        text = text.replace(token, "")
    return re.sub(r"[\s\-_.·,&()/]+", "", text)


def load_dart_companies(corp_zip: Path) -> dict[str, tuple[str, str]]:
    with zipfile.ZipFile(corp_zip) as archive:
        member = next(name for name in archive.namelist() if name.lower().endswith(".xml"))
        root = ElementTree.fromstring(archive.read(member))
    result: dict[str, tuple[str, str]] = {}
    for node in root.findall("list"):
        ticker = str(node.findtext("stock_code") or "").strip()
        if ticker.isdigit():
            result[ticker.zfill(6)] = (
                str(node.findtext("corp_code") or "").strip(),
                str(node.findtext("corp_name") or "").strip(),
            )
    return result


def load_raw_ticker_corp(audit_csv: Path) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    with audit_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            ticker = str(row.get("ticker") or "").zfill(6)
            corp = str(row.get("corp_code") or "")
            if ticker.isdigit() and corp:
                result[ticker].add(corp)
    return result


def load_membership_spells(root: Path) -> dict[tuple[str, str], dict[str, str | int]]:
    spells: dict[tuple[str, str], dict[str, str | int]] = {}
    paths = sorted(root.rglob("*.csv"))
    if not paths:
        raise FileNotFoundError(f"membership 파일이 없습니다: {root}")
    for path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                ticker = str(row.get("ticker") or "").zfill(6)
                name = str(row.get("name") or "").strip()
                day = str(row.get("date") or "")[:10]
                if not ticker.isdigit() or not name or not day:
                    continue
                record = spells.setdefault((ticker, name), {"first_date": day, "last_date": day, "session_rows": 0})
                record["first_date"] = min(str(record["first_date"]), day)
                record["last_date"] = max(str(record["last_date"]), day)
                record["session_rows"] = int(record["session_rows"]) + 1
    return spells


def freeze(membership_root: Path, dart_root: Path, contract_path: Path, output_root: Path) -> dict[str, object]:
    for path in (membership_root, dart_root, contract_path, output_root):
        guard_path(path)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("manual_aliases") != {}:
        raise ValueError("identity contract v1은 수동 alias를 허용하지 않습니다.")
    corp_zip = dart_root / "corp_codes.xml.zip"
    audit_csv = dart_root / "collection_audit.csv"
    if not corp_zip.exists() or not audit_csv.exists():
        raise FileNotFoundError("DART corp_codes.xml.zip과 collection_audit.csv가 필요합니다.")
    companies = load_dart_companies(corp_zip)
    raw_links = load_raw_ticker_corp(audit_csv)
    spells = load_membership_spells(membership_root)
    rows: list[dict[str, str | int]] = []
    ticker_status: dict[str, set[str]] = defaultdict(set)
    for (ticker, membership_name), spell in sorted(spells.items()):
        company = companies.get(ticker)
        linked = raw_links.get(ticker, set())
        if not company or not linked:
            corp_code = dart_name = ""
            status = "NO_DART_CORP_MAPPING_NOT_MODEL_ELIGIBLE"
        else:
            corp_code, dart_name = company
            if len(linked) != 1 or corp_code not in linked:
                status = "AMBIGUOUS_TICKER_CORP_NOT_MODEL_ELIGIBLE"
            elif normalize_name(membership_name) == normalize_name(dart_name):
                status = "CONFIRMED_EXACT_NAME_AND_UNIQUE_CORP"
            else:
                status = "UNRESOLVED_NAME_MISMATCH_NOT_MODEL_ELIGIBLE"
        ticker_status[ticker].add(status)
        rows.append({
            "ticker": ticker, "corp_code": corp_code, "dart_corp_name": dart_name,
            "membership_name": membership_name, "normalized_dart_name": normalize_name(dart_name),
            "normalized_membership_name": normalize_name(membership_name),
            "first_date": spell["first_date"], "last_date": spell["last_date"],
            "session_rows": spell["session_rows"], "identity_status": status,
            "model_eligible": str(status == "CONFIRMED_EXACT_NAME_AND_UNIQUE_CORP").lower(),
        })
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / "identity_spells.csv"
    columns = list(rows[0])
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row["identity_status"])] += 1
    confirmed_tickers = sorted({str(row["ticker"]) for row in rows if row["model_eligible"] == "true"})
    unresolved_tickers = sorted(set(ticker_status) - set(confirmed_tickers))
    result = {
        "schema_version": "kospi200-historical-identity-freeze-v1",
        "status": "PASS_FAIL_CLOSED_IDENTITY_FREEZE",
        "contract_sha256": sha256(contract_path), "corp_codes_sha256": sha256(corp_zip),
        "collection_audit_sha256": sha256(audit_csv),
        "membership_files": len(list(membership_root.rglob("*.csv"))),
        "membership_name_spells": len(rows), "membership_tickers": len(ticker_status),
        "confirmed_tickers": len(confirmed_tickers), "fully_unresolved_tickers": len(unresolved_tickers),
        "status_counts": dict(sorted(counts.items())), "unresolved_ticker_list": unresolved_tickers,
        "output_sha256": sha256(target), "raw_modified": False, "protected_oos_accessed": False,
    }
    (output_root / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KOSPI 200 역사적 ticker-DART identity 동결")
    parser.add_argument("--membership-root", type=Path, default=Path("data/incoming/v2_kospi200_membership_raw/normalized/membership_daily"))
    parser.add_argument("--dart-root", type=Path, default=Path("data/incoming/v2_kospi200_dart_fundamentals_raw"))
    parser.add_argument("--contract", type=Path, default=Path("configs/kospi200_identity_contract_v1.json"))
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/v2_kospi200_identity_frozen"))
    args = parser.parse_args(argv)
    result = freeze(args.membership_root, args.dart_root, args.contract, args.output_root)
    print(json.dumps({key: result[key] for key in ("status", "confirmed_tickers", "fully_unresolved_tickers", "output_sha256")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
