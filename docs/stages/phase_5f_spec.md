# Phase 5F 시계열 경로·시장 이상상태 모델 명세

## 1. 승인과 연구 질문

- Experiment ID: `EXP-20260823-006`
- 사용자 승인: 2026-08-23, 논문을 참고한 Phase 5E 후속 구조 재시도 승인
- 상태: 결과 확인 전 사전등록
- 2019~2021: 이미 소비된 adaptive diagnostic이며 Test/OOS가 아님
- Development Test: 미승인·미접근
- Final OOS: Phase 8까지 봉인

연구 질문은 단일 시점 Feature 수준 대신 종목별 최근 기술신호의 경로와 시장상태의 변화를 사용하고, 비용 차감 초과수익의 평균과 조건부 중앙값을 함께 예측하며, Train에서만 학습한 시장 이상상태에서 신규매수를 보류하면 Phase 5E의 불안정한 선형 예측과 과도한 오판을 줄일 수 있는가이다.

## 2. 논문에서 채택·배제한 방향

채택하는 것은 기술지표 병렬 입력, 시계열 경로 표현, 비지도 시장 이상탐지, 상태·행동·보상 분리라는 구조적 아이디어다. 외부 거시지표·뉴스·기업 텍스트, 현재 종목을 과거에 소급한 표본, 가격 수준 RMSE·R², 결과를 본 뒤 조정한 이상치 비율은 사용하지 않는다. 강화학습·LSTM·Transformer·Mamba도 이번에는 사용하지 않는다. 표본 독립성과 경제적 평가가 충분하지 않은 상태에서 복잡도만 늘리지 않기 위해서다.

## 3. 입력과 시계열 Feature

- 물리 입력: `data/processed/v24/phase5_train_validation_2021/`
- 역할: `phase5_train_validation`
- 물리 최대일: `2021-12-31`
- 종목 기본변수 8개: `reversal_5`, `excess_momentum_20`, `excess_momentum_63`, 20·60·200일 추세, `low_volatility_20`, `volume_confirmation_5_20`
- 각 종목변수 변환: 당일 횡단면 rank, 5세션 rank 변화, 20세션 평균·표준편차, 20세션 중 rank가 0.5보다 큰 비율
- 시장 기본변수 5개: KOSPI 100 200일 추세·63일 모멘텀·20일 저변동성, 200일선 상회 Breadth, 20일 양의 모멘텀 Breadth
- 각 시장변수 변환: 당일 값, 5세션 변화, 20세션 표준편차

종목 시계열은 동일 `security_id`와 `membership_spell_id` 안에서 거래소 세션이 연속할 때만 이어진다. 중간 세션 누락·편입 spell 변경 시 rolling 상태를 초기화한다. 모든 값은 `t`일 장 종료까지의 정보만 쓴다. 분봉은 사용하지 않는다.

## 4. Target·모델·이상상태

Target은 Phase 5E와 동일한 `t+1` 시가 진입부터 `t+11` 시가 청산까지의 비용 차감 KOSPI 100 초과 로그수익률이다. 횡단면 rank로 바꾸지 않는다.

- 평균 모델: `HistGradientBoostingRegressor(loss=squared_error)`
- 강건 모델: `HistGradientBoostingRegressor(loss=quantile, quantile=0.50)`
- 공통 고정값: learning rate 0.03, 120회, depth 2, 최소 leaf 500, L2 10, early stopping 없음
- 시장 이상상태: `IsolationForest`, 200 trees, max samples 256
- 이상 임계값: 각 fold Train 고유 날짜의 `score_samples` 하위 5% 값
- 결측 대체와 모든 적합: 각 fold Train에서만 수행
- purge/embargo: 각각 20거래일
- Random split·후보 탐색·결과 기반 threshold 변경: 금지

외부 사건 일자나 경제위기 라벨은 이상탐지 적합·임계값에 사용하지 않는다.

## 5. 점수·매매 규칙

- 일별 점수: 평균 모델의 예상 비용 차감 초과수익
- 신규매수: 평균 `>=0.003`, 조건부 중앙값 `>0`, 시장 비이상 상태를 모두 충족
- 후보 정렬: 평균 예상 초과수익 내림차순, 동률은 `security_id` 오름차순
- 일별 최대 후보·최대 보유: 10
- 종목당 목표비중: 10%
- 최소 보유: 0, 조건 미충족 시 현금
- 청산: 평균 `<=0`, 중앙값 `<=0`, 시장 이상상태, 의무 조건, 또는 최대 10세션
- 공매도·레버리지·피라미딩: 금지

## 6. 평가·증거 지위

기본비용 연결 순초과수익 `>0`, 2배 비용 연결 순초과수익 `>=0`, 진입주문 100건 이상, MDD가 지수보다 5%p 넘게 악화되지 않는지를 진단한다. 연도별 결과·현금·보유 수·이상상태 veto 빈도도 보고하되 hard gate로 두지 않는다. 기존 D20은 변경하지 않는다.

2019~2021이 이미 소비됐으므로 결과와 무관하게 거래 후보나 Development Test 후보로 승격하지 않는다. 같은 구간 결과를 보고 Feature·모델·임계값을 다시 바꾸지 않는다.

## 7. 감사·산출물

- 파티션·manifest·파일 hash·날짜를 reader 전에 검증
- Development Test loaded/calculated/evaluated/selected 모두 0
- Final OOS 접근 false, 로드 후 날짜 필터 없음
- fold별 Train/Validation·purge/embargo·전처리·모델·이상탐지 적합 경계 기록
- `model_metrics.csv`, `fold_audit.csv`, `portfolio_metrics.csv`, `signal_activity.csv`
- `temporal_feature_audit.json`, `anomaly_audit.json`, `diagnostic_decision.json`
- `target_contract.json`, `data_audit.json`, `run.json`, `manifest.json`

실제 실행 결과를 확인한 뒤에만 `docs/stages/phase_5f_report.md`를 작성한다.

## 8. 테스트와 완료 조건

- 설정·Experiment ID·Feature·모델·threshold 고정 검증
- Development Test·금지 경로 fail-closed
- `t`→`t+1`→`t+11`과 비용 target 회귀 검증
- 거래소 세션 5/20 lookback, 중간 누락·membership spell reset
- 미래 행 변경이 과거 시계열 Feature·주문을 바꾸지 않음
- Train-only 결측 대체·두 회귀·IsolationForest·5% threshold
- purge/embargo 20, PIT·tradable·rank eligibility·CA 경계
- no-trade·시장 이상 veto·0~10종목·원장·비용 stress
- 감사 필드·manifest hash·동일 입력 byte determinism
- 전체 회귀 테스트 통과

## Codex Handoff

- 구현: `src/kospi100_temporal_risk/`
- 설정: `configs/phase5f_temporal_risk.json`
- 테스트: `tests/test_phase5f_config.py`, `tests/test_phase5f_modeling.py`, `tests/test_phase5f_policy.py`
- hash 확인: `PYTHONPATH=src python -m kospi100_temporal_risk.cli freeze --config configs/phase5f_temporal_risk.json`
- 실행: `PYTHONPATH=src python -m kospi100_temporal_risk.cli run --config configs/phase5f_temporal_risk.json --output artifacts/phase5f/adaptive_diagnostic`
- 완료 뒤에도 Development Test·Final OOS를 자동 실행하지 않는다.
