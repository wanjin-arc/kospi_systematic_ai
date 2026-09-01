#!/usr/bin/env python3
"""2011~2014 DART 구형 표 원문을 감사 가능한 수치 후보로 정리한다.

이 도구는 구형 표의 계정명을 표준 XBRL account ID로 추정하지 않는다. 따라서 출력은
원문 수치 후보와 PIT 감사자료이며, Agent B 또는 factor panel 입력은 아니다.
"""

from __future__ import annotations

import argparse
import bisect
import calendar
import csv
import hashlib
import json
import re
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path


FORBIDDEN_PATH_PARTS = {"sealed", "final_oos_v24"}
RAW_STATUS = "DOWNLOADED_DOCUMENT"
UNRATIFIED_REASON = "LEGACY_LABEL_MAPPING_NOT_RATIFIED_NOT_MODEL_ELIGIBLE"

# 구형 보고서에 실제로 표기된 총계 레이블만 허용한다. 부분 계정이나 문장 안의 단어는
# 매칭하지 않으며, 표준 XBRL 계정 ID로 바꾸지도 않는다.
ACCOUNT_LABELS = {
    "assets": {"자산총계", "자산총액"},
    "liabilities": {"부채총계"},
    "equity": {"자본총계", "자본총액"},
    "current_assets": {"유동자산"},
    "current_liabilities": {"유동부채"},
    "cash_and_equivalents": {"현금및현금성자산", "현금과현금성자산"},
    "revenue": {"매출액", "매출", "영업수익"},
    "operating_income": {"영업이익", "영업손익"},
    "net_income": {"당기순이익", "당기순손익"},
    "operating_cash_flow": {"영업활동으로인한현금흐름"},
    "capital_expenditure": {"유형자산의취득", "유형자산취득"},
}
UNIT_MULTIPLIERS = {"원": Decimal("1"), "천원": Decimal("1000"), "백만원": Decimal("1000000"), "억원": Decimal("100000000")}


