"""PIT canonical accounts를 분기 상태와 20개 일별 펀더멘털 Factor로 변환한다."""

from __future__ import annotations

from collections.abc import Mapping


REPORT_QUARTER = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}
FLOW_ACCOUNTS = ("revenue", "operating_income", "net_income", "operating_cash_flow", "capital_expenditure")
BALANCE_ACCOUNTS = ("assets", "liabilities", "equity", "current_assets", "current_liabilities", "cash_and_equivalents")


def fiscal_key(year: int, report_code: str) -> int:
    if report_code not in REPORT_QUARTER:
        raise ValueError(f"알 수 없는 report_code: {report_code}")
    return year * 4 + REPORT_QUARTER[report_code]


def trailing_values(
    statements: Mapping[tuple[int, int], Mapping[str, float]], year: int, quarter: int,
) -> dict[str, float]:
    """당시 공개된 누적 손익·현금흐름을 TTM으로 바꾼다."""
    current = statements.get((year, quarter), {})
    result = {name: current.get(name) for name in BALANCE_ACCOUNTS}
    if quarter == 4:
        for name in FLOW_ACCOUNTS:
            result[name] = current.get(name)
        return result
    previous_annual = statements.get((year - 1, 4), {})
    previous_same = statements.get((year - 1, quarter), {})
    for name in FLOW_ACCOUNTS:
        values = (previous_annual.get(name), current.get(name), previous_same.get(name))
        result[name] = None if any(value is None for value in values) else float(values[0]) + float(values[1]) - float(values[2])
    return result


def latest_fiscal_period(statements: Mapping[tuple[int, int], Mapping[str, float]]) -> tuple[int, int] | None:
    return max(statements) if statements else None
