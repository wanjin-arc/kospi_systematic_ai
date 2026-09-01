#!/usr/bin/env python3
"""기수집 OpenDART 원천에서 receipt-date PIT 보정 레이어를 만든다.

사업연도와 접수연도는 다를 수 있다. 원천 JSON을 수정하지 않고 모든 연도별
공시목록을 교차 대조해 재무제표 응답의 접수번호를 확인한다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build(raw_root: Path, output_root: Path) -> dict[str, object]:
    disclosure_root = raw_root / "disclosures"
    statement_root = raw_root / "financial_statements"
    if not disclosure_root.exists() or not statement_root.exists():
        raise FileNotFoundError("disclosures와 financial_statements 원천이 모두 필요합니다.")
    receipt_dates: dict[str, str] = {}
    conflicts: set[str] = set()
    for path in sorted(disclosure_root.rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("list") or []:
            number, day = str(row.get("rcept_no") or ""), str(row.get("rcept_dt") or "")
            if not number or not day:
                continue
            previous = receipt_dates.setdefault(number, day)
            if previous != day:
                conflicts.add(number)

    rows: list[dict[str, str]] = []
    for path in sorted(statement_root.rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        numbers = sorted({str(row.get("rcept_no") or "") for row in payload.get("list") or [] if row.get("rcept_no")})
        dates = [receipt_dates[number] for number in numbers if number in receipt_dates and number not in conflicts]
        resolved = bool(numbers) and len(dates) == len(numbers)
        rows.append({
            "source_file": str(path.relative_to(raw_root)).replace("\\", "/"),
            "source_sha256": sha256(path),
            "receipt_numbers": "|".join(numbers),
            "receipt_date": max(dates) if resolved else "",
            "availability_status": "RESOLVED" if resolved else "UNRESOLVED_NOT_MODEL_ELIGIBLE",
        })
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / "receipt_overrides.csv"
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    result = {
        "schema_version": "kospi200-dart-receipt-override-v1",
        "raw_root": str(raw_root),
        "raw_statement_files": len(rows),
        "disclosure_receipt_count": len(receipt_dates),
        "conflicting_receipt_dates": sorted(conflicts),
        "resolved_statement_files": sum(row["availability_status"] == "RESOLVED" for row in rows),
        "unresolved_statement_files": sum(row["availability_status"] != "RESOLVED" for row in rows),
        "output_sha256": sha256(target),
        "raw_modified": False,
    }
    (output_root / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenDART receipt-date PIT 보정 레이어 생성")
    parser.add_argument("--raw-root", type=Path, default=Path("data/incoming/v2_kospi200_dart_fundamentals_raw"))
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/v2_kospi200_dart_receipt_overrides"))
    args = parser.parse_args(argv)
    print(json.dumps(build(args.raw_root, args.output_root), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
