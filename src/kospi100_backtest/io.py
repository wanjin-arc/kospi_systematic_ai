from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, fields, is_dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping

from .types import (
    AuditEvent,
    CashLedgerEntry,
    ClosedTrade,
    EquityPoint,
    Fill,
    OrderEvent,
    PositionLedgerEntry,
    PositionSnapshot,
    RunResult,
)


def _scalar(value: object) -> object:
    if isinstance(value, (date, Decimal)):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return json.dumps(value, default=_json_default, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if value is None:
        return ""
    return value


def _json_default(value: object) -> object:
    if isinstance(value, (date, Decimal)):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(type(value).__name__)


def _write_rows(path: Path, rows: Iterable[object], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for item in rows:
            raw = asdict(item)
            writer.writerow({key: _scalar(raw[key]) for key in fieldnames})


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, default=_json_default, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_result(result: RunResult, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = {
        "fills.csv": (result.fills, Fill),
        "order_events.csv": (result.order_events, OrderEvent),
        "cash_ledger.csv": (result.cash_ledger, CashLedgerEntry),
        "position_ledger.csv": (result.position_ledger, PositionLedgerEntry),
        "position_snapshots.csv": (result.position_snapshots, PositionSnapshot),
        "equity_curve.csv": (result.equity_curve, EquityPoint),
        "closed_trades.csv": (result.closed_trades, ClosedTrade),
        "audit_events.csv": (result.audit_events, AuditEvent),
    }
    for filename, (rows, row_type) in tables.items():
        _write_rows(output_dir / filename, rows, [item.name for item in fields(row_type)])

    _write_json(output_dir / "metrics.json", result.metrics)
    _write_json(output_dir / "reconciliation.json", result.reconciliation)
    _write_json(
        output_dir / "run.json",
        {
            "input_hash": result.input_hash,
            "config_hash": result.config_hash,
            "initial_cash": result.initial_cash,
            "final_cash": result.final_cash,
            "final_positions": result.final_positions,
            "final_cost_basis": result.final_cost_basis,
            "reconciliation": "PASS" if result.reconciliation.passed else "FAIL",
        },
    )
    hashes = {
        path.name: _sha256(path)
        for path in sorted(output_dir.iterdir())
        if path.is_file() and path.name != "manifest.json"
    }
    _write_json(output_dir / "manifest.json", hashes)
    return hashes
