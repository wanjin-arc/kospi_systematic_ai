from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config
from .runner import confirm_development_test, freeze_values, run_diagnostic


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 5F 시계열 경로·시장 이상상태 adaptive diagnostic")
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze = subparsers.add_parser("freeze", help="실행 전 source/config/data/model-contract hash 확인")
    freeze.add_argument("--config", type=Path, required=True)
    run = subparsers.add_parser("run", help="2019~2021 adaptive diagnostic")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    confirm = subparsers.add_parser("confirm-development-test", help="별도 승인 전 항상 거부")
    confirm.add_argument("--config", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "freeze":
        result = freeze_values(load_config(args.config))
    elif args.command == "run":
        result = run_diagnostic(args.config, args.output)
    else:
        confirm_development_test(args.config)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
