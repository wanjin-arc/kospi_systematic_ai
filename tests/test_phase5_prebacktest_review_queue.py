import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools" / "build_phase5_prebacktest_review_queue.py"
SPEC = importlib.util.spec_from_file_location("phase5_prebacktest_review_queue", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ReviewQueueTests(unittest.TestCase):
    def test_only_both_member_events_are_in_scope(self):
        self.assertEqual(len(MODULE.phase5_events([{"member_both_sessions": "True"}, {"member_both_sessions": "False"}])), 1)

    def test_priority_never_approves_terms(self):
        self.assertEqual(MODULE.priority("주식분할결정", "DOCUMENT_ARCHIVED"), "DIRECT_TERMS_CANDIDATE_REVIEW")
        self.assertEqual(MODULE.priority("주식분할결정", "DOCUMENT_UNAVAILABLE"), "SOURCE_UNAVAILABLE")

    def test_queue_preserves_pit_identity_failure(self):
        events = [{"candidate_id": "E", "ticker": "000001", "effective_date_candidate": "2021-04-15", "observed_share_ratio": "5"}]
        filings = [{"ticker": "000001", "rcept_no": "R", "rcept_dt": "20210401", "report_nm": "주식분할결정", "document_zip": "a.zip", "document_status": "DOCUMENT_ARCHIVED"}]
        identity = [{"ticker": "000001", "first_date": "2020-01-01", "last_date": "2022-01-01", "identity_status": "CONFIRMED", "corp_code": "X"}]
        queue = MODULE.build_queue(events, filings, identity, 30)
        self.assertEqual(queue[0]["review_priority"], "DIRECT_TERMS_CANDIDATE_REVIEW")
        self.assertEqual(queue[0]["terms_approved"], "false")
        self.assertEqual(queue[0]["pit_identity_status"], "CONFIRMED")


if __name__ == "__main__":
    unittest.main()
