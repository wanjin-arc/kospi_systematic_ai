from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from .schema import PRICE_COLUMNS, SCHEMA_VERSION, SPLIT_ACTION_TYPES, TABLE_SPECS
from .validation import (
    CsvTable,
    Issue,
    active_membership_ids,
    load_tables,
    load_source_manifest,
    parse_date,
    parse_decimal,
    summarize_issues,
    validate_calendar,
    validate_events,
    validate_coverage,
    validate_lineage,
    validate_memberships,
    validate_ohlcv,
    validate_price_coverage,
    validate_referential_integrity,
    validate_suspensions,
    validate_symbol_master,
)


@dataclass
class BuildResult:
    status: str
    report_path: Path
    issues: list[Issue]
    artifacts: list[Path]
    stats: dict[str, object]

    @property
    def is_valid(self) -> bool:
        return self.status == "VALID"


class Phase1Pipeline:
    def __init__(
        self,
        input_root: Path,
        output_root: Path,
        report_path: Path,
        *,
        expected_universe_size: int = 100,
        research_start: date = date(2011, 1, 1),
        research_end: date = date(2025, 12, 31),
        development_end: date = date(2023, 12, 31),
        final_oos_start: date = date(2024, 1, 1),
        final_oos_end: date = date(2025, 12, 31),
    ) -> None:
        self.input_root = Path(input_root)
        self.output_root = Path(output_root)
        self.report_path = Path(report_path)
        self.expected_universe_size = expected_universe_size
        self.research_start = research_start
        self.research_end = research_end
        self.development_end = development_end
        self.final_oos_start = final_oos_start
        self.final_oos_end = final_oos_end

    def validate(self) -> BuildResult:
        tables, issues = load_tables(self.input_root)
        manifest_rows, manifest_issues = load_source_manifest(self.input_root)
        issues.extend(manifest_issues)
        issues.extend(self._validate_loaded_tables(tables, manifest_rows))
        stats = self._stats(tables, issues)
        status = "VALID" if not any(issue.severity in {"BLOCKER", "ERROR"} for issue in issues) else "BLOCKED"
        self._write_report(status, stats, issues, [])
        return BuildResult(status, self.report_path, issues, [], stats)

    def build(self) -> BuildResult:
        tables, issues = load_tables(self.input_root)
        manifest_rows, manifest_issues = load_source_manifest(self.input_root)
        issues.extend(manifest_issues)
        issues.extend(self._validate_loaded_tables(tables, manifest_rows))
        stats = self._stats(tables, issues)
        if any(issue.severity in {"BLOCKER", "ERROR"} for issue in issues):
            self._write_report("BLOCKED", stats, issues, [])
            return BuildResult("BLOCKED", self.report_path, issues, [], stats)

        artifacts = self._write_partitions(tables)
        artifact_hashes = {str(path): _sha256(path) for path in artifacts}
        stats["artifact_sha256"] = artifact_hashes
        self._write_report("VALID", stats, issues, artifacts)
        return BuildResult("VALID", self.report_path, issues, artifacts, stats)

    def _validate_loaded_tables(
        self, tables: dict[str, CsvTable], manifest_rows: list[dict[str, str]]
    ) -> list[Issue]:
        issues: list[Issue] = []
        if table := tables.get("symbol_master"):
            issues.extend(validate_symbol_master(table))
        if table := tables.get("trading_calendar"):
            issues.extend(validate_calendar(table))
        if table := tables.get("ohlcv_raw"):
            issues.extend(validate_ohlcv(table, ("trade_date", "symbol_id")))
        if table := tables.get("index_ohlcv_raw"):
            issues.extend(validate_ohlcv(table, ("trade_date", "index_code")))
        if table := tables.get("corporate_actions"):
            issues.extend(validate_events(table))
        if table := tables.get("suspensions"):
            issues.extend(validate_suspensions(table))
        if table := tables.get("universe_membership"):
            issues.extend(
                validate_memberships(table, tables.get("trading_calendar"), self.expected_universe_size)
            )
        coverage_tables = ("universe_membership", "trading_calendar", "ohlcv_raw", "suspensions")
        if all(name in tables for name in coverage_tables):
            issues.extend(
                validate_price_coverage(
                    tables["universe_membership"],
                    tables["trading_calendar"],
                    tables["ohlcv_raw"],
                    tables["suspensions"],
                )
            )
        issues.extend(validate_lineage(tables, manifest_rows))
        issues.extend(validate_referential_integrity(tables))
        issues.extend(validate_coverage(tables, self.research_start, self.research_end))
        return issues

    def _stats(self, tables: dict[str, CsvTable], issues: list[Issue]) -> dict[str, object]:
        stats: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "input_root": str(self.input_root),
            "table_rows": {name: len(table.rows) for name, table in tables.items()},
            "input_sha256": {name: table.sha256 for name, table in tables.items()},
            "issue_counts": summarize_issues(issues),
            "expected_universe_size": self.expected_universe_size,
            "research_window": [self.research_start.isoformat(), self.research_end.isoformat()],
            "development_end": self.development_end.isoformat(),
            "final_oos_window": [self.final_oos_start.isoformat(), self.final_oos_end.isoformat()],
        }
        date_ranges: dict[str, list[str] | None] = {}
        date_column_by_table = {
            "trading_calendar": "trade_date",
            "ohlcv_raw": "trade_date",
            "index_ohlcv_raw": "trade_date",
            "universe_membership": "valid_from",
            "corporate_actions": "effective_date",
            "suspensions": "suspended_from",
        }
        for name, column in date_column_by_table.items():
            values: list[date] = []
            if name in tables:
                for row in tables[name].rows:
                    try:
                        values.append(parse_date(row[column]))
                    except (KeyError, ValueError):
                        continue
            date_ranges[name] = [min(values).isoformat(), max(values).isoformat()] if values else None
        stats["date_ranges"] = date_ranges
        return stats

    def _write_report(
        self, status: str, stats: dict[str, object], issues: list[Issue], artifacts: list[Path]
    ) -> None:
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "status": status,
            "stats": stats,
            "issues": [issue.to_dict() for issue in issues],
            "artifacts": [str(path) for path in artifacts],
        }
        self.report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def _write_partitions(self, tables: dict[str, CsvTable]) -> list[Path]:
        development = self.output_root / "processed" / "development"
        sealed_oos = self.output_root / "sealed" / "final_oos"
        development.mkdir(parents=True, exist_ok=True)
        sealed_oos.mkdir(parents=True, exist_ok=True)

        cleaned_ohlcv = _clean_ohlcv(
            tables["ohlcv_raw"].rows,
            tables["universe_membership"].rows,
            tables["corporate_actions"].rows,
        )
        table_rows: dict[str, tuple[list[str], list[dict[str, str]], str]] = {
            "ohlcv_clean": (
                [
                    *tables["ohlcv_raw"].fieldnames,
                    "adjustment_factor_asof",
                    "analysis_open",
                    "analysis_high",
                    "analysis_low",
                    "analysis_close",
                    "analysis_volume",
                ],
                cleaned_ohlcv,
                "trade_date",
            ),
            "index_ohlcv": (tables["index_ohlcv_raw"].fieldnames, tables["index_ohlcv_raw"].rows, "trade_date"),
            "trading_calendar": (tables["trading_calendar"].fieldnames, tables["trading_calendar"].rows, "trade_date"),
            "corporate_actions": (tables["corporate_actions"].fieldnames, tables["corporate_actions"].rows, "effective_date"),
        }

        artifacts: list[Path] = []
        for name, (columns, rows, date_column) in table_rows.items():
            dev_rows, oos_rows = _partition_simple_rows(
                rows, date_column, self.development_end, self.final_oos_start, self.final_oos_end
            )
            dev_path = development / f"{name}.csv.gz"
            oos_path = sealed_oos / f"{name}.csv.gz"
            _write_csv_gz(dev_path, columns, dev_rows)
            _write_csv_gz(oos_path, columns, oos_rows)
            artifacts.extend((dev_path, oos_path))

        membership_columns = tables["universe_membership"].fieldnames
        dev_memberships, oos_memberships = _partition_intervals(
            tables["universe_membership"].rows,
            self.development_end,
            self.final_oos_start,
            self.final_oos_end,
        )
        for root, rows in ((development, dev_memberships), (sealed_oos, oos_memberships)):
            path = root / "universe_membership.csv.gz"
            _write_csv_gz(path, membership_columns, rows)
            artifacts.append(path)

        symbol_columns = tables["symbol_master"].fieldnames
        dev_symbols, oos_symbols = _partition_symbol_master(
            tables["symbol_master"].rows,
            self.development_end,
            self.final_oos_start,
            self.final_oos_end,
        )
        for root, rows in ((development, dev_symbols), (sealed_oos, oos_symbols)):
            path = root / "symbol_master.csv.gz"
            _write_csv_gz(path, symbol_columns, rows)
            artifacts.append(path)

        suspension_columns = tables["suspensions"].fieldnames
        dev_suspensions, oos_suspensions = _partition_named_intervals(
            tables["suspensions"].rows,
            "suspended_from",
            "suspended_to",
            self.development_end,
            self.final_oos_start,
            self.final_oos_end,
        )
        for root, rows in ((development, dev_suspensions), (sealed_oos, oos_suspensions)):
            path = root / "suspensions.csv.gz"
            _write_csv_gz(path, suspension_columns, rows)
            artifacts.append(path)

        for root in (development, sealed_oos):
            manifest_path = root / "manifest.json"
            local_artifacts = [path for path in artifacts if path.parent == root]
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "partition": "development" if root == development else "final_oos_sealed",
                "files": {path.name: _sha256(path) for path in sorted(local_artifacts)},
            }
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            artifacts.append(manifest_path)
        return artifacts


