# v2 Phase 2 Agent B 사전등록 명세

## 상태

`COMPLETED_CONSUMED_DEVELOPMENT_DIAGNOSTIC`

사용자가 2026-08-26 승인한 Fundamental Agent B의 동결 실행 계약이다. Experiment ID는
`EXP-20260826-001`이며 결과 확인 전 코드·설정·입력 hash를 registry에 고정한다.

## 입력

- `data/processed/v2_kospi200_fundamental_factor_panel/fundamental_factor_panel.csv.gz`
- 기간: 2016-03-24~2023-12-28. OpenDART 전체 재무제표 API는 2015 사업연도부터
  제공된다. 2015 보고서의 2014 비교금액은 2014 관측치로 소급하지 않는다.
- 20개 원 Factor와 유니버스 percentile·robust z-score
- `rank_eligible=true` 및 fail-closed identity가 확인된 동시점 KOSPI 200 종목만 사용
- 날짜별 적격 종목 30개 이상만 사용한다. 현재 1,912개 패널 날짜 중 1,907개가 충족한다.
- 섹터 자료가 없으므로 v1에서는 KOSPI 200 전체 단면 변환만 사용

## 권고 연구 질문

확정 재무제표만 사용하는 분기 상태가 향후 약 1분기 KOSPI 200 초과수익률 순위를
안정적으로 예측하며, 규칙 기반 균등 composite보다 얕은 비선형 ranker가 내부
walk-forward Rank IC와 NDCG를 개선하는가?

## 사전등록 권고안

- target: `t+1` 시가부터 `t+64` 시가까지 63거래일 KOSPI 200 초과수익률의 날짜별 순위
- 표본 시점: 각 달 마지막 거래일. 동일 분기 재무상태의 일별 중복 학습을 금지한다.
- 후보 1: 20개 percentile 방향을 사전 정의한 equal-weight composite
- 후보 2: Train-only 표준화 Ridge rank regression
- 후보 3: scikit-learn `HistGradientBoostingRegressor` 얕은 고정 구조 1개
- 분할: expanding walk-forward; 마지막 검증연도보다 앞선 연도만 Train에 사용
- purge/embargo: 각각 63 KRX 세션
- 평가지표: 날짜별 Spearman Rank IC, NDCG@30, 연도별 방향 안정성, coverage
- 일별 선택: 실제 PIT KOSPI 200 중 당일 시가총액 상위 200개를 먼저 고르고,
  Agent B 점수 상위 최대 30개를 출력한다. 유효 종목이 30개 미만이면 채우지 않는다.
- 희석도: KRX 상장주식수의 252세션 누적 변화다. 주식수와 가격이 역방향으로 상쇄되는
  20% 이상 변화는 분할·병합의 기계적 reset으로 제외한다. 원자료가 불충분하면 결측이다.
- 재무 업데이트: 실제 DART 접수일 다음 KRX 세션부터 최신 확정 상태로 교체한다.
- 이번 단계 비목표: 포트폴리오 백테스트, 매매 임계값, Agent C/D 결합, Development Test, Final OOS

## 데이터 지위

2016~2023은 모두 consumed development다. 어떤 fold도 독립 OOS라고 부르지 않으며,
모델 채택의 최종 증거는 동결 이후 forward shadow에서만 얻는다. 이 단계의 결과는 후보
축소와 구현 진단에만 사용한다.

## Codex Handoff

1. `EXP-20260826-001`을 `experiments/registry.csv`에 `preregistered`로 추가한다.
2. target·월말 snapshot·63세션 purge/embargo와 금지 경로 guard를 테스트한다.
3. equal-weight·Ridge·고정 shallow HistGradientBoosting 후보를 동일 fold에서 비교한다.
4. 모델·포트폴리오를 분리하고 Phase 2에서는 예측 품질만 평가한다.
5. 전체 회귀 통과 뒤 결과·hash·manifest를 별도 `artifacts/v2_phase2/`에 기록한다.
