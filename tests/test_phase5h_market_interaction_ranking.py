import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


TOOL = Path(__file__).resolve().parents[1] / "tools" / "run_phase5h_market_interaction_ranking.py"
SPEC = importlib.util.spec_from_file_location("phase5h_market_interaction_ranking", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Phase5HMarketInteractionRankingTests(unittest.TestCase):
    def test_config_freezes_full_interaction_set_and_candidate_order(self):
        payload = MODULE.load_config(Path("configs/phase5h_market_interaction_ranking.json"))
        config = MODULE._model_config(payload)
        self.assertEqual(len(config.stock_features), 21)
        self.assertEqual(len(config.regime_features), 4)
        self.assertEqual(len(config.interactions), 84)
        self.assertEqual(tuple(payload["models"]["candidate_order"]), MODULE.CANDIDATES)

    def test_development_test_and_feature_selection_mutations_fail_closed(self):
        source = json.loads(Path("configs/phase5h_market_interaction_ranking.json").read_text(encoding="utf-8"))
        for mutate in (
            lambda value: value.__setitem__("development_test_access", True),
            lambda value: value["feature_contract"].__setitem__("phase4c_result_based_selection", True),
        ):
            payload = json.loads(json.dumps(source))
            mutate(payload)
            with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
                json.dump(payload, handle)
                path = Path(handle.name)
            self.addCleanup(path.unlink, missing_ok=True)
            with self.assertRaises((PermissionError, ValueError)):
                MODULE.load_config(path)

