from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runner import run_phase3


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the frozen Phase-3 KOSPI100 rule baseline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output", type=Path, default=Path("artifacts/phase3"))
    args = parser.parse_args()
    summary = run_phase3(args.config, args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
