from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


class ContractError(ValueError):
    """미래 shadow 계약이 안전 경계를 위반했을 때 발생한다."""


_SECRET_KEYS = {
    "appkey",
    "appsecret",
    "app_key",
    "app_secret",
    "access_token",
    "account_number",
    "cano",
}


def _walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.add(str(key).lower())
            keys.update(_walk_keys(nested))
    elif isinstance(value, list):
        for nested in value:
            keys.update(_walk_keys(nested))
    return keys


def _contains_protected_path(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.replace("\\", "/").lower()
        return "sealed" in normalized and "oos" in normalized
    if isinstance(value, dict):
        return any(_contains_protected_path(nested) for nested in value.values())
    if isinstance(value, list):
        return any(_contains_protected_path(nested) for nested in value)
    return False


def validate_contract(config: dict[str, Any], *, release_ready: bool = False) -> None:
    if config.get("schema_version") != "v2-phase6-forward-shadow-v1":
        raise ContractError("지원하지 않는 Phase 6 계약 버전입니다.")
    if config.get("mode") != "shadow_only":
        raise ContractError("Phase 6 초기 실행은 shadow_only만 허용됩니다.")
    if config.get("protected_oos_accessed") is not False:
        raise ContractError("Protected OOS 접근 표시는 반드시 false여야 합니다.")

    start = date.fromisoformat(str(config.get("evaluation_start")))
    if start < date(2026, 8, 27):
        raise ContractError("미래 평가 시작일은 2026-08-27 이전일 수 없습니다.")

    if _contains_protected_path(config):
        raise ContractError("Protected OOS 경로를 입력 또는 실행 경로로 참조할 수 없습니다.")

    found_secrets = _walk_keys(config) & _SECRET_KEYS
    if found_secrets:
        raise ContractError(f"설정 파일에 비밀값 필드가 포함돼 있습니다: {sorted(found_secrets)}")

    kis = config.get("kis", {})
    if kis.get("environment") != "virtual":
        raise ContractError("KIS 실계좌 환경은 허용되지 않습니다.")
    if any(kis.get(key) is not False for key in ("enabled", "network_calls", "order_submission")):
        raise ContractError("현재 단계에서는 KIS 네트워크·주문 호출이 모두 꺼져 있어야 합니다.")

    if config.get("agent_b", {}).get("family") != "XGBRanker":
        raise ContractError("Agent B는 XGBRanker로 동결돼야 합니다.")
    if config.get("agent_b", {}).get("objective") != "rank:ndcg":
        raise ContractError("Agent B objective는 rank:ndcg여야 합니다.")
    if config.get("agent_b", {}).get("top_n") != 30:
        raise ContractError("Agent B 후보 수는 30이어야 합니다.")
    if config.get("agent_c", {}).get("family") != "PyTorch_LSTM_CNN":
        raise ContractError("Agent C는 실제 LSTM·CNN 구조여야 합니다.")
    if config.get("agent_d", {}).get("architecture") != "agent_b_top30_then_agent_c_execution":
        raise ContractError("Agent D는 B Top30 이후 C 실행 구조여야 합니다.")

    if release_ready:
        pending = json.dumps(config, ensure_ascii=False).find("TRAINING_PENDING") >= 0
        if pending:
            raise ContractError("학습 결과와 hash가 동결되기 전에는 shadow 주문을 만들 수 없습니다.")


def load_contract(path: str | Path, *, release_ready: bool = False) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_contract(config, release_ready=release_ready)
    return config
