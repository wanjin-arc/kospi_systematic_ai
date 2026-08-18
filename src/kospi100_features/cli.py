from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runner import run_phase4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 4 기술 변수 단변량 연구")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="동결된 Phase 4 연구 실행")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        result = run_phase4(args.config, args.output)
        print(json.dumps(result["run"], ensure_ascii=False, sort_keys=True))
        return 0
    raise AssertionError("도달할 수 없는 Phase 4 CLI 명령")


if __name__ == "__main__":
    raise SystemExit(main())
