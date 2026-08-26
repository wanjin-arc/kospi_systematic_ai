#!/usr/bin/env python3
"""KOSPI 200 PIT 구성종목 수집 결과를 모델 사용 전 감사한다.

원천과 정규화 파일을 변경하지 않는다. 2024년 이후 또는 봉인 OOS 경로는
입력으로 거부하며, 수집 manifest의 raw SHA-256도 다시 확인한다.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_krx_kospi200_v2 as collector  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _deny_protected(path: Path) -> None:
    parts = {part.casefold() for part in path.resolve().parts}
    if {"sealed", "final_oos_v24"} & parts:
        raise PermissionError("봉인 OOS 경로는 v2 KOSPI 200 감사 입력으로 사용할 수 없습니다.")


def _dates(root: Path, suffix: str) -> set[str]:
    return {path.stem for path in root.rglob(f"*{suffix}")}


def _raw_date(path: Path) -> str:
    return path.name.removesuffix(".csv.gz")


def audit(root: Path, output: Path) -> dict[str, object]:
    _deny_protected(root)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest가 없습니다: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "kospi200-krx-raw-v2":
        raise ValueError("KOSPI 200 v2 원천 manifest가 아닙니다.")
    if manifest.get("protected_oos_accessed") is not False:
        raise ValueError("원천 manifest의 protected OOS 감사값이 false가 아닙니다.")
    if manifest.get("coverage", {}).get("end", "9999-99-99") > "2023-12-31":
        raise ValueError("2023년 이후 KRX 수집 결과는 v2 개발 감사에서 허용하지 않습니다.")

    raw_root = root / "raw" / "membership_1028"
    normalized_root = root / "normalized" / "membership_daily"
    checkpoint = root / "checkpoints" / "completed_sessions.txt"
    skipped_empty = root / "checkpoints" / "skipped_empty_sessions.txt"
    if not raw_root.exists() or not normalized_root.exists() or not checkpoint.exists():
        raise FileNotFoundError("raw, normalized, completed checkpoint가 모두 필요합니다.")

    expected_hashes = {item["path"]: item["sha256"] for item in manifest.get("raw_files", [])}
    actual_raw = sorted(raw_root.rglob("*.csv.gz"))
    actual_hashes = {
        str(path.relative_to(root)).replace("\\", "/"): sha256_file(path)
        for path in actual_raw
    }
    hash_mismatches = sorted(
        path for path, digest in actual_hashes.items() if expected_hashes.get(path) != digest
    )
    unexpected_manifest_paths = sorted(set(expected_hashes) - set(actual_hashes))

    skipped_dates = set()
    if skipped_empty.exists():
        skipped_dates = {line.strip() for line in skipped_empty.read_text(encoding="utf-8").splitlines() if line.strip()}

    counts: Counter[int] = Counter()
    invalid_dates: list[str] = []
    duplicate_ticker_dates: list[str] = []
    for raw_path in actual_raw:
        day = _raw_date(raw_path)
        with gzip.open(raw_path, "rb") as handle:
            members = collector.parse_membership(handle.read(), pd.Timestamp(day).date())
        count = len(members)
        if day not in skipped_dates:
            counts[count] += 1
        if day not in skipped_dates and not (199 <= count <= 205):
            invalid_dates.append(day)
        if members["ticker"].duplicated().any():
            duplicate_ticker_dates.append(day)

    normalized_dates = _dates(normalized_root, ".csv")
    raw_dates = {_raw_date(path) for path in actual_raw}
    completed_dates = {line.strip() for line in checkpoint.read_text(encoding="utf-8").splitlines() if line.strip()}
    effective_raw_dates = raw_dates - skipped_dates
    missing_normalized = sorted(effective_raw_dates - normalized_dates)
    extra_normalized = sorted(normalized_dates - raw_dates)
    checkpoint_mismatch = sorted((effective_raw_dates - completed_dates) | (completed_dates - effective_raw_dates))

    result = {
        "schema_version": "kospi200-membership-audit-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_root": str(root),
        "input_manifest_sha256": sha256_file(manifest_path),
        "coverage": manifest["coverage"],
        "session_source_sessions": manifest.get("session_source", {}).get("sessions"),
        "raw_snapshot_files": len(actual_raw),
        "normalized_snapshot_files": len(normalized_dates),
        "skipped_empty_sessions": sorted(skipped_dates),
        "official_member_count_distribution": {str(key): counts[key] for key in sorted(counts)},
        "raw_manifest_hash_mismatches": hash_mismatches,
        "raw_manifest_missing_files": unexpected_manifest_paths,
        "invalid_member_count_dates": invalid_dates,
        "duplicate_ticker_dates": duplicate_ticker_dates,
        "missing_normalized_dates": missing_normalized,
        "extra_normalized_dates": extra_normalized,
        "completed_checkpoint_mismatch": checkpoint_mismatch,
        "protected_oos_accessed": False,
        "model_use_allowed": False,
        "fundamental_data_status": "NOT_COLLECTED",
    }
    result["status"] = (
        "PASS_MEMBERSHIP_ONLY_DART_REQUIRED"
        if not any((hash_mismatches, unexpected_manifest_paths, invalid_dates, duplicate_ticker_dates,
                    missing_normalized, extra_normalized, checkpoint_mismatch))
        else "FAIL"
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "membership_audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    pd.DataFrame(
        [{"member_count": key, "sessions": counts[key]} for key in sorted(counts)]
    ).to_csv(output / "membership_count_distribution.csv", index=False, encoding="utf-8-sig")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KOSPI 200 PIT 구성종목 원천·정규화 감사")
    parser.add_argument("--input-root", type=Path, default=Path("data/incoming/v2_kospi200_membership_raw"))
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/v2_phase1_membership_audit"))
    args = parser.parse_args(argv)
    print(json.dumps(audit(args.input_root, args.output_root), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
