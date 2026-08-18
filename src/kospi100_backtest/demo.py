from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from .config import engine_from_files
from .io import write_result
from .types import Bar, CorporateAction, CorporateActionType, Order, Side


def D(value: str) -> Decimal:
    return Decimal(value)


def synthetic_scenario() -> tuple[tuple[date, ...], tuple[Bar, ...], tuple[Order, ...], tuple[CorporateAction, ...], dict[date, Decimal]]:
    sessions = tuple(date.fromisoformat(value) for value in ("2022-12-29", "2023-01-02", "2023-01-03", "2023-01-04", "2023-01-05"))
    bars = (
        Bar(sessions[0], "A", D("9900"), D("10100"), D("9800"), D("10000")),
        Bar(sessions[1], "A", D("10000"), D("10500"), D("9800"), D("10200")),
        Bar(sessions[2], "A", D("10300"), D("11200"), D("9000"), D("10000")),
        Bar(sessions[0], "B", D("100"), D("102"), D("99"), D("100")),
        Bar(sessions[1], "B", D("110"), D("112"), D("108"), D("111")),
        Bar(sessions[0], "C", D("5000"), D("5050"), D("4950"), D("5000")),
        Bar(sessions[1], "C", None, None, None, None, tradable=False),
        Bar(sessions[1], "D", D("20000"), D("20200"), D("19800"), D("20100")),
        Bar(sessions[2], "D", D("20200"), D("20500"), D("20000"), D("20400")),
        Bar(sessions[3], "D", D("10200"), D("10400"), D("10100"), D("10300")),
        Bar(sessions[4], "D", D("10400"), D("10500"), D("10300"), D("10450")),
        Bar(sessions[1], "E", D("3000"), D("3050"), D("2950"), D("3010")),
        Bar(sessions[2], "E", D("3020"), D("3070"), D("3000"), D("3060"), max_buy_quantity=3),
        Bar(sessions[3], "E", D("3060"), D("3100"), D("3040"), D("3080")),
        Bar(sessions[4], "E", D("3090"), D("3120"), D("3070"), D("3110")),
    )
    orders = (
        Order("BUY-A", sessions[0], sessions[1], "A", Side.BUY, cash_budget=D("1000000"), limit_price=D("10500"), stop_price=D("9500"), target_price=D("11000"), priority=1),
        Order("BUY-B-GAP", sessions[0], sessions[1], "B", Side.BUY, quantity=100, limit_price=D("105"), priority=2),
        Order("BUY-C-HALT", sessions[0], sessions[1], "C", Side.BUY, quantity=10, limit_price=D("5200"), priority=3),
        Order("BUY-D", sessions[1], sessions[2], "D", Side.BUY, quantity=4, limit_price=D("21000"), priority=1),
        Order("BUY-E-PARTIAL", sessions[1], sessions[2], "E", Side.BUY, quantity=5, limit_price=D("3200"), priority=2),
        Order("SELL-D", sessions[3], sessions[4], "D", Side.SELL, quantity=None, reason="SYNTHETIC_EXIT"),
        Order("SELL-E", sessions[3], sessions[4], "E", Side.SELL, quantity=None, reason="SYNTHETIC_EXIT"),
    )
    actions = (
        CorporateAction("SPLIT-D-2X", sessions[3], "D", CorporateActionType.SPLIT, share_multiplier=D("2")),
    )
    benchmark = {
        sessions[0]: D("1000"),
        sessions[1]: D("1005"),
        sessions[2]: D("1001"),
        sessions[3]: D("1008"),
        sessions[4]: D("1010"),
    }
    return sessions, bars, orders, actions, benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description="Write deterministic Phase-2 synthetic reference ledgers")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("configs/phase2_engine.json"))
    parser.add_argument("--cost-schedule", type=Path, default=Path("configs/kospi_sell_cost_schedule.csv"))
    args = parser.parse_args()
    sessions, bars, orders, actions, benchmark = synthetic_scenario()
    engine = engine_from_files(args.config, args.cost_schedule)
    result = engine.run(sessions, bars, orders, corporate_actions=actions, benchmark_close=benchmark)
    hashes = write_result(result, args.output)
    print(json.dumps({"status": "PASS", "files": len(hashes), "input_hash": result.input_hash}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
