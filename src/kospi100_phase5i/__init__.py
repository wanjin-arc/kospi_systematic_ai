"""Phase 5I 2004 확장 점수 지속성 진단."""

from .config import Phase5IConfig, load_config
from .runner import freeze_values, run_diagnostic

__all__ = ["Phase5IConfig", "load_config", "freeze_values", "run_diagnostic"]
