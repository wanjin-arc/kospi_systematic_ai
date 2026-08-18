from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path

from .types import Side, ZERO


@dataclass(frozen=True)
class CostBand:
    effective_from: date
    effective_to: date
    transaction_tax_rate: Decimal
    rural_special_tax_rate: Decimal
    source: str = ""

    def __post_init__(self) -> None:
        if self.effective_from > self.effective_to:
            raise ValueError("cost band start must not exceed end")
        if self.transaction_tax_rate < ZERO or self.rural_special_tax_rate < ZERO:
            raise ValueError("tax rates cannot be negative")

    def contains(self, session: date) -> bool:
        return self.effective_from <= session <= self.effective_to


class CostSchedule:
    def __init__(self, bands: tuple[CostBand, ...]) -> None:
        if not bands:
            raise ValueError("at least one cost band is required")
        ordered = tuple(sorted(bands, key=lambda item: item.effective_from))
        for previous, current in zip(ordered, ordered[1:]):
            if current.effective_from <= previous.effective_to:
                raise ValueError("cost bands overlap")
            if (current.effective_from - previous.effective_to).days != 1:
                raise ValueError("cost bands contain a calendar gap")
        self.bands = ordered

    def rates_on(self, session: date) -> tuple[Decimal, Decimal]:
        for band in self.bands:
            if band.contains(session):
                return band.transaction_tax_rate, band.rural_special_tax_rate
        raise KeyError(f"no verified sell-tax rate for {session.isoformat()}")

    @classmethod
    def from_csv(cls, path: Path) -> "CostSchedule":
        bands: list[CostBand] = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                bands.append(
                    CostBand(
                        effective_from=date.fromisoformat(row["effective_from"]),
                        effective_to=date.fromisoformat(row["effective_to"]),
                        transaction_tax_rate=Decimal(row["transaction_tax_rate"]),
                        rural_special_tax_rate=Decimal(row["rural_special_tax_rate"]),
                        source=row.get("source", ""),
                    )
                )
        return cls(tuple(bands))


@dataclass(frozen=True)
class ExecutionCostModel:
    schedule: CostSchedule
    commission_rate: Decimal = Decimal("0.0002")
    buy_slippage_rate: Decimal = Decimal("0.001")
    sell_slippage_rate: Decimal = Decimal("0.001")
    money_quantum: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        if min(self.commission_rate, self.buy_slippage_rate, self.sell_slippage_rate) < ZERO:
            raise ValueError("cost and slippage rates cannot be negative")
        if self.money_quantum <= ZERO:
            raise ValueError("money_quantum must be positive")

    def fill_price(self, side: Side, reference_price: Decimal) -> Decimal:
        if reference_price <= ZERO:
            raise ValueError("reference price must be positive")
        rate = self.buy_slippage_rate if side is Side.BUY else -self.sell_slippage_rate
        return reference_price * (Decimal("1") + rate)

    def commission(self, gross_notional: Decimal) -> Decimal:
        return self._round_cash(gross_notional * self.commission_rate)

    def sell_taxes(self, session: date, gross_notional: Decimal) -> tuple[Decimal, Decimal]:
        transaction_rate, rural_rate = self.schedule.rates_on(session)
        return self._round_cash(gross_notional * transaction_rate), self._round_cash(gross_notional * rural_rate)

    def _round_cash(self, value: Decimal) -> Decimal:
        return value.quantize(self.money_quantum, rounding=ROUND_FLOOR)


def default_kospi_cost_schedule() -> CostSchedule:
    """Verified KOSPI sell-side statutory schedule for the frozen 2011-2025 research window."""

    return CostSchedule(
        (
            CostBand(date(2011, 1, 1), date(2019, 6, 2), Decimal("0.0015"), Decimal("0.0015")),
            CostBand(date(2019, 6, 3), date(2020, 12, 31), Decimal("0.0010"), Decimal("0.0015")),
            CostBand(date(2021, 1, 1), date(2022, 12, 31), Decimal("0.0008"), Decimal("0.0015")),
            CostBand(date(2023, 1, 1), date(2023, 12, 31), Decimal("0.0005"), Decimal("0.0015")),
            CostBand(date(2024, 1, 1), date(2024, 12, 31), Decimal("0.0003"), Decimal("0.0015")),
            CostBand(date(2025, 1, 1), date(2025, 12, 31), Decimal("0"), Decimal("0.0015")),
        )
    )