def _clean_ohlcv(
    ohlcv_rows: Iterable[dict[str, str]],
    membership_rows: Iterable[dict[str, str]],
    action_rows: Iterable[dict[str, str]],
) -> list[dict[str, str]]:
    memberships = list(membership_rows)
    events: dict[str, list[tuple[date, Decimal]]] = defaultdict(list)
    for row in action_rows:
        if row.get("action_type", "").upper() not in SPLIT_ACTION_TYPES:
            continue
        effective = parse_date(row["effective_date"])
        factor = parse_decimal(row["share_factor_numerator"]) / parse_decimal(row["share_factor_denominator"])
        events[row["symbol_id"]].append((effective, factor))
    for symbol_events in events.values():
        symbol_events.sort(key=lambda item: item[0])

    cleaned: list[dict[str, str]] = []
    for row in sorted(ohlcv_rows, key=lambda item: (item["trade_date"], item["symbol_id"])):
        session = parse_date(row["trade_date"])
        if row["symbol_id"] not in active_membership_ids(memberships, session):
            continue
        cumulative = Decimal(1)
        for effective, factor in events.get(row["symbol_id"], []):
            if effective <= session:
                cumulative *= factor
        output = dict(row)
        output["adjustment_factor_asof"] = _format_decimal(cumulative)
        for column in PRICE_COLUMNS:
            output[f"analysis_{column}"] = _format_decimal(parse_decimal(row[column]) * cumulative)
        output["analysis_volume"] = _format_decimal(parse_decimal(row["volume"]) / cumulative)
        cleaned.append(output)
    return cleaned


