"""Phase 4F 명령행 진입점."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config
from .materialize import materialize_phase4f_release
from .runner import preflight_values, run


def main() -> None:
    parser = argparse.ArgumentParser(description="v2 Phase 4F model-only pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("materialize", "preflight", "run"):
        command = sub.add_parser(name)
        command.add_argument("--config", required=True, type=Path)
        if name == "run":
            command.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "materialize":
        config = load_config(args.config)
        result = materialize_phase4f_release(config)
    elif args.command == "preflight":
        result, _ = preflight_values(args.config)
    else:
        result = run(args.config, args.output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