def guard_path(path: Path) -> None:
    if FORBIDDEN_PATH_PARTS.intersection(part.casefold() for part in path.parts):
        raise ValueError(f"금지된 OOS 경로입니다: {path}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def decode_legacy_xml(raw: bytes) -> tuple[str, str]:
    try:
        text = raw.decode("utf-8")
        if text.count("�") <= max(2, len(text) // 1000):
            return text, "UTF8"
    except UnicodeDecodeError:
        pass
    return raw.decode("cp949", errors="replace"), "CP949"


def compact(value: str) -> str:
    value = value.replace("&cr;", " ").replace("\u00a0", " ")
    value = re.sub(r"^\s*\d+\s*[\-.)]\s*", "", value)
    value = re.sub(r"[\s·ㆍㆍ\[\]\(\)\.:：,]", "", value)
    return value.strip()


def number(value: str) -> Decimal | None:
    text = str(value or "").strip().replace(",", "").replace("&cr;", "")
    if not text or text in {"-", "－"} or "%" in text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("() ")
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
        return None
    try:
        result = Decimal(text)
    except InvalidOperation:
        return None
    return -result if negative else result


def format_decimal(value: Decimal) -> str:
    return format(value, "f")


@dataclass
class ParsedTable:
    rows: list[list[str]]
    context: str


class LegacyTableParser(HTMLParser):
    """DART 구형 XML의 느슨한 표 태그를 복구 가능한 표 행으로 읽는다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[ParsedTable] = []
        self._stack: list[dict[str, object]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._outside: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._stack.append({"rows": [], "context": " ".join(self._outside[-200:])[-3000:]})
        elif tag == "tr" and self._stack:
            self._row = []
        elif tag in {"td", "th", "te", "tu"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)
        elif not self._stack:
            self._outside.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th", "te", "tu"} and self._cell is not None and self._row is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._stack and self._row is not None:
            rows = self._stack[-1]["rows"]
            assert isinstance(rows, list)
            rows.append(self._row)
            self._row = None
        elif tag == "table" and self._stack:
            item = self._stack.pop()
            rows = item["rows"]
            context = item["context"]
            assert isinstance(rows, list) and isinstance(context, str)
            self.tables.append(ParsedTable(rows=rows, context=context))


def parse_tables(raw: bytes) -> tuple[list[ParsedTable], str]:
    text, encoding = decode_legacy_xml(raw)
    parser = LegacyTableParser()
    parser.feed(text)
    parser.close()
    return parser.tables, encoding


def detect_unit(table: ParsedTable) -> str:
    text = " ".join([table.context, *[" ".join(row) for row in table.rows]])
    compact_text = re.sub(r"\s+", "", text)
    # 구형 DART 표에는 ``(단위 : 백만원)``처럼 공백·전각 콜론·괄호가
    # 제각각 들어간다. 기존 검사는 ``단위:``만 찾았으므로 정상 단위를
    # 놓쳤다. 표 안에서만, 가장 큰 단위부터 정확히 확인한다.
    for unit in ("백만원", "천원", "억원", "원"):
        if re.search(rf"단위[\s:：\)\]]*{re.escape(unit)}(?:[,\)\]]|$)", compact_text):
            return unit
    return ""


def detect_scope(table: ParsedTable) -> str:
    text = compact(" ".join([table.context, *[" ".join(row) for row in table.rows]]))
    if "연결재무" in text or "연결손익" in text or "연결현금" in text:
        return "CFS_EVIDENCED"
    if "별도재무" in text or "개별재무" in text or "별도손익" in text or "개별손익" in text:
        return "OFS_EVIDENCED"
    return "UNKNOWN_NOT_MODEL_ELIGIBLE"


def table_candidates(table: ParsedTable) -> list[dict[str, str]]:
    unit = detect_unit(table)
    scope = detect_scope(table)
    output: list[dict[str, str]] = []
    label_lookup = {label: canonical for canonical, labels in ACCOUNT_LABELS.items() for label in labels}
    for row_index, row in enumerate(table.rows):
        for label_index, cell in enumerate(row):
            canonical = label_lookup.get(compact(cell))
            if canonical is None:
                continue
            values = [number(cell_value) for cell_value in row[label_index + 1 :]]
            value = next((item for item in values if item is not None), None)
            if value is None:
                continue
            amount_krw = ""
            if unit:
                amount_krw = format_decimal(value * UNIT_MULTIPLIERS[unit])
            output.append({
                "canonical_candidate": canonical,
                "source_label": cell.strip(),
                "reported_amount": format_decimal(value),
                "reported_unit": unit,
                "amount_krw_candidate": amount_krw,
                "statement_scope": scope,
                "table_row_index": str(row_index),
                "row_cells": " | ".join(row),
            })
            break
    return output


def report_period(report_name: str) -> str:
    match = re.search(r"\((\d{4})\.(\d{2})\)", report_name)
    if not match:
        return ""
    year, month = int(match.group(1)), int(match.group(2))
    return f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def load_sessions(root: Path) -> list[date]:
    sessions: set[date] = set()
    for path in root.rglob("*.csv"):
        try:
            sessions.add(datetime.strptime(path.stem, "%Y%m%d").date())
        except ValueError:
            continue
    if not sessions:
        raise FileNotFoundError(f"KRX membership session CSV가 없습니다: {root}")
    return sorted(sessions)


def next_session(receipt: str, sessions: list[date]) -> str:
    try:
        receipt_day = datetime.strptime(receipt, "%Y%m%d").date()
    except ValueError:
        return ""
    index = bisect.bisect_right(sessions, receipt_day)
    return sessions[index].isoformat() if index < len(sessions) else ""


def load_identity(path: Path) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            result[str(row.get("ticker") or "").zfill(6)].append({key: str(value or "") for key, value in row.items()})
    return result


def identity_status(identity: dict[str, list[dict[str, str]]], ticker: str, corp_code: str, available_from: str) -> tuple[str, str]:
    if not available_from:
        return "UNRESOLVED_NO_AVAILABILITY_DATE", "false"
    for spell in identity.get(ticker, []):
        if spell.get("first_date", "") <= available_from <= spell.get("last_date", ""):
            if spell.get("corp_code") != corp_code:
                return "UNRESOLVED_CORP_CODE_MISMATCH", "false"
            return spell.get("identity_status") or "UNRESOLVED_IDENTITY", spell.get("model_eligible") or "false"
    return "UNRESOLVED_NO_PIT_IDENTITY_SPELL", "false"


def logical_latest(rows: list[dict[str, str]]) -> set[str]:
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row.get("document_status") == RAW_STATUS and row.get("report_period_end"):
            groups[(row["ticker"], row["report_kind"], row["report_period_end"])].append(row)
    latest: set[str] = set()
    for values in groups.values():
        chosen = max(values, key=lambda item: (item.get("rcept_dt", ""), item.get("rcept_no", "")))
        latest.add(chosen["rcept_no"])
    return latest


def write_csv(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(raw_root: Path, membership_root: Path, identity_path: Path, output_root: Path) -> dict[str, object]:
    for path in (raw_root, membership_root, identity_path, output_root):
        guard_path(path)
    source_manifest = raw_root / "manifest.json"
    source_audit = raw_root / "document_audit.csv"
    if not source_manifest.exists() or not source_audit.exists():
        raise FileNotFoundError("원문 루트의 manifest.json과 document_audit.csv가 필요합니다.")
    manifest_payload = json.loads(source_manifest.read_text(encoding="utf-8"))
    if manifest_payload.get("coverage") != {"start_year": 2011, "end_year": 2014}:
        raise ValueError("2011~2014 legacy DART 원문만 허용합니다.")
    sessions = load_sessions(membership_root)
    identities = load_identity(identity_path)
    with source_audit.open("r", encoding="utf-8-sig", newline="") as handle:
        source_rows = [{key: str(value or "") for key, value in row.items()} for row in csv.DictReader(handle)]
    for row in source_rows:
        row["ticker"] = row.get("ticker", "").zfill(6)
        row["report_period_end"] = report_period(row.get("report_nm", ""))
        row["available_from"] = next_session(row.get("rcept_dt", ""), sessions)
        status, eligible = identity_status(identities, row["ticker"], row.get("corp_code", ""), row["available_from"])
        row["identity_status"] = status
        row["identity_model_eligible"] = eligible
    latest_receipts = logical_latest(source_rows)

    document_rows: list[dict[str, str]] = []
    candidate_rows: list[dict[str, str]] = []
    for source in sorted(source_rows, key=lambda item: (item.get("rcept_dt", ""), item["ticker"], item.get("rcept_no", ""))):
        base = {
            "ticker": source["ticker"], "corp_code": source.get("corp_code", ""), "rcept_no": source.get("rcept_no", ""),
            "rcept_dt": source.get("rcept_dt", ""), "available_from": source["available_from"],
            "report_nm": source.get("report_nm", ""), "report_kind": source.get("report_kind", ""),
            "report_period_end": source["report_period_end"], "is_correction": source.get("is_correction", ""),
            "document_status": source.get("document_status", ""), "document_path": source.get("document_path", ""),
            "identity_status": source["identity_status"], "identity_model_eligible": source["identity_model_eligible"],
            "latest_logical_filing": str(source.get("rcept_no", "") in latest_receipts).lower(),
        }
        candidates: list[dict[str, str]] = []
        encoding = ""
        parser_status = "NOT_DOWNLOADED"
        table_count = "0"
        xml_payload_count = "0"
        xml_payloads = ""
        if source.get("document_status") == RAW_STATUS and source.get("document_path"):
            document = raw_root / source["document_path"]
            if document.exists():
                try:
                    with zipfile.ZipFile(document) as archive:
                        xmls = sorted(name for name in archive.namelist() if name.casefold().endswith(".xml"))
                        if not xmls:
                            raise ValueError("XML payload가 없습니다.")
                        encodings: set[str] = set()
                        table_total = 0
                        for xml_name in xmls:
                            tables, current_encoding = parse_tables(archive.read(xml_name))
                            encodings.add(current_encoding)
                            table_total += len(tables)
                            for table in tables:
                                for candidate in table_candidates(table):
                                    candidate["xml_payload"] = xml_name
                                    candidates.append(candidate)
                    encoding = "+".join(sorted(encodings))
                    table_count = str(table_total)
                    xml_payload_count = str(len(xmls))
                    xml_payloads = "|".join(xmls)
                    parser_status = "PARSED_NUMERIC_CANDIDATES" if candidates else "PARSED_NO_STRICT_CORE_LABEL_CANDIDATE"
                except (OSError, ValueError, zipfile.BadZipFile) as exc:
                    parser_status = f"PARSE_REJECT_{type(exc).__name__}"
            else:
                parser_status = "MISSING_ARCHIVED_DOCUMENT"
        document_rows.append({
            **base, "source_sha256": sha256(raw_root / source["document_path"]) if source.get("document_path") and (raw_root / source["document_path"]).exists() else "",
            "detected_encoding": encoding, "xml_payload_count": xml_payload_count, "xml_payloads": xml_payloads,
            "table_count": table_count, "numeric_candidate_rows": str(len(candidates)),
            "parser_status": parser_status, "model_eligible": "false", "model_eligibility_reason": UNRATIFIED_REASON,
        })
        for candidate in candidates:
            candidate_rows.append({
                **base, **candidate, "source_sha256": sha256(raw_root / source["document_path"]),
                "model_eligible": "false", "model_eligibility_reason": UNRATIFIED_REASON,
            })

    # 동일 문서에서 동일 scope·계정의 서로 다른 값은 선택하지 않는다.
    selected_rows: list[dict[str, str]] = []
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in candidate_rows:
        if row["latest_logical_filing"] == "true":
            grouped[(row["rcept_no"], row["statement_scope"], row["canonical_candidate"])].append(row)
    for values in grouped.values():
        distinct = {(item["reported_amount"], item["reported_unit"], item["amount_krw_candidate"]) for item in values}
        if len(distinct) == 1:
            chosen = min(values, key=lambda item: (int(item["table_row_index"]), item["source_label"]))
            selected_rows.append({**chosen, "selection_status": "UNAMBIGUOUS_CURRENT_FILING_CANDIDATE_NOT_MODEL_ELIGIBLE"})
        else:
            for item in values:
                selected_rows.append({**item, "selection_status": "AMBIGUOUS_SAME_FILING_ACCOUNT_EXCLUDED"})

    output_root.mkdir(parents=True, exist_ok=True)
    document_columns = [
        "ticker", "corp_code", "rcept_no", "rcept_dt", "available_from", "report_nm", "report_kind", "report_period_end", "is_correction",
        "document_status", "document_path", "identity_status", "identity_model_eligible", "latest_logical_filing", "source_sha256",
        "detected_encoding", "xml_payload_count", "xml_payloads", "table_count", "numeric_candidate_rows", "parser_status", "model_eligible", "model_eligibility_reason",
    ]
    candidate_columns = [
        "ticker", "corp_code", "rcept_no", "rcept_dt", "available_from", "report_nm", "report_kind", "report_period_end", "is_correction",
        "document_status", "document_path", "identity_status", "identity_model_eligible", "latest_logical_filing", "canonical_candidate",
        "source_label", "reported_amount", "reported_unit", "amount_krw_candidate", "statement_scope", "xml_payload", "table_row_index", "row_cells",
        "source_sha256", "model_eligible", "model_eligibility_reason",
    ]
    selected_columns = [*candidate_columns, "selection_status"]
    document_target = output_root / "legacy_document_numeric_audit.csv"
    candidates_target = output_root / "legacy_financial_candidates.csv"
    selected_target = output_root / "legacy_financial_selected.csv"
    write_csv(document_target, document_rows, document_columns)
    write_csv(candidates_target, candidate_rows, candidate_columns)
    write_csv(selected_target, selected_rows, selected_columns)
    counts = Counter(row["canonical_candidate"] for row in candidate_rows)
    selected_counts = Counter(row["canonical_candidate"] for row in selected_rows if row["selection_status"].startswith("UNAMBIGUOUS"))
    result = {
        "schema_version": "kospi200-legacy-dart-numeric-audit-v1",
        "status": "PASS_CANDIDATE_EXTRACTION_MODEL_INPUT_FORBIDDEN",
        "raw_manifest_sha256": sha256(source_manifest), "raw_audit_sha256": sha256(source_audit), "identity_sha256": sha256(identity_path),
        "membership_sessions": {"count": len(sessions), "min": sessions[0].isoformat(), "max": sessions[-1].isoformat()},
        "documents": len(document_rows), "downloaded_documents": sum(row["document_status"] == RAW_STATUS for row in document_rows),
        "parsed_documents": sum(row["parser_status"].startswith("PARSED") for row in document_rows),
        "documents_with_multiple_xml_payloads": sum(int(row["xml_payload_count"] or 0) > 1 for row in document_rows),
        "candidate_rows": len(candidate_rows), "candidate_account_rows": dict(sorted(counts.items())),
        "selected_rows": sum(row["selection_status"].startswith("UNAMBIGUOUS") for row in selected_rows),
        "selected_account_rows": dict(sorted(selected_counts.items())),
        "correction_rows": sum(row["is_correction"] == "true" for row in document_rows),
        "identity_confirmed_at_availability": sum(row["identity_model_eligible"] == "true" for row in document_rows),
        "model_eligible_rows": 0, "model_eligibility_reason": UNRATIFIED_REASON,
        "outputs": {path.name: sha256(path) for path in (document_target, candidates_target, selected_target)},
        "raw_modified": False, "protected_oos_accessed": False, "model_started": False,
    }
    (output_root / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KOSPI 200 2011~2014 DART 구형 재무표 수치 후보 감사")
    parser.add_argument("--raw-root", type=Path, default=Path("data/incoming/v2_kospi200_dart_legacy_originals_raw"))
    parser.add_argument("--membership-root", type=Path, default=Path("data/incoming/v2_kospi200_membership_raw/normalized/membership_daily"))
    parser.add_argument("--identity", type=Path, default=Path("data/processed/v2_kospi200_identity_frozen/identity_spells.csv"))
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/v2_kospi200_legacy_dart_numeric_audit"))
    args = parser.parse_args(argv)
    result = run(args.raw_root, args.membership_root, args.identity, args.output_root)
    print(json.dumps({key: result[key] for key in ("status", "documents", "candidate_rows", "selected_rows", "model_eligible_rows")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
