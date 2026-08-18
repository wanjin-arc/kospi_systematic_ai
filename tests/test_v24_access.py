from __future__ import annotations

import gzip
import tempfile
import unittest
from datetime import date
from pathlib import Path

from kospi100_data.access import FinalOOSAccessError, V24PointInTimeDataset


class V24AccessTests(unittest.TestCase):
    def test_v24_access_denies_final_oos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = V24PointInTimeDataset(Path(tmp))
            with self.assertRaises(FinalOOSAccessError):
                dataset.universe_on(date(2024, 1, 2))

    def test_v24_access_returns_only_tradable_entry_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "membership_daily.csv.gz"
            with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
                handle.write("date,security_id,is_member,eligible_new_entry,tradable\n")
                handle.write("2023-12-28,A,True,True,True\n")
                handle.write("2023-12-28,B,True,True,False\n")
                handle.write("2023-12-28,C,False,True,True\n")
            dataset = V24PointInTimeDataset(Path(tmp))
            self.assertEqual(dataset.universe_on(date(2023, 12, 28)), {"A"})


if __name__ == "__main__":
    unittest.main()
