# v2 Phase 3B 독립 Technical Agent C 사전등록 명세

## 상태

`COMPLETED_AGENT_D_INPUT_CANDIDATE`

Experiment ID는 `EXP-20260826-003`이다. Phase 3의 직렬 구조와 달리 Agent B를
입력·gate로 사용하지 않고 전체 PIT KOSPI 200을 OHLCV만으로 점수화한다.

## 연구 질문

10세션 동안의 최대 불리 변동과 2:1 익절·손절 선후관계를 독립적으로 예측하면,
Agent D가 펀더멘털 점수와 결합할 수 있는 보완적 기술 점수를 만들 수 있는가?

## 입력과 Feature

- 2016-01-04~2023-12-28 KRX OHLCV와 PIT KOSPI 200 membership
- 모델·평가 구간 2018-01-02~2023-12-28
- Agent B·재무제표·DART Factor는 읽지 않는다.
- Phase 3과 동일한 causal OHLCV 14개 Feature
- 분할·병합으로 확인한 기계적 변화에는 lookback reset

## 두 분기와 target

- risk branch: t+1 시가 진입 후 10세션 최대 불리 변동률 예측
- bottom branch: +10% 익절이 -5% 손절보다 먼저 발생하면 1, 아니면 0
- 같은 세션에 둘 다 닿으면 일봉 선후관계를 모르므로 손절 우선
- 10세션 후 자동 종료 수익률에서 40bp를 뺀 값을 순위 평가 보조 target으로 사용
- t+1 시가가 t 종가 대비 절대 5%를 초과하면 향후 Agent D 실행에서 gap veto

## 모델

- `linear_event_dual`: Ridge risk + Logistic bottom
- `hist_event_dual`: shallow HistGradientBoosting risk + bottom
- composite score: 성공확률 - 0.5 × 날짜별 예상 MAE percentile
- 표본은 매 5번째 세션, expanding annual fold, purge 10 + embargo 10
- 선택: composite score의 일별 Spearman IC 최대, 동률이면 bottom AUC 최대, 선형 우선

현재 환경에는 PyTorch/TensorFlow/Keras가 없으므로 이 Experiment를 LSTM/CNN으로
표현하지 않는다. proxy 구조가 양의 보완 신호를 보일 때만 정확한 딥러닝 의존성·sequence
tensor·seed·hardware determinism을 별도 Experiment로 사전등록한다.

## 비목표

- Agent B와 결합, 포트폴리오·비중·실제 주문
- 5%/11% 투자 비중, score 0.05/0.075 threshold 튜닝
- 분봉, Final OOS, v1 Development Test 파티션

## Codex Handoff

독립 membership 입력을 테스트하고 Agent B 경로가 코드·설정에 없음을 검증한다.
실행 전 source·config·membership·market hash를 registry에 동결하고 독립 재실행한다.
