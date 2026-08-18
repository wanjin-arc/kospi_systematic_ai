from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from .costs import CostSchedule, ExecutionCostModel
from .engine import BacktestEngine, EngineConfig


def engine_from_files(engine_config_path: Path, cost_schedule_path: Path) -> BacktestEngine:
    payload = json.loads(engine_config_path.read_text(encoding="utf-8"))
    frozen_requirements = {
        "long_only": True,
        "whole_shares_only": True,
        "allow_pyramiding": False,
        "same_bar_stop_target_policy": "STOP_FIRST",
        "day_order_remainder_policy": "CANCEL",
        "unresolved_corporate_action_policy": "FAIL_CLOSED",
        "final_oos_access": "DENIED_UNTIL_PHASE_8",
    }
    for key, expected in frozen_requirements.items():
        if payload.get(key) != expected:
            raise ValueError(f"unsupported Phase-2 configuration: {key}")
    config = EngineConfig(
        initial_cash=Decimal(payload["initial_cash_krw"]),
        allow_pyramiding=payload["allow_pyramiding"],
        same_bar_policy=payload["same_bar_stop_target_policy"],
        day_order_remainder_policy=payload["day_order_remainder_policy"],
        max_positions=payload.get("max_positions"),
    )
    costs = ExecutionCostModel(
        schedule=CostSchedule.from_csv(cost_schedule_path),
        commission_rate=Decimal(payload["commission_rate_per_side"]),
        buy_slippage_rate=Decimal(payload["buy_slippage_rate"]),
        sell_slippage_rate=Decimal(payload["sell_slippage_rate"]),
        money_quantum=Decimal(payload["money_quantum_krw"]),
    )
    return BacktestEngine(config=config, cost_model=costs)
