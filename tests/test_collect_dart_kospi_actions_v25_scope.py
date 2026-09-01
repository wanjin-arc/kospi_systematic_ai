import importlib.util
import tempfile
import unittest
from datetime import date
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools" / "collect_dart_kospi_actions_v25.py"
SPEC = importlib.util.spec_from_file_location("collect_dart_kospi_actions_v25", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class EventScopeTests(unittest.TestCase):
    def test_scope_reads_only_explicit_tickers_and_normalises_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.csv"
            path.write_text(
                "candidate_id,ticker,effective_date_candidate\n"
                "a,210,2021-04-15\n"
                "b,035720,2021-04-15\n"
                "c,invalid,2021-04-15\n",
                encoding="utf-8",
            )
            self.assertEqual(MODULE.load_event_scope(path), {"000210": [date(2021, 4, 15)], "035720": [date(2021, 4, 15)]})

    def test_filing_window_is_scoped_to_event_date(self):
        scope = {"035720": [date(2021, 4, 15)]}
        self.assertTrue(MODULE.filing_in_event_scope({"rcept_dt": "20210401"}, scope, 30))
        self.assertFalse(MODULE.filing_in_event_scope({"rcept_dt": "20200101"}, scope, 30))
        self.assertFalse(MODULE.filing_in_event_scope({"rcept_dt": "bad"}, scope, 730))

    def test_empty_scope_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.csv"
            path.write_text("ticker,effective_date_candidate\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE.load_event_scope(path)

    def test_phase5s_ledger_scope_keeps_only_both_member_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.csv"
            path.write_text(
                "ticker,effective_date_candidate,member_both_sessions\n"
                "035720,2021-04-15,True\n"
                "035720,2021-04-16,False\n",
                encoding="utf-8",
            )
            self.assertEqual(MODULE.load_event_scope(path), {"035720": [date(2021, 4, 15)]})


if __name__ == "__main__":
    unittest.main()
