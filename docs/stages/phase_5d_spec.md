# Phase 5D 시장상태·절대점수 선택형 Ranking 명세

## 1. 승인과 연구 성격

- Experiment ID: `EXP-20260823-004`
- 사용자 승인: 2026-08-23, 평균 현금 10% gate 제거 및 가변 보유 허용
- 평가 구간: 2019~2021 재사용 Validation 진단
- Development Test: 미승인·미접근
- Final OOS: 봉인 유지

2019~2021은 Phase 5에서 이미 확인한 구간이므로 Test 또는 OOS가 아니다. 이번 결과는 운용 구조를 이해하기 위한 재사용 진단이며, 성과가 좋아도 거래 후보로 승격하지 않는다.

## 2. 변경 이유

평균 현금 10% 이하를 강제하면 신호가 약하거나 시장이 불리할 때도 투자하도록 압박한다. 현금 보유가 허용된 long-only 시스템에서는 현금 비중과 보유 종목 수는 위험 선택의 결과여야 한다. 따라서 Phase 5D는 다음 원칙을 사용한다.

- 최소 보유 종목 수는 0개다.
- 최대 보유 종목 수만 10개로 제한한다.
- 종목 점수가 절대 기준을 넘지 못하면 매수하지 않는다.
- 시장상태가 neutral이면 최대 5개, risk-off이면 0개로 줄인다.
- 평균 현금은 성과·위험·기회비용 지표로 보고하되 hard gate로 쓰지 않는다.

## 3. 고정 입력과 모델

- Phase 4B의 21개 종목변수, 5개 시장상태, 6개 상호작용
- Phase 5B 진단 모델 `elastic_a005_l02`
- D09 10세션 초과수익률 순위 target
- 각 annual fold Train-only 적합
- purge 20, embargo 20
- `t` 종가까지 계산하고 `t+1` 시가 이후 주문

## 4. 종목 점수와 매매 규칙

1. ElasticNet의 raw predicted target rank를 종목별로 계산한다.
2. 같은 fold·membership spell·연속 거래세션 안에서 5세션 causal EMA를 적용한다.
3. 날짜별 횡단면 평균과 표준편차로 현재 점수 z-score를 계산한다.
4. 신규매수는 `z >= 1.0`인 종목만 허용한다.
5. 보유 중 `z < 0`이면 다음 거래일 시가에 청산한다.
6. risk-on에서 진입 후보는 순위 20위까지 제출하되 엔진 최대 보유는 10개다. 보유 순위가 20위 밖이면 청산한다.
7. neutral에서는 상위 5개까지만 진입·유지한다.
8. risk-off에서는 신규매수를 하지 않고 최근 신호 포지션을 다음 시가에 청산한다.
9. 20세션 보유 상한을 안전장치로 유지한다.

## 5. 시장상태

- `index_trend_200 > 0`이고 `breadth_above_sma200 >= 0.5`: risk-on, 최대 10종목
- 두 조건 중 하나만 참: neutral, 최대 5종목
- 두 조건 모두 거짓: risk-off, 최대 0종목

시장상태는 `t` 종가까지의 지수와 동시점 Universe breadth만 사용한다.

## 6. 데이터 경계

- 입력 역할: `phase5_train_validation`
- 물리 최대일: 2021-12-31
- 2019~2021 loaded/calculated/evaluated 행을 별도 감사한다.
- 2022~2023 loaded/calculated/evaluated/selected는 모두 0이어야 한다.
- 로드 후 날짜 필터링은 금지한다.
- Final OOS는 접근하지 않는다.

## 7. 산출물과 판정

- `portfolio_metrics.csv`
- `fold_rank_metrics.csv`
- `fold_audit.csv`
- `regime_exposure_audit.csv`
- `policy_audit.json`
- `diagnostic_decision.json`
- `score_contract.json`
- `data_audit.json`
- `run.json`
- `manifest.json`

성과, turnover, 비용, MDD, 현금, 평균 보유 수, 시장상태별 노출을 보고한다. 이번 실행에는 promotion gate가 없다. 무결성 실패만 실행 실패이며 성과 결과는 그대로 기록한다.

## 8. 테스트와 완료 조건

- 설정·기간·파티션·고정 모델 guard
- 2022년 이후 입력 reader 전 거부
- causal EMA 및 미래점수 불변
- z-score 진입·청산 경계
- risk-on 10, neutral 5, risk-off 0개 규칙
- 최소 보유 0개와 잔여현금 무벌점
- `t` 신호에서 `t+1` 주문
- Development Test 명령 fail-closed
- 독립 byte determinism과 전체 회귀 통과

## Codex Handoff

- 구현: `src/kospi100_selective_ranking/`
- 설정: `configs/phase5d_selective_ranking.json`
- 테스트: `tests/test_phase5d_config.py`, `tests/test_phase5d_policy.py`
- 실행: `PYTHONPATH=src python -m kospi100_selective_ranking.cli run --config configs/phase5d_selective_ranking.json --output artifacts/phase5d/reused_validation_diagnostic`
- 완료 후에도 Development Test와 Final OOS는 자동 실행하지 않는다.
