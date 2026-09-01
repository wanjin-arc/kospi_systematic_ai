from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from kospi200_phase5r.runner import (
    _integrity_decision,
    _phase5r_share_reset_candidates,
    _raw_ticker_identity_audit,
)


def _membership(dates: list[str], ticker: str = "035720") -> pd.DataFrame:
    return pd.DataFrame({"date": dates, "ticker": [ticker] * len(dates)})


class Phase5RShareResetCandidateTests(unittest.TestCase):
    def test_observed_kakao_reset_is_candidate_only_and_never_ready(self) -> None:
        market = pd.DataFrame(
            {
                "date": ["2021-04-14", "2021-04-15"],
                "ticker": ["035720", "035720"],
                "security_id": ["KRX_COMMON:035720", "KRX_COMMON:035720"],
                "open": [558000.0, 120500.0],
                "close": [558000.0, 120500.0],
                "listed_shares": [88761861.0, 443809305.0],
                "mechanical_reset": [False, True],
            }
        )
        calendar = ("2021-04-14", "2021-04-15")
        candidates = _phase5r_share_reset_candidates(
            market,
            _membership(list(calendar)),
            calendar,
        )

        self.assertEqual(len(candidates), 1)
        row = candidates[0]
        self.assertEqual(row["candidate_id"], "OBSERVED-SHARE-CHANGE:2021-04-15:035720")
        self.assertAlmostEqual(row["observed_share_ratio"], 5.0)
        self.assertTrue(row["member_both_sessions"])
        self.assertEqual(
            row["resolution_status"],
            "UNRESOLVED_MISSING_EFFECTIVE_DATE_RATIO_PIT_IDENTITY",
        )
        self.assertFalse(row["safe_for_position_accounting"])
        self.assertFalse(row["executable_corporate_action_created"])

    def test_candidate_selection_does_not_use_effective_close(self) -> None:
        market = pd.DataFrame(
            {
                "date": ["2021-04-14", "2021-04-15"],
                "ticker": ["035720", "035720"],
                "open": [558000.0, 120500.0],
                "close": [558000.0, 120500.0],
                "listed_shares": [88761861.0, 443809305.0],
            }
        )
        changed = market.copy()
        changed.loc[1, "close"] = 999999.0
        calendar = ("2021-04-14", "2021-04-15")
        first = _phase5r_share_reset_candidates(market, _membership(list(calendar)), calendar)
        second = _phase5r_share_reset_candidates(changed, _membership(list(calendar)), calendar)

        self.assertEqual([row["candidate_id"] for row in first], [row["candidate_id"] for row in second])
        self.assertFalse(first[0]["candidate_decision_uses_effective_day_close"])
        self.assertNotEqual(
            first[0]["share_adjusted_close_ratio_diagnostic"],
            second[0]["share_adjusted_close_ratio_diagnostic"],
        )

    def test_candidate_does_not_bridge_missing_security_session(self) -> None:
        market = pd.DataFrame(
            {
                "date": ["2021-04-14", "2021-04-15", "2021-04-16"],
                "ticker": ["A", "B", "A"],
                "open": [100.0, 50.0, 20.0],
                "close": [100.0, 50.0, 20.0],
                "listed_shares": [100.0, 100.0, 500.0],
            }
        )
        calendar = ("2021-04-14", "2021-04-15", "2021-04-16")
        membership = pd.DataFrame({"date": calendar, "ticker": ["A", "B", "A"]})
        self.assertEqual(
            _phase5r_share_reset_candidates(market, membership, calendar),
            (),
        )

    def test_raw_identity_audit_detects_00680k_collision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            membership = root / "20210104_membership.csv"
            market = root / "20210104_market.csv.gz"
            pd.DataFrame({"ticker": ["000680"]}).to_csv(membership, index=False)
            pd.DataFrame(
                {
                    "종목코드": ["000680", "00680K"],
                    "상장주식수": [100, 100],
                }
            ).to_csv(
                market,
                index=False,
                compression="gzip",
                encoding="cp949",
            )
            audit = _raw_ticker_identity_audit(
                {"membership": (membership,), "market": (market,)},
                evaluation_start=date(2021, 1, 4),
                member_tickers={"000680"},
            )

        self.assertFalse(audit["canonical_raw_ticker_contract_complete"])
        self.assertFalse(audit["stable_identity_contract_complete"])
        self.assertEqual(audit["member_ticker_normalization_collision_count"], 1)
        self.assertEqual(
            audit["member_ticker_normalization_collisions"][0],
            {"normalized_ticker": "000680", "raw_values": ["000680", "00680K"]},
        )

    def test_unresolved_identity_and_action_hard_reject_phase5r(self) -> None:
        gates, decision = _integrity_decision(
            {"phase4e_model_gate_pass": True},
            {"stable_identity_contract_complete": False},
            ({"safe_for_position_accounting": False},),
            {"canonical_ex2_return_evaluable": False},
        )
        self.assertFalse(gates["stable_identity_contract_complete"])
        self.assertFalse(gates["corporate_action_terms_complete"])
        self.assertFalse(gates["canonical_ex2_return_evaluable"])
        self.assertEqual(
            decision,
            "REJECT_PHASE5R_UNRESOLVED_CA_AND_IDENTITY_CONTRACT",
        )


if __name__ == "__main__":
    unittest.main()
