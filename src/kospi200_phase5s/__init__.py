"""KOSPI 200 v2 Phase 5S integrity-first soft-fusion research package."""

from .config import EXPERIMENT_ID, Phase5SConfig, guard_path, load_config
from .data import Phase5SInputs, build_score_panel, load_phase5s_inputs
from .labels import attach_reset_safe_labels

__all__ = [
    "EXPERIMENT_ID",
    "Phase5SConfig",
    "Phase5SInputs",
    "attach_reset_safe_labels",
    "build_score_panel",
    "guard_path",
    "load_config",
    "load_phase5s_inputs",
]
