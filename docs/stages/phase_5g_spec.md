# Phase 5G 다중 기간 합의 모델 명세

## 연구 질문과 증거 경계

- Experiment ID: `EXP-20260823-007`
- 목적: 한 시점의 단일 10거래일 예측에 의존하지 않고 5·10·20거래일 비용 차감 KOSPI 100 초과수익의 방향이 함께 양수인 종목을 찾는다.
- 입력은 `phase4b_train_internal` 역할의 2018년 이하 물리 파티션뿐이다.
- 2015~2018 anchored annual fold는 Train 내부 진단이다. 이미 소비된 2019~2021, Development Test, Final OOS는 읽거나 평가하지 않는다.
- 이 실행만으로 거래 후보나 Development Test 후보로 승격하지 않는다. 양호한 결과도 새 독립 데이터가 필요하다.

## 입력·변수·target

- Phase 4B의 종목 기술변수 21개, 시장상태 변수 5개, 상호작용 6개를 누락 없이 사용한다.
- 종목 변수는 매일 PIT Universe 안에서 평균 percentile rank로 변환한다.
- `t`일 종가 뒤 신호, `t+1` 시가 진입, `t+6`·`t+11`·`t+21` 시가 청산으로 각각 5·10·20거래일 초과 로그수익률을 계산한다.
- 각 target은 왕복 commission·slippage와 실제 청산일 세금을 차감한다.
- Corporate Action reset을 가로지르거나 진입·청산일에 거래 불가능한 표본은 제외한다.

## 고정 모델·정책

- 단일 고정 Extra Trees 다중출력 회귀: 300 trees, depth 6, leaf 500, max_features 0.5, seed 20260823, `n_jobs=1`.
- 각 fold의 전처리와 모델은 Train에서만 적합한다. purge와 embargo는 각각 20거래일이다.
- 세 예측 중 2개 이상이 양수이고 중앙값이 0.2% 이상인 종목만 진입 가능하다.
- 중앙값 내림차순·종목 ID 오름차순으로 매일 순위를 정해 최대 10종목, 종목당 목표 10%로 다음 거래일 시가에 주문한다.
- 최소 보유 종목은 0개이며 미배분 자금은 현금으로 둔다. pyramiding은 금지하고 최대 보유는 20거래일이다.

## 평가·완료 조건

- 2015~2018 연결 기본비용 순초과수익률 > 0, 2배 비용 순초과수익률 >= 0, 연도별 4/4 비음수, 진입 주문 100건 이상, MDD가 지수보다 5%p 초과 악화되지 않아야 내부 gate를 모두 통과한다.
- gate 통과 여부와 무관하게 승격은 금지한다. 같은 내부 구간을 보고 설정을 바꾸려면 새 Experiment ID가 필요하다.
- 전체 테스트, Phase 5G 테스트, 독립 재실행 byte determinism을 확인한다.
- 산출물은 `artifacts/phase5g/internal_diagnostic/`에 기록하고 hash manifest와 데이터 접근 감사를 포함한다.

## Codex Handoff

- 구현: `src/kospi100_multihorizon/`, Phase 5G 설정·테스트·보고서·registry.
- 동결: 실제 데이터 실행 전에 source/config/data/model-contract hash를 registry에 기록한다.
- 명령: `python -m kospi100_multihorizon.cli freeze ...`, 이어서 명세의 `run_command`.
- 금지: 2019년 이후 입력, Development Test, Final OOS, 결과 기반 재조정, 과거 Phase 산출물 변경.
