# v2 Phase 3C 공식지수 초과수익 Agent C2 명세

## 상태

`COMPLETED_DIAGNOSTIC_ONLY`

Experiment ID는 `EXP-20260826-006`이다. Agent D에서 기존 Agent C 단독 포트폴리오가 공식지수 대체 proxy를 이기지 못한 원인을 반영한다.

## 연구 질문

2004년부터 축적한 PIT KOSPI 200 OHLCV와 공식 KRX 1028 지수의 causal 시장상태를 사용해 10세션 비용 차감 공식지수 초과수익을 직접 예측하면 기존 2:1 event score보다 안정적인 일별 기술 점수를 만들 수 있는가.

## 고정 계약

- Universe: 날짜별 실제 PIT KOSPI 200 전체
- 종목 입력: 기존 14개 causal OHLCV Feature
- 시장 입력: KOSPI 200 20세션 수익률, 60세션 추세, 20세션 변동성
- target: `t+1 시가~t+11 시가 종목수익 - 같은 기간 공식 KOSPI200 수익 - 40bp`
- 후보: 기존 `hist_event_dual_v1`, 선형 excess 회귀·분류, shallow HistGB excess 회귀·분류
- Train: 2006~2018부터 시작하는 expanding window
- Validation: 2019~2023 연도별, purge 10·embargo 10
- 선택: 평균 excess Rank IC, 동률이면 positive-excess AUC, 그다음 단순 모델
- Agent B·재무데이터 접근 금지, 포트폴리오 백테스트 금지

2019~2023은 이미 소비된 개발 진단이다. 같은 결과를 보고 모델 깊이·비용·Feature·기간을 변경하지 않는다. v1 Development Test와 Final OOS에는 접근하지 않는다.

## 완료 조건

- 2004~2010 및 2011~2023 시장 입력의 물리 경계와 hash 감사
- 공식 index_code 1028 및 4,945행 검증
- t+1~t+11 종목·지수 target 시점 테스트
- 지수 Feature의 미래 bar 미사용 테스트
- 기존 event 모델을 동일 후보군에서 비교
- 독립 재실행 byte determinism과 전체 테스트 통과

## Codex Handoff

Agent C2는 독립 점수 후보까지만 생성한다. B2와의 실제 결합·필터·포트폴리오는 다음 Agent D2의 별도 사전등록 대상이다.
