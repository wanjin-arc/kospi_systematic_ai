from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config
from .runner import freeze_values, run_diagnostic


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 5I 2004 확장 지속성 진단")
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--config", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "freeze":
        result = freeze_values(load_config(args.config))
    else:
        result = run_diagnostic(args.config, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
