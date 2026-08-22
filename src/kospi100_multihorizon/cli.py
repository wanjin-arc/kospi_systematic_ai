from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config
from .runner import confirm_development_test, freeze_values, run_diagnostic


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 5G 다중 기간 합의 Train 내부 진단")
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze", help="실행 전 hash 확인")
    freeze.add_argument("--config", type=Path, required=True)
    run = commands.add_parser("run", help="2018년 이하 Train 내부 진단")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    denied = commands.add_parser("confirm-development-test", help="미승인 접근 거부")
    denied.add_argument("--config", type=Path, required=True)
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
