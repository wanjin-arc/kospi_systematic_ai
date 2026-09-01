#!/usr/bin/env python3
"""2011~2014 legacy 및 2015~2023 XBRL canonical accounts를 새 파생 패널로 합친다."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

FORBIDDEN_PATH_PARTS = {"sealed", "final_oos_v24"}
FIELDS = ["ticker", "corp_code", "receipt_date", "available_from", "statement_scope", "business_year", "report_code", "canonical_account", "amount", "source_account_id", "source_account_name", "source_file"]


def guard(path: Path) -> None:
    if FORBIDDEN_PATH_PARTS.intersection(part.casefold() for part in path.parts):
        raise ValueError(f"금지된 OOS 경로입니다: {path}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_rows(path: Path, origin: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for source in csv.DictReader(handle):
            row = {field: str(source.get(field) or "") for field in FIELDS}
            row["ticker"] = row["ticker"].zfill(6)
            row["source_file"] = f"{origin}:{row['source_file']}"
            rows.append(row)
    return rows


def merge(legacy_path: Path, standard_path: Path, output_root: Path) -> dict[str, object]:
    for path in (legacy_path, standard_path, output_root):
        guard(path)
    legacy, standard = read_rows(legacy_path, "legacy"), read_rows(standard_path, "xbrl")
    if any(row["available_from"] >= "2015-01-01" for row in legacy):
        raise ValueError("legacy 입력에 2015년 이후 행이 있습니다.")
    if any(row["available_from"] < "2015-01-01" for row in standard):
        raise ValueError("표준 XBRL 입력에 2015년 이전 행이 있습니다.")
    keys: set[tuple[str, str, str, str]] = set()
    for row in [*legacy, *standard]:
        key = (row["ticker"], row["available_from"], row["source_file"], row["canonical_account"])
        if key in keys:
            raise ValueError(f"canonical 중복 행입니다: {key}")
        keys.add(key)
    rows = sorted([*legacy, *standard], key=lambda row: (row["available_from"], row["ticker"], row["source_file"], row["canonical_account"]))
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / "canonical_financial_accounts.csv"
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    result = {
        "schema_version": "kospi200-canonical-fundamentals-merged-v2",
        "status": "PASS_LEGACY_AND_XBRL_MERGED_MODEL_NOT_STARTED",
        "legacy_input_sha256": sha256(legacy_path), "xbrl_input_sha256": sha256(standard_path),
        "output_sha256": sha256(target), "legacy_rows": len(legacy), "xbrl_rows": len(standard), "output_rows": len(rows),
        "min_date": min(row["available_from"] for row in rows), "max_date": max(row["available_from"] for row in rows),
        "raw_modified": False, "protected_oos_accessed": False, "model_started": False,
    }
    (output_root / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KOSPI 200 legacy/XBRL canonical merger")
    parser.add_argument("--legacy", type=Path, default=Path("data/processed/v2_kospi200_legacy_canonical_fundamentals/canonical_financial_accounts_legacy.csv"))
    parser.add_argument("--xbrl", type=Path, default=Path("data/processed/v2_kospi200_canonical_fundamentals/canonical_financial_accounts.csv"))
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/v2_kospi200_canonical_fundamentals_2011_2023"))
    args = parser.parse_args(argv)
    print(json.dumps(merge(args.legacy, args.xbrl, args.output_root), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
