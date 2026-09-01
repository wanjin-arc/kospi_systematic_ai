from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_analysis_config, load_selection_config
from .runner import confirm_development_test, freeze_values, run_analysis, run_selection


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 4B/5B 다변수 일별 횡단면 ranking 연구")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("freeze-analysis", "Phase 4B 실행 전 source/config/data hash 확인"),
        ("freeze-selection", "Phase 5B 실행 전 source/config/data/model hash 확인"),
        ("analyze", "2011~2018 Train 내부 Feature 분석"),
        ("select", "2015~2018 내부 Validation 모델·포트폴리오 선택"),
    ):
        child = subparsers.add_parser(command, help=help_text)
        child.add_argument("--config", type=Path, required=True)
        if command in {"analyze", "select"}:
            child.add_argument("--output", type=Path, required=True)
    confirm = subparsers.add_parser("confirm-development-test", help="별도 승인 전 항상 거부")
    confirm.add_argument("--config", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "freeze-analysis":
        result = freeze_values(load_analysis_config(args.config))
    elif args.command == "freeze-selection":
        result = freeze_values(load_selection_config(args.config))
    elif args.command == "analyze":
        result = run_analysis(args.config, args.output)
    elif args.command == "select":
        result = run_selection(args.config, args.output)
    else:
        confirm_development_test(args.config)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
