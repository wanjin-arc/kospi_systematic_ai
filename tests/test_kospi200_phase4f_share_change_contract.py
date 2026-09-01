from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from kospi100_backtest.costs import CostBand, CostSchedule
from kospi200_phase5s.data import (
    STOCK_FEATURES,
    _load_market,
    _load_membership,
    _technical_features,
)
from kospi200_phase5s.labels import LABEL_COLUMNS, attach_reset_safe_labels


TICKER = "123456"
SECURITY_ID = f"KRX_COMMON:{TICKER}"


def _write_market_day(
    root: Path,
    day: str,
    rows: list[tuple[str, object, float]],
) -> None:
    path = root / day[:4] / f"{day.replace('-', '')}.csv.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_rows: list[dict[str, object]] = []
    for ticker, listed_shares, close in rows:
        frame_rows.append(
            {
                "ISU_SRT_CD": ticker,
                "TDD_OPNPRC": close,
                "TDD_HGPRC": close * 1.01,
                "TDD_LWPRC": close * 0.99,
                "TDD_CLSPRC": close,
                "ACC_TRDVOL": 1_000,
                "ACC_TRDVAL": close * 1_000,
                "LIST_SHRS": listed_shares,
                "MKTCAP": close * float(listed_shares)
                if listed_shares is not None and np.isfinite(float(listed_shares))
                else "",
            }
        )
    pd.DataFrame(frame_rows).to_csv(
        path,
        index=False,
        encoding="cp949",
        compression={"method": "gzip", "mtime": 0},
    )


def _market_config(root: Path, start: str, end: str) -> SimpleNamespace:
    return SimpleNamespace(
        market_roots=(root,),
        data_start=date.fromisoformat(start),
        data_end=date.fromisoformat(end),
        excluded_tickers=frozenset({"005930", "000660"}),
        excluded_security_ids=frozenset(
            {"KRX_COMMON:005930", "KRX_COMMON:000660"}
        ),
        share_change_gross_ratio_threshold=1.20,
    )


def _label_fixture(
    rows: int = 30,
) -> tuple[pd.DataFrame, pd.DataFrame, tuple[str, ...], pd.DataFrame, pd.DataFrame]:
    sessions = tuple(pd.bdate_range("2011-01-03", periods=rows).date.astype(str))
    prices = np.linspace(100.0, 130.0, rows)
    market = pd.DataFrame(
        {
            "date": sessions,
            "ticker": TICKER,
            "security_id": SECURITY_ID,
            "open": prices,
            "high": prices * 1.01,
            "low": prices * 0.99,
            "close": prices,
            "mechanical_reset": False,
            "unresolved_action": False,
            "unresolved_share_change_candidate": False,
            "listed_shares_observation_gap": False,
        }
    )
    index = pd.DataFrame(
        {"date": sessions, "open": np.linspace(200.0, 220.0, rows)}
    )
    membership = pd.DataFrame(
        {"date": sessions, "ticker": TICKER, "security_id": SECURITY_ID}
    )
    signals = pd.DataFrame(
        {"date": [sessions[0]], "ticker": [TICKER], "security_id": [SECURITY_ID]}
    )
    return signals, market, sessions, index, membership


def _schedule() -> CostSchedule:
    return CostSchedule(
        (
            CostBand(
                date(2011, 1, 1),
                date(2012, 12, 31),
                Decimal("0.0015"),
                Decimal("0.0015"),
            ),
        )
    )


