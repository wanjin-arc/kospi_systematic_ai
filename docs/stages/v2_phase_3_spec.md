# v2 Phase 3 Technical Agent C 사전등록 명세

## 상태

`COMPLETED_REJECTED_CONSUMED_DEVELOPMENT`

Experiment ID는 `EXP-20260826-002`다. 이 단계는 Agent B Top 30 안에서 기술적
진입 후보를 만드는 consumed-development 진단이며 포트폴리오 백테스트가 아니다.

## 고정 입력과 경계

- Agent B: `EXP-20260826-001`의 `ridge_a10`
- 후보: `artifacts/v2_phase2_agent_b_release/daily_top30.csv.gz`
- 시장자료: 2016-01-04~2023-12-28 KRX 일봉 OHLCV
- 모델 표본: 2018-01-02~2023-12-28
- t일 종가까지 완성된 일봉만 Feature에 사용하고 주문 가능 시점은 t+1 이후다.
- v2 2022~2023은 이미 소비된 개발 자료이며 독립 Test/OOS로 부르지 않는다.

## Feature

OHLCV만으로 `return_1/5/20/60`, `volatility_5/20`, `downside_volatility_20`,
`close_to_ma20/60`, `drawdown_20/60`, `intraday_range`, `volume_ratio_20`, `gap_1`
14개를 계산한다. 분할·병합으로 확인한 기계적 가격 변화에는 시계열을 reset한다.

## Target과 후보

- target: t+1 시가부터 t+11 시가까지 10세션 수익률에서 왕복비용 proxy 40bp를 뺀 값
- 표본: 매 5번째 KRX 세션
- 후보 1: Train-only median imputer·standard scaler·Ridge(alpha=10) 회귀와 Logistic(C=1)
- 후보 2: 고정 shallow HistGradientBoosting 회귀와 분류
- score: 예상 비용 차감 수익률
- 진입 적격: 예상 비용 차감 수익률 > 0이고 양수확률 >= 0.55
- 일별 최대 10종목, 최소 0종목
- 분할: expanding annual walk-forward, purge 10 + embargo 10 KRX 세션
- 선택: 평균 일별 Spearman IC 최대, 동률이면 Brier score 최소, 그다음 단순 모델 우선

## 비목표와 금지사항

- Agent B 재튜닝, Top 30 규칙 변경
- 손절·익절·보유기간 정책 및 포트폴리오 백테스트
- 지수 초과성과·Sharpe·MDD를 이 단계 결과로 주장
- 분봉, Final OOS, v1 Development Test 파티션, 실주문·배포

## Codex Handoff

`src/kospi200_agent_c/`와 전용 테스트를 구현하고, source·config·Agent B 입력 hash를
실행 전에 registry에 동결한다. 실제 실행과 독립 재실행 후에만 보고서를 작성한다.
