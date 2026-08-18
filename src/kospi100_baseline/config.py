from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class Period:
    name: str
    start: date
    end: date


@dataclass(frozen=True)
class BaselineConfig:
    path: Path
    payload: Mapping[str, Any]
    experiment_id: str
    data_root: Path
    maximum_permitted_date: date
    periods: Mapping[str, Period]
    holding_sessions: tuple[int, ...]
    maximum_holdings: tuple[int, ...]
    initial_cash: Decimal
    commission_rate: Decimal
    slippage_rate: Decimal
    tax_schedule_path: Path
    random_seed: int

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


def load_config(path: Path) -> BaselineConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != "phase3-baseline-v1":
        raise ValueError("unsupported Phase-3 baseline configuration")
    if payload.get("required_partition_role") != "development":
        raise ValueError("Phase 3 can load only the development partition")
    if payload.get("final_oos_access") != "DENIED_UNTIL_PHASE_8":
        raise ValueError("final OOS must remain denied before Phase 8")
    if payload["selection"].get("partition") != "validation_only":
        raise ValueError("candidate selection must use validation only")
    if payload["selection"].get("development_test_runs") != 1:
        raise ValueError("development test is limited to one frozen candidate")

    holding = tuple(int(value) for value in payload["candidates"]["holding_sessions"])
    holdings = tuple(int(value) for value in payload["candidates"]["maximum_holdings"])
    if holding != (5, 10, 20) or holdings != (5, 10, 15):
        raise ValueError("Phase-3 parameter family is frozen to H={5,10,20}, N={5,10,15}")

    periods = {
        name: Period(name, date.fromisoformat(bounds[0]), date.fromisoformat(bounds[1]))
        for name, bounds in payload["periods"].items()
    }
    expected = {
        "train": (date(2011, 1, 1), date(2018, 12, 31)),
        "validation": (date(2019, 1, 1), date(2021, 12, 31)),
        "development_test": (date(2022, 1, 1), date(2023, 12, 31)),
    }
    if {key: (value.start, value.end) for key, value in periods.items()} != expected:
        raise ValueError("research partitions differ from the frozen protocol")

    root = Path(payload["data_root"])
    lowered_parts = {part.lower() for part in root.parts}
    if "sealed" in lowered_parts or "final_oos_v24" in lowered_parts:
        raise PermissionError("sealed final OOS paths are forbidden in Phase 3")
    tax_path = Path(payload["costs"]["sell_tax_schedule"])
    return BaselineConfig(
        path=path,
        payload=payload,
        experiment_id=str(payload["experiment_id"]),
        data_root=root,
        maximum_permitted_date=date.fromisoformat(payload["maximum_permitted_date"]),
        periods=periods,
        holding_sessions=holding,
        maximum_holdings=holdings,
        initial_cash=Decimal(payload["portfolio"]["initial_cash_krw"]),
        commission_rate=Decimal(payload["costs"]["commission_rate_per_side"]),
        slippage_rate=Decimal(payload["costs"]["slippage_rate_per_side"]),
        tax_schedule_path=tax_path,
        random_seed=int(payload["random_seed"]),
    )