class Phase4FShareChangeDetectionTests(unittest.TestCase):
    def test_membership_rejects_every_noncanonical_raw_ticker(self) -> None:
        day = "2020-01-02"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "2020" / "20200102.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                {"date": [day], "ticker": ["00680K"], "name": ["비정규"]}
            ).to_csv(path, index=False, encoding="utf-8")
            config = SimpleNamespace(
                membership_root=root,
                data_start=date.fromisoformat(day),
                data_end=date.fromisoformat(day),
                excluded_tickers=frozenset({"005930", "000660"}),
                excluded_security_ids=frozenset(
                    {"KRX_COMMON:005930", "KRX_COMMON:000660"}
                ),
            )
            with self.assertRaisesRegex(ValueError, "비정규 raw ticker"):
                _load_membership(config)

    def test_market_noncanonical_ticker_collision_with_pit_member_fails_closed(self) -> None:
        day = "2020-01-02"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_market_day(root, day, [("00680K", 100.0, 100.0)])
            with self.assertRaisesRegex(ValueError, "정규화 충돌"):
                _load_market(_market_config(root, day, day), {"000680"})

    def test_candidate_depends_on_listed_shares_not_effective_day_price(self) -> None:
        sessions = ("2020-01-02", "2020-01-03", "2020-01-06")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ordinary = root / "ordinary"
            compensated = root / "compensated"
            ordinary_closes = (100.0, 100.0, 101.0)
            compensated_closes = (100.0, 100.0 / 1.20, 101.0)
            shares = (100.0, 120.0, 120.0)
            for day, share_count, ordinary_close, compensated_close in zip(
                sessions, shares, ordinary_closes, compensated_closes
            ):
                _write_market_day(
                    ordinary, day, [(TICKER, share_count, ordinary_close)]
                )
                _write_market_day(
                    compensated, day, [(TICKER, share_count, compensated_close)]
                )
            ordinary_market, _, _ = _load_market(
                _market_config(ordinary, sessions[0], sessions[-1]), {TICKER}
            )
            compensated_market, _, _ = _load_market(
                _market_config(compensated, sessions[0], sessions[-1]), {TICKER}
            )

        expected = [False, True, False]
        self.assertEqual(
            ordinary_market["unresolved_share_change_candidate"].tolist(), expected
        )
        self.assertEqual(
            compensated_market["unresolved_share_change_candidate"].tolist(), expected
        )
        self.assertNotEqual(
            ordinary_market["mechanical_reset"].tolist(),
            compensated_market["mechanical_reset"].tolist(),
            "가격은 진단용 mechanical subset에는 영향을 줄 수 있지만 candidate에는 영향을 주면 안 됩니다.",
        )

    def test_log_symmetric_gross_ratio_threshold_includes_120_percent_boundaries(self) -> None:
        sessions = ("2020-01-02", "2020-01-03")
        first = {
            "111111": 100.0,
            "222222": 100.0,
            "333333": 120.0,
            "444444": 100.0,
        }
        second = {
            "111111": 119.9,
            "222222": 120.0,
            "333333": 100.0,
            "444444": 80.0,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_market_day(
                root,
                sessions[0],
                [(ticker, shares, 100.0) for ticker, shares in first.items()],
            )
            _write_market_day(
                root,
                sessions[1],
                [(ticker, shares, 100.0) for ticker, shares in second.items()],
            )
            market, _, _ = _load_market(
                _market_config(root, sessions[0], sessions[-1]), set(first)
            )

        current = market.loc[market["date"].eq(sessions[1])].set_index("ticker")
        self.assertFalse(bool(current.loc["111111", "unresolved_share_change_candidate"]))
        self.assertTrue(bool(current.loc["222222", "unresolved_share_change_candidate"]))
        self.assertTrue(
            bool(current.loc["333333", "unresolved_share_change_candidate"]),
            "하락 경계는 1/1.20을 포함해야 합니다.",
        )
        self.assertTrue(bool(current.loc["444444", "unresolved_share_change_candidate"]))

    def test_invalid_share_observations_emit_gap_boundary_not_candidate(self) -> None:
        sessions = ("2020-01-02", "2020-01-03")
        first = {
            "111111": 100.0,
            "222222": 0.0,
            "333333": -1.0,
            "444444": None,
            "555555": 100.0,
            "666666": 100.0,
        }
        second = {
            "111111": None,
            "222222": 100.0,
            "333333": 100.0,
            "444444": 100.0,
            "555555": 100.0,
            "666666": np.inf,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_market_day(
                root,
                sessions[0],
                [(ticker, shares, 100.0) for ticker, shares in first.items()],
            )
            _write_market_day(
                root,
                sessions[1],
                [(ticker, shares, 100.0) for ticker, shares in second.items()],
            )
            market, _, _ = _load_market(
                _market_config(root, sessions[0], sessions[-1]), set(first)
            )

        current = market.loc[market["date"].eq(sessions[1])].set_index("ticker")
        for ticker in ("111111", "222222", "333333", "444444", "666666"):
            with self.subTest(ticker=ticker):
                self.assertFalse(
                    bool(current.loc[ticker, "unresolved_share_change_candidate"])
                )
                self.assertTrue(
                    bool(current.loc[ticker, "listed_shares_observation_gap"])
                )
        self.assertFalse(bool(current.loc["555555", "listed_shares_observation_gap"]))
        first_valid = market.loc[
            market["date"].eq(sessions[0]) & market["ticker"].eq("555555")
        ].iloc[0]
        self.assertFalse(
            bool(first_valid["listed_shares_observation_gap"]),
            "정상 주식수의 첫 관측은 observation gap이 아닙니다.",
        )

    def test_nonconsecutive_ticker_rows_are_never_compared(self) -> None:
        sessions = ("2020-01-02", "2020-01-03", "2020-01-06")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_market_day(
                root,
                sessions[0],
                [("111111", 100.0, 100.0), ("222222", 100.0, 100.0)],
            )
            _write_market_day(root, sessions[1], [("222222", 100.0, 100.0)])
            _write_market_day(
                root,
                sessions[2],
                [("111111", 300.0, 100.0), ("222222", 100.0, 100.0)],
            )
            market, _, _ = _load_market(
                _market_config(root, sessions[0], sessions[-1]),
                {"111111", "222222"},
            )

        resumed = market.loc[
            market["date"].eq(sessions[-1]) & market["ticker"].eq("111111")
        ].iloc[0]
        self.assertFalse(bool(resumed["unresolved_share_change_candidate"]))
        self.assertFalse(bool(resumed["listed_shares_observation_gap"]))


class Phase4FTechnicalBoundaryTests(unittest.TestCase):
    @staticmethod
    def _technical_market(boundary_column: str) -> tuple[pd.DataFrame, tuple[str, ...]]:
        sessions = tuple(pd.bdate_range("2020-01-02", periods=130).date.astype(str))
        close = np.linspace(100.0, 150.0, len(sessions))
        frame = pd.DataFrame(
            {
                "date": sessions,
                "ticker": TICKER,
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": np.linspace(1_000.0, 2_000.0, len(sessions)),
                "mechanical_reset": False,
                "unresolved_share_change_candidate": False,
                "listed_shares_observation_gap": False,
            }
        )
        frame.loc[65, boundary_column] = True
        return frame, sessions

    def test_candidate_and_observation_gap_restart_technical_segment(self) -> None:
        for boundary_column in (
            "unresolved_share_change_candidate",
            "listed_shares_observation_gap",
        ):
            with self.subTest(boundary_column=boundary_column):
                market, sessions = self._technical_market(boundary_column)
                result = _technical_features(market, sessions).reset_index(drop=True)
                self.assertTrue(result.loc[65, list(STOCK_FEATURES)].isna().all())
                self.assertAlmostEqual(
                    float(result.loc[66, "return_1"]),
                    float(market.loc[66, "close"] / market.loc[65, "close"] - 1.0),
                )
                self.assertTrue(pd.isna(result.loc[124, "return_60"]))
                self.assertTrue(np.isfinite(result.loc[125, "return_60"]))

    def test_missing_share_boundary_column_fails_closed(self) -> None:
        market, sessions = self._technical_market(
            "unresolved_share_change_candidate"
        )
        for column in (
            "unresolved_share_change_candidate",
            "listed_shares_observation_gap",
        ):
            with self.subTest(column=column):
                with self.assertRaises((KeyError, ValueError)):
                    _technical_features(market.drop(columns=column), sessions)


class Phase4FShareChangeLabelTests(unittest.TestCase):
    @staticmethod
    def _attach(
        fixture: tuple[
            pd.DataFrame,
            pd.DataFrame,
            tuple[str, ...],
            pd.DataFrame,
            pd.DataFrame,
        ]
    ) -> tuple[pd.DataFrame, dict[str, object]]:
        signals, market, sessions, index, membership = fixture
        return attach_reset_safe_labels(
            signals,
            market,
            sessions,
            index,
            membership,
            _schedule(),
        )

    def test_candidate_crossing_invalidates_label_and_clears_all_targets(self) -> None:
        fixture = list(_label_fixture())
        fixture[1] = fixture[1].copy()
        fixture[1].loc[10, "unresolved_share_change_candidate"] = True
        labeled, audit = self._attach(tuple(fixture))  # type: ignore[arg-type]
        row = labeled.iloc[0]
        self.assertFalse(bool(row["label_valid"]))
        self.assertIn(
            "UNRESOLVED_SHARE_CHANGE_CROSSING", row["label_invalid_reason"]
        )
        self.assertTrue(labeled.loc[:, list(LABEL_COLUMNS)].isna().all(axis=None))
        self.assertEqual(audit["unresolved_share_change_crossing_rows_excluded"], 1)

    def test_observation_gap_crossing_invalidates_label_and_clears_all_targets(self) -> None:
        fixture = list(_label_fixture())
        fixture[1] = fixture[1].copy()
        fixture[1].loc[10, "listed_shares_observation_gap"] = True
        labeled, audit = self._attach(tuple(fixture))  # type: ignore[arg-type]
        row = labeled.iloc[0]
        self.assertFalse(bool(row["label_valid"]))
        self.assertIn("LISTED_SHARES_OBSERVATION_GAP", row["label_invalid_reason"])
        self.assertTrue(labeled.loc[:, list(LABEL_COLUMNS)].isna().all(axis=None))
        self.assertEqual(audit["listed_shares_observation_gap_rows_excluded"], 1)

    def test_missing_share_boundary_column_fails_closed(self) -> None:
        for column in (
            "unresolved_share_change_candidate",
            "listed_shares_observation_gap",
        ):
            fixture = list(_label_fixture())
            fixture[1] = fixture[1].drop(columns=column)
            with self.subTest(column=column), self.assertRaises((KeyError, ValueError)):
                self._attach(tuple(fixture))  # type: ignore[arg-type]

    def test_null_share_boundary_is_treated_as_crossing(self) -> None:
        for column, reason in (
            (
                "unresolved_share_change_candidate",
                "UNRESOLVED_SHARE_CHANGE_CROSSING",
            ),
            ("listed_shares_observation_gap", "LISTED_SHARES_OBSERVATION_GAP"),
        ):
            fixture = list(_label_fixture())
            fixture[1] = fixture[1].copy()
            fixture[1][column] = fixture[1][column].astype("boolean")
            fixture[1].loc[10, column] = pd.NA
            labeled, _ = self._attach(tuple(fixture))  # type: ignore[arg-type]
            with self.subTest(column=column):
                self.assertFalse(bool(labeled.iloc[0]["label_valid"]))
                self.assertIn(reason, labeled.iloc[0]["label_invalid_reason"])


if __name__ == "__main__":
    unittest.main()
