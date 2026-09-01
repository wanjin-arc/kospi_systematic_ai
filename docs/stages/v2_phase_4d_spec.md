# v2 Phase 4D Agent D4 사전등록 명세

## 목적

Agent D3의 원점수 0.05·0.075 규칙은 점수 분포와 맞지 않아 거의 모든 날 상시 진입했고 turnover가 292배까지 증가했다. D4는 C4가 예측한 비용 차감 초과수익의 경제적 0 경계와 횡단면 순위만 사용해 저회전 포트폴리오로 변환한다.

## 동결 후보와 운용

- Experiment ID: `EXP-20260826-011`
- 후보: `C4_SPARSE`, `C4_B2_RISK_CALIBRATION_SPARSE`
- B2는 종목을 제거하지 않고 순위 위험보정에만 사용한다.
- 예상 비용 차감 초과수익이 0보다 큰 종목 중 일별 상위 5개
- 5거래일마다만 신규 진입 판단, 종목당 10%, 최대 10종목
- t일 종가 신호, t+1 시가 체결, ±5% gap veto
- label과 일치하도록 손절·익절 barrier 없이 10거래일 기간 청산
- 공식 KRX KOSPI200 1028 지수와 비교하고 TWR, alpha, MDD, Sharpe, turnover, 승률, Profit Factor, 거래당 기대값을 기록한다.

## 채택 gate

연결 순초과수익 양수, 5개 연도 중 최소 3개 초과수익 양수, Sharpe 양수, MDD -30% 초과, 원장 대사 통과를 모두 요구한다. 2019~2023은 이미 소비된 개발기간이므로 통과해도 forward 검증 전 거래 승인으로 보지 않는다.

## Codex Handoff

`src/kospi200_agent_d4/`, 동결 설정, 전용 테스트를 구현하고 C4 산출물 hash 동결 뒤 실행한다. 독립 재실행과 전체 테스트 후 `docs/stages/v2_phase_4d_report.md`에 결과와 한계를 기록한다.
