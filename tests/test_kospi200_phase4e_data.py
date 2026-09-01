from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from kospi200_phase4e.materialize import PHYSICAL_CUTOFF, materialize_phase4e_release, sha256
from kospi200_phase5r.data import (
    FUNDAMENTAL_FEATURES,
    Phase5RInputs,
    audit_unresolved_action_candidates,
    build_score_panel,
    load_phase5r_inputs,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_csv_gz(path: Path, frame: pd.DataFrame, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(
        path,
        index=False,
        encoding=encoding,
        compression={"method": "gzip", "mtime": 0},
    )


class Phase4EDataTests(unittest.TestCase):
    def test_candidate_evidence_does_not_change_score_universe_or_percentiles(self) -> None:
        sessions = tuple(pd.bdate_range("2020-08-03", periods=70).date.astype(str))
        tickers = ("111111", "222222", "333333")
        membership = pd.DataFrame(
            [
                {
                    "date": day,
                    "ticker": ticker,
                    "security_id": f"KRX_COMMON:{ticker}",
                }
                for day in sessions
                for ticker in tickers
            ]
        )
        market_rows: list[dict[str, object]] = []
        for session_number, day in enumerate(sessions):
            for ticker_number, ticker in enumerate(tickers, start=1):
                close = 100.0 + ticker_number * 10.0 + session_number * (0.2 + ticker_number * 0.01)
                market_rows.append(
                    {
                        "date": day,
                        "ticker": ticker,
                        "security_id": f"KRX_COMMON:{ticker}",
                        "open": close,
                        "high": close * 1.01,
                        "low": close * 0.99,
                        "close": close,
                        "volume": 1000.0 + session_number,
                        "trading_value": close * (1000.0 + session_number),
                        "listed_shares": 1_000_000.0,
                        "market_cap": close * 1_000_000.0,
                        "mechanical_reset": False,
                        "price_valid": True,
                        "unresolved_action": False,
                    }
                )
        market = pd.DataFrame(market_rows)
        index_close = pd.Series(range(len(sessions)), dtype=float) * 0.3 + 300.0
        index = pd.DataFrame(
            {
                "date": sessions,
                "index_code": "1028",
                "open": index_close,
                "high": index_close * 1.01,
                "low": index_close * 0.99,
                "close": index_close,
            }
        )
        fundamental_rows: list[dict[str, object]] = []
        # 005930은 원천 fundamental에 극단값이 있어도 PIT membership/최종 U_t에 없다.
        for ticker, value in (
            ("111111", 1.0),
            ("222222", 2.0),
            ("333333", 100.0),
            ("005930", 1000.0),
        ):
            row: dict[str, object] = {
                "date": sessions[-1],
                "ticker": ticker,
                "security_id": f"KRX_COMMON:{ticker}",
            }
            row.update({factor: value for factor in FUNDAMENTAL_FEATURES})
            fundamental_rows.append(row)
        inputs = Phase5RInputs(
            membership=membership,
            market=market,
            sessions=sessions,
            index=index,
            fundamental=pd.DataFrame(fundamental_rows),
            audit={},
            paths={},
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_path = root / "candidates.csv"
            empty_path = root / "empty_candidates.csv"
            pd.DataFrame(
                [
                    {
                        "canonical_event_id": "CANDIDATE-C",
                        "ticker": "333333",
                        "filing_date": sessions[-2].replace("-", ""),
                        "event_type_candidate": "PAID_ISSUE",
                        "member_on_filing_date": True,
                    },
                    {
                        "canonical_event_id": "CANDIDATE-EXCLUDED",
                        "ticker": "005930",
                        "filing_date": sessions[-2].replace("-", ""),
                        "event_type_candidate": "MERGER",
                        "member_on_filing_date": True,
                    },
                ]
            ).to_csv(candidate_path, index=False)
            pd.DataFrame(
                columns=[
                    "canonical_event_id",
                    "ticker",
                    "filing_date",
                    "event_type_candidate",
                    "member_on_filing_date",
                ]
            ).to_csv(empty_path, index=False)
            candidate_market, candidate_audit, _ = audit_unresolved_action_candidates(
                market, candidate_path, date(2020, 12, 30)
            )
            empty_market, empty_audit, _ = audit_unresolved_action_candidates(
                market, empty_path, date(2020, 12, 30)
            )
            candidate_score = build_score_panel(inputs._replace(market=candidate_market))
            empty_score = build_score_panel(inputs._replace(market=empty_market))

        compare = ["date", "ticker", *[f"{factor}__phase4e_percentile" for factor in FUNDAMENTAL_FEATURES]]
        pd.testing.assert_frame_equal(
            candidate_score[compare].reset_index(drop=True),
            empty_score[compare].reset_index(drop=True),
        )
        final = candidate_score.loc[candidate_score["date"].eq(sessions[-1])].sort_values("ticker")
        expected = [1.0 / 3.0, 2.0 / 3.0, 1.0]
        self.assertEqual(final["ticker"].tolist(), ["111111", "222222", "333333"])
        self.assertEqual(final["roe__phase4e_percentile"].tolist(), expected)
        for factor in FUNDAMENTAL_FEATURES:
            self.assertEqual(
                final[f"{factor}__phase4e_percentile"].tolist(),
                expected,
                factor,
            )
        self.assertFalse(candidate_market["unresolved_action"].any())
        self.assertFalse(empty_market["unresolved_action"].any())
        self.assertEqual(candidate_audit["corporate_action_source_rows"], 2)
        self.assertEqual(empty_audit["corporate_action_source_rows"], 0)
        self.assertEqual(
            candidate_audit["corporate_action_semantics"],
            "UNRESOLVED_FILING_CANDIDATE_EVIDENCE_NOT_TIMING_BOUNDARY",
        )

    def test_unresolved_filing_is_audit_evidence_only(self) -> None:
        sessions = tuple(
            pd.to_datetime(
                [
                    "2020-12-21",
                    "2020-12-22",
                    "2020-12-23",
                    "2020-12-24",
                    "2020-12-28",
                    "2020-12-29",
                    "2020-12-30",
                ]
            ).date.astype(str)
        )
        market = pd.DataFrame(
            [
                {
                    "date": day,
                    "ticker": ticker,
                    "mechanical_reset": day == sessions[-1] and ticker == "111111",
                    "unresolved_action": False,
                }
                for day in sessions
                for ticker in ("111111", "222222")
            ]
        )
        actions = pd.DataFrame(
            [
                # 실제 membership으로는 12/22 구성종목이다. bogus False를 무시해야 한다.
                {"canonical_event_id": "A", "ticker": "111111", "filing_date": "20201222", "member_on_filing_date": False},
                # 다음 세션 12/28에 비구성종목이다. bogus True여도 block하면 안 된다.
                {"canonical_event_id": "B", "ticker": "222222", "filing_date": "20201224", "member_on_filing_date": True},
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            action_path = Path(directory) / "unresolved.csv"
            actions.to_csv(action_path, index=False)
            output, audit, _ = audit_unresolved_action_candidates(
                market,
                action_path,
                date(2020, 12, 30),
            )
        self.assertFalse(output["unresolved_action"].any())
        self.assertTrue(
            output.loc[
                output["ticker"].eq("111111") & output["date"].eq("2020-12-30"),
                "mechanical_reset",
            ].item()
        )
        self.assertEqual(audit["corporate_action_candidate_rows_at_or_before_data_end"], 2)
        self.assertEqual(audit["corporate_action_timing_boundaries_emitted"], 0)
        self.assertEqual(audit["corporate_action_blocked_market_rows"], 0)
        self.assertEqual(audit["corporate_action_forced_exit_rows"], 0)
        self.assertEqual(audit["corporate_action_reset_boundaries_emitted"], 0)
        self.assertTrue(audit["corporate_action_member_on_filing_date_ignored"])

    def test_loader_accepts_earlier_phase4e_duck_config_and_records_ca_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            membership_root = root / "membership"
            market_root = root / "market"
            sessions = ("2020-12-28", "2020-12-29", "2020-12-30")
            for day in sessions:
                compact = day.replace("-", "")
                membership_path = membership_root / "2020" / f"{compact}.csv"
                membership_path.parent.mkdir(parents=True, exist_ok=True)
                pd.DataFrame(
                    {"date": [day, day], "ticker": ["111111", "222222"], "name": ["A", "B"]}
                ).to_csv(membership_path, index=False)
                _write_csv_gz(
                    market_root / "2020" / f"{compact}.csv.gz",
                    pd.DataFrame(
                        {
                            "종목코드": ["111111", "222222"],
                            "시가": [100, 200],
                            "고가": [102, 202],
                            "저가": [99, 199],
                            "종가": [101, 201],
                            "거래량": [1000, 2000],
                            "거래대금": [101000, 402000],
                            "상장주식수": [1000000, 2000000],
                            "시가총액": [101000000, 402000000],
                        }
                    ),
                    encoding="cp949",
                )

            index_path = root / "release" / "index.csv.gz"
            _write_csv_gz(
                index_path,
                pd.DataFrame(
                    {
                        "date": sessions,
                        "index_code": ["1028"] * 3,
                        "open": [300, 301, 302],
                        "high": [301, 302, 303],
                        "low": [299, 300, 301],
                        "close": [300, 301, 302],
                    }
                ),
            )
            fundamental_path = root / "release" / "fundamental.csv.gz"
            rows: list[dict[str, object]] = []
            for day in sessions:
                for ticker, value in (("111111", 1.0), ("222222", 2.0)):
                    row: dict[str, object] = {"date": day, "ticker": ticker}
                    row.update({factor: value for factor in FUNDAMENTAL_FEATURES})
                    rows.append(row)
            _write_csv_gz(fundamental_path, pd.DataFrame(rows))
            _write_json(
                fundamental_path.parent / "manifest.json",
                {"max_date": "2020-12-30", "protected_oos_accessed": False},
            )
            action_path = root / "release" / "actions.csv.gz"
            _write_csv_gz(
                action_path,
                pd.DataFrame(
                    [
                        {
                            "canonical_event_id": "A",
                            "ticker": "111111",
                            "filing_date": "20201228",
                            "member_on_filing_date": False,
                        }
                    ]
                ),
            )
            config = SimpleNamespace(
                membership_root=membership_root,
                market_roots=(market_root,),
                fundamental_panel=fundamental_path,
                index_file=index_path,
                corporate_action_file=action_path,
                data_start=date(2020, 12, 28),
                fundamental_start=date(2020, 12, 28),
                data_end=date(2020, 12, 30),
                excluded_tickers=frozenset({"005930", "000660"}),
                excluded_security_ids=frozenset(
                    {"KRX_COMMON:005930", "KRX_COMMON:000660"}
                ),
            )
            action_hash = sha256(action_path)
            inputs = load_phase5r_inputs(config)

        self.assertEqual(inputs.sessions, sessions)
        self.assertIn("roe__phase4e_percentile", inputs.fundamental.columns)
        self.assertFalse(inputs.market["unresolved_action"].any())
        self.assertEqual(inputs.paths["corporate_action"], (action_path,))
        self.assertEqual(inputs.audit["corporate_action_source_sha256"], action_hash)
        self.assertEqual(inputs.audit["corporate_action_candidate_rows_at_or_before_data_end"], 1)
        self.assertEqual(inputs.audit["corporate_action_blocked_market_rows"], 0)
        self.assertEqual(
            inputs.audit["corporate_action_semantics"],
            "UNRESOLVED_FILING_CANDIDATE_EVIDENCE_NOT_TIMING_BOUNDARY",
        )
        self.assertEqual(inputs.audit["maximum_permitted_date"], "2020-12-30")

    def test_materializer_is_deterministic_physically_bounded_and_preserves_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "processed" / "phase4e"
            fundamental_source = source / "fundamental.csv.gz"
            index_source = source / "index.csv.gz"
            action_source = source / "actions.csv"
            fundamental_manifest = source / "fundamental_manifest.json"
            action_manifest = source / "action_manifest.json"
            _write_csv_gz(
                fundamental_source,
                pd.DataFrame(
                    {
                        "date": ["2020-12-29", "2020-12-30", "2021-01-04"],
                        "ticker": ["111111", "111111", "111111"],
                        "roe": ["0.1", "0.2", "9.9"],
                    }
                ),
            )
            _write_json(
                fundamental_manifest,
                {"max_date": "2023-12-28", "protected_oos_accessed": False},
            )
            _write_csv_gz(
                index_source,
                pd.DataFrame(
                    {
                        "date": ["2004-01-02", "2020-12-30", "2021-01-04"],
                        "index_code": ["1028", "1028", "1028"],
                        "open": [1, 2, 3],
                        "high": [1, 2, 3],
                        "low": [1, 2, 3],
                        "close": [1, 2, 3],
                    }
                ),
            )
            pd.DataFrame(
                {
                    "canonical_event_id": ["A", "B", "C"],
                    "ticker": ["111111", "111111", "111111"],
                    "filing_date": ["20201230", "20201231", "20210104"],
                    "member_on_filing_date": [False, True, True],
                }
            ).to_csv(action_source, index=False)
            _write_json(
                action_manifest,
                {"status": "BLOCKED_PENDING_VERIFIED_TERMS", "promoted_mechanical_adjustments": 0},
            )
            config = SimpleNamespace(
                payload={
                    "materialization_sources": {
                        "fundamental_panel": str(fundamental_source),
                        "fundamental_manifest": str(fundamental_manifest),
                        "index_file": str(index_source),
                        "corporate_action_file": str(action_source),
                        "corporate_action_manifest": str(action_manifest),
                    }
                },
                data_start=date(2004, 1, 2),
                data_end=PHYSICAL_CUTOFF,
                data_release_id="SYNTHETIC-P4E",
                fundamental_panel=output / "fundamental_factor_panel.csv.gz",
                index_file=output / "kospi200_index_ohlcv.csv.gz",
                corporate_action_file=output / "corporate_action_candidates.csv.gz",
                data_release_manifest=output / "manifest.json",
            )
            sources = (
                fundamental_source,
                fundamental_manifest,
                index_source,
                action_source,
                action_manifest,
            )
            before = {path: sha256(path) for path in sources}
            first = materialize_phase4e_release(config)
            first_hashes = {
                name: sha256(path)
                for name, path in {
                    "fundamental": config.fundamental_panel,
                    "index": config.index_file,
                    "actions": config.corporate_action_file,
                    "manifest": config.data_release_manifest,
                }.items()
            }
            second = materialize_phase4e_release(config)
            second_hashes = {
                name: sha256(path)
                for name, path in {
                    "fundamental": config.fundamental_panel,
                    "index": config.index_file,
                    "actions": config.corporate_action_file,
                    "manifest": config.data_release_manifest,
                }.items()
            }
            after = {path: sha256(path) for path in sources}
            released_fundamental = pd.read_csv(config.fundamental_panel)
            released_index = pd.read_csv(config.index_file, dtype={"index_code": str})
            released_actions = pd.read_csv(config.corporate_action_file, dtype={"filing_date": str})
            manifest = json.loads(config.data_release_manifest.read_text(encoding="utf-8"))
            manifest_output_hashes = {
                name: entry["sha256"] for name, entry in manifest["outputs"].items()
            }
            actual_output_hashes = {
                "fundamental_panel": sha256(config.fundamental_panel),
                "index_file": sha256(config.index_file),
                "corporate_action_file": sha256(config.corporate_action_file),
            }

        self.assertEqual(before, after)
        self.assertEqual(first_hashes, second_hashes)
        self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])
        self.assertEqual(released_fundamental["date"].max(), "2020-12-30")
        self.assertEqual(released_index["date"].max(), "2020-12-30")
        self.assertEqual(released_actions["filing_date"].tolist(), ["20201230"])
        self.assertEqual(
            released_actions["materialized_action_semantics"].tolist(),
            ["UNRESOLVED_FILING_CANDIDATE_EVIDENCE_NOT_TIMING_BOUNDARY"],
        )
        self.assertFalse(manifest["raw_modified"])
        self.assertFalse(manifest["protected_oos_accessed"])
        self.assertEqual(manifest["post_cutoff_rows_written"], 0)
        self.assertEqual(manifest["corporate_action_timing_boundaries_emitted"], 0)
        self.assertEqual(manifest["corporate_action_reset_boundaries_emitted"], 0)
        self.assertEqual(manifest["corporate_action_blocked_rows"], 0)
        self.assertEqual(manifest["corporate_action_forced_exit_rows"], 0)
        self.assertEqual(
            manifest["corporate_action_semantics"],
            "UNRESOLVED_FILING_CANDIDATE_EVIDENCE_NOT_TIMING_BOUNDARY",
        )
        self.assertEqual(manifest_output_hashes, actual_output_hashes)


if __name__ == "__main__":
    unittest.main()