def _partition_simple_rows(
    rows: Iterable[dict[str, str]],
    date_column: str,
    development_end: date,
    final_oos_start: date,
    final_oos_end: date,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    dev: list[dict[str, str]] = []
    oos: list[dict[str, str]] = []
    for row in rows:
        if not row.get(date_column):
            continue
        value = parse_date(row[date_column])
        if value <= development_end:
            dev.append(dict(row))
        elif final_oos_start <= value <= final_oos_end:
            oos.append(dict(row))
    return dev, oos


def _partition_intervals(
    rows: Iterable[dict[str, str]],
    development_end: date,
    final_oos_start: date,
    final_oos_end: date,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    return _partition_named_intervals(
        rows, "valid_from", "valid_to", development_end, final_oos_start, final_oos_end, end_exclusive=True
    )


def _partition_named_intervals(
    rows: Iterable[dict[str, str]],
    start_column: str,
    end_column: str,
    development_end: date,
    final_oos_start: date,
    final_oos_end: date,
    *,
    end_exclusive: bool = False,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    dev: list[dict[str, str]] = []
    oos: list[dict[str, str]] = []
    oos_end_exclusive = date(final_oos_end.year + 1, 1, 1)
    for source in rows:
        start = parse_date(source[start_column])
        end = parse_date(source[end_column]) if source.get(end_column) else None
        effective_end = end or date.max
        if not end_exclusive and end is not None:
            effective_end = date.fromordinal(end.toordinal() + 1)

        if start <= development_end and effective_end > date.min:
            row = dict(source)
            if end is None or end > final_oos_start:
                row[end_column] = final_oos_start.isoformat() if end_exclusive else development_end.isoformat()
            dev.append(row)
        if start < oos_end_exclusive and effective_end > final_oos_start:
            row = dict(source)
            row[start_column] = max(start, final_oos_start).isoformat()
            if end is None or effective_end > oos_end_exclusive:
                row[end_column] = oos_end_exclusive.isoformat() if end_exclusive else final_oos_end.isoformat()
            oos.append(row)
    return dev, oos


def _partition_symbol_master(
    rows: Iterable[dict[str, str]],
    development_end: date,
    final_oos_start: date,
    final_oos_end: date,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    dev, oos = _partition_intervals(rows, development_end, final_oos_start, final_oos_end)
    for row in dev:
        if row.get("delisting_date") and parse_date(row["delisting_date"]) >= final_oos_start:
            row["delisting_date"] = ""
    return dev, oos


def _write_csv_gz(path: Path, fieldnames: list[str], rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                writer = csv.DictWriter(text, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
