"""Phase 5S predict-only 명령행 진입점."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runner import preflight_values, run


def main() -> None:
    parser = argparse.ArgumentParser(description="v2 Phase 5S frozen-model portfolio")
    sub = parser.add_subparsers(dest="command", required=True)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("--config", required=True, type=Path)
    execute = sub.add_parser("run")
    execute.add_argument("--config", required=True, type=Path)
    execute.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "preflight":
        result, _, _ = preflight_values(args.config)
    else:
        result = run(args.config, args.output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
