from __future__ import annotations

import csv
import gzip
from datetime import date
from pathlib import Path

from .validation import active_membership_ids, parse_date


class FinalOOSAccessError(PermissionError):
    pass


class PointInTimeDataset:
    """Read development data without exposing final OOS rows by default."""

    def __init__(self, development_root: Path, *, final_oos_start: date = date(2024, 1, 1)) -> None:
        self.development_root = Path(development_root)
        self.final_oos_start = final_oos_start

    def universe_on(self, session: date) -> set[str]:
        self._guard(session)
        memberships = self._read_gzip_csv("universe_membership.csv.gz")
        return active_membership_ids(memberships, session)

    def history_through(self, symbol_id: str, as_of: date, *, limit: int | None = None) -> list[dict[str, str]]:
        self._guard(as_of)
        rows = [
            row
            for row in self._read_gzip_csv("ohlcv_clean.csv.gz")
            if row.get("symbol_id") == symbol_id and parse_date(row["trade_date"]) <= as_of
        ]
        rows.sort(key=lambda row: row["trade_date"])
        return rows[-limit:] if limit is not None else rows

    def _guard(self, value: date) -> None:
        if value >= self.final_oos_start:
            raise FinalOOSAccessError(
                f"{value.isoformat()} is inside the sealed final-OOS period; ordinary development access is denied."
            )

    def _read_gzip_csv(self, filename: str) -> list[dict[str, str]]:
        path = self.development_root / filename
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))


class V24PointInTimeDataset:
    """Development-only reader for the production v24 daily tables."""

    def __init__(self, development_root: Path, *, final_oos_start: date = date(2024, 1, 1)) -> None:
        self.development_root = Path(development_root)
        self.final_oos_start = final_oos_start

    def universe_on(self, session: date, *, new_entry_only: bool = True) -> set[str]:
        self._guard(session)
        rows = self._read("membership_daily.csv.gz")
        result = set()
        for row in rows:
            if parse_date(row["date"]) != session or not _v24_true(row.get("is_member", "")):
                continue
            if new_entry_only and (not _v24_true(row.get("eligible_new_entry", "")) or not _v24_true(row.get("tradable", ""))):
                continue
            result.add(row["security_id"])
        return result

    def history_through(self, security_id: str, as_of: date, *, limit: int | None = None) -> list[dict[str, str]]:
        self._guard(as_of)
        rows = [
            row
            for row in self._read("feature_price_panel.csv.gz")
            if row.get("security_id") == security_id and parse_date(row["date"]) <= as_of
        ]
        rows.sort(key=lambda row: row["date"])
        return rows[-limit:] if limit is not None else rows

    def _guard(self, value: date) -> None:
        if value >= self.final_oos_start:
            raise FinalOOSAccessError(
                f"{value.isoformat()} is inside the sealed final-OOS period; ordinary development access is denied."
            )

    def _read(self, filename: str) -> list[dict[str, str]]:
        with gzip.open(self.development_root / filename, "rt", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))


def _v24_true(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "y"}
