#!/usr/bin/env python3
"""DART 2011~2014 원문을 계정 추출 전 단계에서 fail-closed로 분류한다.

이 도구는 원문 ZIP 안의 구조ㆍ인코딩ㆍ정정 여부와 파일 해시만 기록한다. 재무 수치,
공시 텍스트, 예측 또는 모델 입력을 만들지 않는다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path


FORBIDDEN_PATH_PARTS = {"sealed", "final_oos_v24"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def guard(path: Path) -> None:
    if FORBIDDEN_PATH_PARTS.intersection(part.casefold() for part in path.parts):
        raise ValueError(f"금지된 OOS 경로입니다: {path}")


def decode_legacy_xml(raw: bytes) -> tuple[str, str]:
    """DART 구형 XML은 선언과 달리 CP949 바이트인 경우가 있어 우선 판별한다."""
    try:
        text = raw.decode("utf-8")
        if text.count("�") <= max(2, len(text) // 1000):
            return text, "UTF8"
    except UnicodeDecodeError:
        pass
    return raw.decode("cp949", errors="replace"), "CP949"


def classify_zip(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path) as archive:
        entries = [item for item in archive.infolist() if not item.is_dir()]
        names = [item.filename for item in entries]
        xml_entries = [item for item in entries if item.filename.casefold().endswith(".xml")]
        samples = []
        encodings: Counter[str] = Counter()
        has_table = has_xbrl = False
        for item in xml_entries[:5]:
            raw = archive.read(item)
            text, encoding = decode_legacy_xml(raw)
            encodings[encoding] += 1
            lower = text.casefold()
            has_table = has_table or "<table" in lower
            has_xbrl = has_xbrl or "<xbrl" in lower or "xbrli:" in lower or "http://www.xbrl.org" in lower
            samples.append(item.filename)
        if has_xbrl or any(name.casefold().endswith((".xsd", ".xbrl")) for name in names):
            structure = "XBRL_OR_INLINE_XBRL_REQUIRES_SEPARATE_PARSER"
        elif xml_entries and has_table:
            structure = "LEGACY_TABLE_XML_REQUIRES_NUMERIC_ACCOUNT_REVIEW"
        elif xml_entries:
            structure = "XML_NON_TABULAR_REQUIRES_MANUAL_REVIEW"
        else:
            structure = "NO_XML_PAYLOAD_REJECT"
        return {
            "zip_entries": len(entries), "xml_entries": len(xml_entries), "sample_xml_entries": "|".join(samples),
            "detected_encoding": "+".join(sorted(encodings)) or "NO_XML", "structure": structure,
        }


def run(raw_root: Path, output_root: Path) -> dict[str, object]:
    guard(raw_root); guard(output_root)
    audit_path = raw_root / "document_audit.csv"
    manifest_path = raw_root / "manifest.json"
    if not audit_path.exists() or not manifest_path.exists():
        raise FileNotFoundError("원문 루트에 document_audit.csv와 manifest.json이 필요합니다.")
    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if source_manifest.get("coverage") != {"start_year": 2011, "end_year": 2014}:
        raise ValueError("2011~2014 legacy DART 원문만 허용합니다.")
    rows: list[dict[str, str]] = []
    with audit_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for source in csv.DictReader(handle):
            result = {key: str(value or "") for key, value in source.items()}
            status = result.get("document_status")
            relative = result.get("document_path")
            if status != "DOWNLOADED_DOCUMENT" or not relative:
                result.update({"source_sha256": "", "zip_entries": "0", "xml_entries": "0", "sample_xml_entries": "", "detected_encoding": "", "structure": "NONZIP_OR_MISSING_REJECT", "normalization_status": "NOT_MODEL_ELIGIBLE"})
            else:
                path = raw_root / relative
                if not path.exists():
                    result.update({"source_sha256": "", "zip_entries": "0", "xml_entries": "0", "sample_xml_entries": "", "detected_encoding": "", "structure": "MISSING_ARCHIVED_DOCUMENT_REJECT", "normalization_status": "NOT_MODEL_ELIGIBLE"})
                else:
                    details = classify_zip(path)
                    result.update({key: str(value) for key, value in details.items()})
                    result["source_sha256"] = sha256(path)
                    result["normalization_status"] = (
                        "REQUIRES_CORRECTION_PAIR_AND_NUMERIC_ACCOUNT_AUDIT" if result.get("is_correction") == "true"
                        else "REQUIRES_NUMERIC_ACCOUNT_AND_IDENTITY_AUDIT"
                    )
            rows.append(result)
    rows.sort(key=lambda row: (row.get("rcept_dt", ""), row.get("ticker", ""), row.get("rcept_no", "")))
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / "legacy_document_inventory.csv"
    columns = list(rows[0])
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    structures = Counter(row["structure"] for row in rows)
    result = {
        "schema_version": "kospi200-legacy-dart-document-inventory-v1",
        "status": "PASS_RAW_INTAKE_CLASSIFIED_MODEL_NOT_STARTED",
        "raw_root": str(raw_root), "source_manifest_sha256": sha256(manifest_path), "source_audit_sha256": sha256(audit_path),
        "input_rows": len(rows), "structure_counts": dict(sorted(structures.items())),
        "downloaded_documents": sum(row["document_status"] == "DOWNLOADED_DOCUMENT" for row in rows),
        "correction_rows": sum(row["is_correction"] == "true" for row in rows),
        "inventory_sha256": sha256(target), "raw_modified": False, "model_started": False,
        "protected_oos_accessed": False, "factor_usage": "FORBIDDEN_UNTIL_NUMERIC_ACCOUNT_AND_PIT_IDENTITY_AUDIT",
    }
    (output_root / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KOSPI 200 legacy DART 원문 구조 분류")
    parser.add_argument("--raw-root", type=Path, default=Path("data/incoming/v2_kospi200_dart_legacy_originals_raw"))
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/v2_kospi200_legacy_dart_intake"))
    args = parser.parse_args(argv)
    result = run(args.raw_root, args.output_root)
    print(json.dumps({key: result[key] for key in ("status", "input_rows", "structure_counts", "inventory_sha256")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
