from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from kospi100_multifactor.config import load_selection_config
from kospi100_multifactor.modeling import evaluate_candidates, refit_candidate


class Phase4BModelingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_selection_config(Path("configs/phase5b_multifactor_ranking.json"))
        cls.index = pd.DataFrame({"date": pd.bdate_range("2011-01-03", "2018-12-31")})

    def _frame(self) -> pd.DataFrame:
        rows = []
        for year in range(2011, 2019):
            sessions = self.index.loc[self.index["date"].dt.year.eq(year), "date"]
            for offset in (45, 75, 105, 135, 165, 195):
                dt = sessions.iloc[offset]
                regime_values = {name: (year - 2014) / 4 for name in self.config.regime_features}
                for number in range(30):
                    rank = (number + 1) / 30
                    row = {
                        "date": dt,
                        "security_id": f"S{number:03d}",
                        "membership_spell_id": f"S{number:03d}:01",
                        "close": 100 + number,
                        "forward_excess_log_return_10": rank / 100,
                        "target_rank": rank,
                        **regime_values,
                    }
                    for index, feature in enumerate(self.config.stock_features):
                        row[f"rank__{feature}"] = rank if index % 2 == 0 else 1.0 - rank
                    rows.append(row)
        return pd.DataFrame(rows)

    def test_all_candidates_use_train_only_and_daily_rank(self) -> None:
        frame = self._frame()
        first = evaluate_candidates(frame, self.index, self.config)
        second = evaluate_candidates(frame, self.index, self.config)
        self.assertEqual(first.predictions.to_csv(index=False), second.predictions.to_csv(index=False))
        self.assertEqual(set(first.predictions["candidate"]), set(self.config.candidate_order))
        self.assertEqual(len(first.rank_metrics), len(self.config.candidate_order) * 4)
        self.assertEqual(len(first.feature_metrics), len(self.config.stock_features) * 4)
        self.assertTrue((first.fold_audit["model_fit_used_validation"] == False).all())  # noqa: E712
        self.assertTrue((first.fold_audit["preprocessing_fit_used_validation"] == False).all())  # noqa: E712
        grouped = first.predictions.groupby(["candidate", "date"])["score"]
        self.assertTrue((grouped.min() > 0).all())
        self.assertTrue((grouped.max() <= 1).all())

    def test_refit_model_pickle_is_byte_deterministic(self) -> None:
        frame = self._frame()
        first, first_binary = refit_candidate("ridge_a100", frame, self.index, self.config)
        second, second_binary = refit_candidate("ridge_a100", frame, self.index, self.config)
        self.assertEqual(first, second)
        self.assertEqual(first_binary, second_binary)
        self.assertLessEqual(first["fit_max_date"], "2018-12-31")
        self.assertEqual(first["development_test_rows_used"], 0)


if __name__ == "__main__":
    unittest.main()
