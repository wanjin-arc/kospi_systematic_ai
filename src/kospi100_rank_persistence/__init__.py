"""Phase 5C causal score-persistence research package."""

from .config import Phase5CConfig, load_config
from .policy import apply_causal_persistence, generate_persistent_orders
from .runner import freeze_values, run_diagnostic

__all__ = [
    "Phase5CConfig",
    "apply_causal_persistence",
    "freeze_values",
    "generate_persistent_orders",
    "load_config",
    "run_diagnostic",
]
