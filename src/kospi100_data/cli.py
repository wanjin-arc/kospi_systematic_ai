from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import Phase1Pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and build point-in-time KOSPI 100 data.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "build"):
        child = subparsers.add_parser(command)
        child.add_argument("--input-root", type=Path, required=True)
        child.add_argument("--output-root", type=Path, default=Path("data"))
        child.add_argument("--report", type=Path, required=True)
        child.add_argument("--expected-universe-size", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pipeline = Phase1Pipeline(
        args.input_root,
        args.output_root,
        args.report,
        expected_universe_size=args.expected_universe_size,
    )
    result = pipeline.validate() if args.command == "validate" else pipeline.build()
    print(f"status={result.status}")
    print(f"report={result.report_path}")
    print(f"blockers_or_errors={sum(i.severity in {'BLOCKER', 'ERROR'} for i in result.issues)}")
    return 0 if result.is_valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
