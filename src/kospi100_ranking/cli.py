from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runner import confirm_development_test, run_selection


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 5 cross-sectional ranking research")
    subparsers = parser.add_subparsers(dest="command", required=True)
    select = subparsers.add_parser("select", help="Train/Validation Selection 실행")
    select.add_argument("--config", type=Path, required=True)
    select.add_argument("--output", type=Path, required=True)
    confirm = subparsers.add_parser(
        "confirm-development-test",
        help="별도 승인 전에는 항상 거부되는 Development Test 명령",
    )
    confirm.add_argument("--config", type=Path, required=True)
    confirm.add_argument("--selection", type=Path, required=True)
    confirm.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "select":
        result = run_selection(args.config, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
        return 0
    confirm_development_test(args.config, args.selection, args.output)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
