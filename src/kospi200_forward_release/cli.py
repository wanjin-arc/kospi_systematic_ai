from __future__ import annotations

import argparse
import json

from .contract import load_contract


def main() -> int:
    parser = argparse.ArgumentParser(description="v2 Phase 6 미래 shadow 계약 검사")
    parser.add_argument("command", choices=("validate",))
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    config = load_contract(args.config, release_ready=False)
    print(json.dumps({"experiment_id": config["experiment_id"], "status": config["status"], "valid": True}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
