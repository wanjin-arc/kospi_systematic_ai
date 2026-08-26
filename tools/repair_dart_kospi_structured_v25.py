#!/usr/bin/env python3
"""Repair only invalid OpenDART structured-response paths into a new raw directory.

The first v25 collection preserved responses for three legacy endpoint names that
OpenDART rejects with status ``101``.  This utility never overwrites that raw
collection.  A plan is the default; a caller must explicitly give a positive
request cap before any API request is made.  This makes daily quota use,
interruption, and restart auditable.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path


BASE = "https://opendart.fss.or.kr/api"
REPAIR_ENDPOINTS = {
    "company_split": "cmpDvDecsn.json",
    "split_merger": "cmpDvMgDecsn.json",
    "share_exchange_transfer": "stkExtrDecsn.json",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


LABEL_TERMS = {
    "company_split": ("회사분할",),
    "split_merger": ("분할합병",),
    "share_exchange_transfer": ("주식교환", "주식이전"),
}


def candidate_periods(candidate_csv: Path) -> set[tuple[str, str, str]]:
    """Restrict a repair to the event class actually disclosed in that year."""
    if not candidate_csv.exists():
        return set()
    periods: set[tuple[str, str, str]] = set()
    with candidate_csv.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            title = row.get("report_nm", "").replace(" ", "")
            year = row.get("rcept_dt", "")[:4]
            corp_code = row.get("corp_code", "")
            for label, terms in LABEL_TERMS.items():
                if year.isdigit() and corp_code and any(term in title for term in terms):
                    periods.add((label, corp_code, year))
    return periods


def pending_repairs(source_root: Path, output_root: Path, *, candidate_csv: Path | None = None) -> list[dict[str, str]]:
    """Return repairable legacy paths with a recorded invalid-access response.

    These structured OpenDART endpoints publish data only from 2015.  Earlier
    filings must remain in the original-document/manual-audit path instead of
    consuming a request quota on a request that cannot provide evidence.
    """
    eligible = candidate_periods(candidate_csv) if candidate_csv else set()
    pending: list[dict[str, str]] = []
    for label, endpoint in sorted(REPAIR_ENDPOINTS.items()):
        for source in sorted((source_root / "structured" / label).glob("*/*.json")):
            try:
                payload = read_json(source)
            except (OSError, json.JSONDecodeError):
                continue
            if str(payload.get("status", "")) != "101":
                continue
            corp_code, year = source.parent.name, source.stem
            if int(year) < 2015:
                continue
            if candidate_csv and (label, corp_code, year) not in eligible:
                continue
            target = output_root / "structured" / label / corp_code / f"{year}.json"
            if target.exists():
                continue
            pending.append(
                {
                    "label": label,
                    "endpoint": endpoint,
                    "corp_code": corp_code,
                    "year": year,
                    "source_path": source.relative_to(source_root).as_posix(),
                    "target_path": target.relative_to(output_root).as_posix(),
                }
            )
    return pending


def request_json(endpoint: str, key: str, **params: str) -> dict:
    query = urllib.parse.urlencode({"crtfc_key": key, **params})
    request = urllib.request.Request(
        f"{BASE}/{endpoint}?{query}", headers={"User-Agent": "kospi-systematic-ai structured-repair/1.0"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"OpenDART {endpoint} returned non-JSON data") from exc


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_plan(output_root: Path, rows: list[dict[str, str]]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    columns = ["label", "endpoint", "corp_code", "year", "source_path", "target_path"]
    with (output_root / "repair_plan.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair v25 OpenDART structured status-101 records without overwriting raw input")
    parser.add_argument("--source-root", type=Path, default=Path("data/incoming/v25_kospi_dart_audit_raw_complete"))
    parser.add_argument("--output-root", type=Path, default=Path("data/incoming/v25_kospi_dart_audit_repaired"))
    parser.add_argument("--max-requests", type=int, default=0, help="0 means plan only; a positive cap is required for API calls")
    parser.add_argument("--delay", type=float, default=0.2)
    args = parser.parse_args(argv)
    if args.max_requests < 0:
        raise SystemExit("--max-requests must be non-negative")

    pending = pending_repairs(args.source_root, args.output_root, candidate_csv=args.source_root / "corporate_action_candidates.csv")
    write_plan(args.output_root, pending)
    if args.max_requests == 0:
        print(f"Plan only: {len(pending)} repair requests written to {args.output_root / 'repair_plan.csv'}")
        return 0

    key = getpass("OpenDART API key (input is not stored or printed): ").strip()
    if len(key) != 40:
        raise SystemExit("OpenDART API key must be exactly 40 characters")
    selected = pending[: args.max_requests]
    for number, item in enumerate(selected, start=1):
        response = request_json(
            item["endpoint"], key, corp_code=item["corp_code"], bgn_de=f"{item['year']}0101", end_de=f"{item['year']}1231"
        )
        response["_repair_provenance"] = {
            "legacy_source_path": item["source_path"],
            "endpoint": item["endpoint"],
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        write_json(args.output_root / item["target_path"], response)
        if number % 100 == 0 or number == len(selected):
            print(f"Repaired {number}/{len(selected)} (remaining plan: {len(pending) - number})", flush=True)
        time.sleep(args.delay)
    files = [
        {"path": path.relative_to(args.output_root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(args.output_root.rglob("*.json"))
    ]
    write_json(
        args.output_root / "manifest.json",
        {
            "schema_version": "dart-kospi-structured-repair-v25",
            "source_root": str(args.source_root),
            "planned_requests": len(pending),
            "completed_this_run": len(selected),
            "remaining_after_run": len(pending) - len(selected),
            "files": files,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
