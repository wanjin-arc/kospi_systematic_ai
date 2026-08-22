# Phase 5 Technical Cross-sectional Ranking Model 명세

## 1. 문서 상태

- 상태: 사용자 승인 전 연구 명세 초안
- Phase: Phase 5
- 기준 Phase 4 커밋: `94c8f5c360557587d5de44b1f77165824e2162c5`
- Phase 5 결과 확인 전에 본 명세와 Experiment registry를 동결한다.
- Phase 4 결과와 산출물은 수정하지 않는다.

## 2. 목적

Phase 4에서 입력 후보로 채택된 `reversal_5`만 사용하여 KOSPI 100 종목의 향후 상대수익률을 횡단면으로 순위화하는 Technical Ranking Model을 검증한다.

Phase 5의 목적은 예측력이 아니라 다음 세 조건을 함께 확인하는 것이다.

1. 시간 순서 Validation에서 순위 예측력이 안정적인가.
2. 동일한 체결·비용·포트폴리오 조건에서 단순 Feature 순위와 Phase 3 기준선을 개선하는가.
3. 사전 정의된 채택 gate를 Development Test에서 통과하는가.

Phase 5 통과 모델도 최종 거래 모델이나 Final OOS 통과 모델로 간주하지 않는다.

## 3. 연구 질문과 가설

### 연구 질문 1

`reversal_5` 횡단면 순위는 향후 10거래일 KOSPI 100 초과수익률 순위와 일관된 양의 관계를 갖는가.

### 연구 질문 2

Train에서 적합한 선형 또는 얕은 의사결정나무가 단순 `reversal_5` 순위보다 Validation 성과를 개선하는가.

### 연구 질문 3

선택 모델이 기본 비용과 2배 비용 조건에서 기존 Phase 3 기준선보다 우수하며 사전 정의된 Phase 5 채택 gate를 충족하는가.

## 4. 입력 Feature

Phase 5에서 허용하는 Feature는 다음 하나뿐이다.

```text
reversal_5(i,t) = -(Close(i,t) / Close(i,t-5) - 1)
```

모델 입력은 해당 거래일의 실제 KOSPI 100 구성종목 집합 `U_t` 안에서 계산한 횡단면 percentile rank로 고정한다.

- 높은 `reversal_5` 값의 순위: 1에 가까움
- 동률 처리: average rank
- 계산 시점: `t`일 종가 확정 이후
- 주문 가능 시점: `t+1` 시가 이후
- 결측 Feature 행: 모델 입력에서 제외하고 사유와 coverage를 기록

Phase 4에서 보류·폐기된 다른 Feature와 레짐 변수는 사용할 수 없다.

## 5. Ranking Target

Primary target은 다음 10거래일 KOSPI 100 초과 open-to-open 수익률이다.

```text
r(i,t) =
log(Open(i,t+11) / Open(i,t+1))
-
log(IndexOpen(t+11) / IndexOpen(t+1))
```

같은 날짜의 적격 Universe `U_t` 안에서 `r(i,t)`를 percentile rank로 변환한다.

- 높은 초과수익률: target rank 1
- 동률 처리: average rank
- target은 학습과 평가에만 사용
- `t+1` 이후 정보는 Feature, Universe 또는 주문 결정에 사용할 수 없음
- label이 분할 경계를 넘거나 완성되지 않은 행은 해당 fold에서 제외

5거래일, 20거래일 및 변동성 조정 target은 Phase 5 후보에 포함하지 않는다.

## 6. 데이터 계층과 물리 입력

직접 통합 Development 파일을 읽고 날짜 필터링하는 방식은 금지한다.

### Train/Validation 입력

```text
data/processed/v24/phase5_train_validation_2021/
```

- 역할: `phase5_train_validation`
- 평가 대상 최대일: `2021-12-31`
- Selection 명령에서 허용되는 유일한 입력 역할

### Development Test 입력

```text
data/processed/v24/phase5_development_test_2023/
```

- 역할: `phase5_development_test`
- 평가 기간: 2022–2023
- 동결된 Selection manifest와 선택 모델 hash가 있어야만 접근 가능
- Selection 실행에서는 로드 불가
- 필요한 과거 계산 문맥이 포함되면 manifest에서 context와 evaluation 기간을 분리 기록

각 파티션에는 최소 다음 데이터와 manifest가 필요하다.

- Feature/가격 panel
- 전 기간 OHLCV
- KOSPI 100 지수 OHLCV
- Corporate Action 정합성 자료
- 지수 제외·거래불가 체결 처리 자료
- 파일별 bytes, SHA-256, 날짜 열, 최소일, 최대일, 행 수를 포함한 manifest

Final OOS 경로 `data/sealed/final_oos_v24/`는 Phase 8의 동결된 단일 릴리스 평가 전까지 열기, 스캔, glob, 집계, 테스트 입력 사용을 모두 금지한다.

## 7. 데이터 분할

### Train

- 2011-01-01부터 2018-12-31까지

### Validation

- 2019-01-01부터 2021-12-31까지

### Anchored annual walk-forward

1. 2011–2018 Train → 2019 Validation
2. 2011–2019 Train → 2020 Validation
3. 2011–2020 Train → 2021 Validation

Validation 후보를 선택한 뒤 2011–2021 전체로 한 번만 재적합한다.

### Development Test

- 2022-01-01부터 2023-12-31까지
- 동결 모델을 재적합하지 않고 한 번만 평가
- 별도 사용자 승인 전 접근 금지
- 결과 확인 후 모델·Feature·gate 변경 금지

### Final OOS

- 2024–2025
- Phase 5에서는 사용하지 않음

## 8. Purge와 Embargo

- Purge: 20거래일
- Embargo: 20거래일
- fold 경계에서 label 기간이 다음 구간과 겹치는 표본을 제거
- 종목별 label과 지수 label 모두 동일한 경계를 적용
- Random split과 섞기 방식은 금지

## 9. 전처리와 누수 방지

Phase 5 버전 1에서는 다음 학습형 전처리를 사용하지 않는다.

- scaler
- winsorization
- imputer
- PCA
- 별도 Feature selection
- 학습형 score threshold

현재일 Universe 안의 percentile rank만 허용하며 이는 Train 적합 변환이 아니다.

구현 과정에서 학습형 변환이 필요해지는 경우 실행을 중단하고 명세와 설정을 다시 승인받아야 한다. 승인된 경우에도 각 fold의 Train 안에서만 적합하고 Validation/Test에는 transform만 적용한다.

Universe, Feature, Corporate Action 및 거래 가능 여부는 모두 해당 시점에 알 수 있었던 정보만 사용한다.

## 10. 모델 후보

### B0: Raw Rank Baseline

- 모델 적합 없음
- `reversal_5` 횡단면 percentile rank를 그대로 점수로 사용

### M1: Ordinary Linear Regression

- 입력: `reversal_5` percentile rank 하나
- target: 10거래일 초과수익률 percentile rank
- 절편 포함
- 정규화 없음
- seed 비의존
- 파이프라인 및 방향성 검증용 단순 모델

### M2: Shallow Decision Tree Regression

고정 파라미터:

- criterion: `squared_error`
- splitter: `best`
- max_depth: `{1, 2, 3}`
- min_samples_leaf: `{0.02, 0.05}`
- min_samples_split: `2`
- max_features: `None`
- max_leaf_nodes: `None`
- min_impurity_decrease: `0.0`
- ccp_alpha: `0.0`
- random_state: `20260822`

총 후보는 Raw Rank 1개, 선형회귀 1개, 의사결정나무 6개로 제한한다.

Boosting, Random Forest, 신경망, ensemble, ranking 전용 라이브러리 및 추가 Feature 탐색은 비목표다.

모델 라이브러리와 정확한 버전은 첫 실행 전에 dependency lock 및 manifest에 고정한다.

## 11. 후보 선택 방법

먼저 데이터 무결성, 날짜 경계, coverage 및 재현성 gate를 통과해야 한다.

Validation 진단 지표:

- 일별 Spearman Rank IC
- 연도별 Rank IC와 양의 연도 비율
- NDCG@10
- 상위·하위 decile target spread
- Feature와 target coverage
- turnover
- 비용 차감 순초과수익률
- 비용 차감 Sharpe
- 최대낙폭
- 현금 비중과 미체결 건수

후보 선택 우선순위:

1. 2019–2021 연결 Validation의 기본 비용 차감 Sharpe
2. 순초과수익률
3. 낮은 최대낙폭
4. 낮은 turnover
5. 낮은 모델 복잡도: Raw Rank → Linear → Tree
6. 파라미터 사전 정의 순서

Validation 결과 확인 후 우선순위를 변경할 수 없다.

## 12. 비용과 체결 가정

Phase 3 기준선과 같은 조건을 적용한다.

- 매수·매도 수수료: 편도 2bp
- 매도세: 거래일별 실제 세율
- 불리한 slippage: 편도 10bp
- 비용 stress: 수수료와 slippage 2배 및 3배
- 매도세는 stress에서도 제거하지 않음
- 일봉 신호: `t`일 장 종료 이후 계산
- 주문: `t+1` 시가 이후
- `t`일 종가 대비 `t+1` 시가가 5%를 초과해 상승한 매수 후보는 제외
- 미래 체결가로 주문 수량 또는 후보를 결정하지 않음

## 13. 포트폴리오와 리밸런싱

Phase 3 기준선과 동일한 비교를 위해 다음을 권고 고정값으로 사용한다.

- Long-only 현금 주식
- 최대 보유 종목: 10
- 종목당 목표 비중: 10%
- 보유기간: 20거래일
- pyramiding 금지
- 레버리지·공매도 금지
- 정수 주식 수량
- 잔여 현금 유지
- 매 거래일 점수 생성
- 빈 슬롯만 상위 점수 종목으로 채움
- 순위 하락만을 이유로 기존 포지션을 조기 청산하지 않음
- Corporate Action, 지수 제외, 거래불가에 따른 필수 청산 규칙은 기존 엔진을 적용

Ranking target은 10거래일이고 포트폴리오 보유기간은 Phase 3 비교를 위해 20거래일로 유지한다. 이를 10거래일로 변경하려면 실행 전에 별도 결정과 기준선 재정의가 필요하다.

## 14. Baseline

다음 세 기준과 비교한다.

1. KOSPI 100 가격지수
2. 동결된 Phase 3 기준선
3. Raw `reversal_5` 횡단면 순위 포트폴리오

날짜, Universe, 체결, 비용, 포트폴리오 제약을 동일하게 맞춘다.

## 15. Phase 5 채택 gate

다음 조건을 모두 충족해야 모델 후보로 채택한다.

1. 모든 bias, 데이터 경계, 재현성 테스트 통과
2. 연도별 Validation fold의 80% 이상에서 순초과수익률이 음수가 아님  
   - 현재 3개 fold이므로 3개 모두 충족해야 함
3. 연결 Validation 순 Sharpe가 동결 기준선보다 최소 0.10 높음
4. Development Test 순초과수익률이 양수이며 기준선을 초과
5. Development Test 최대낙폭이 기준선보다 다음 한도를 초과하여 악화되지 않음  
   - 5%p와 기준선 최대낙폭 절댓값의 20% 중 큰 값
6. 2배 비용에서도 위 조건을 충족  
   - Sharpe 개선 조건은 2배 비용에서 0 이상 허용
7. 3배 비용 결과는 별도 스트레스 진단으로 기록

gate 실패 시 결과를 폐기하지 않고 `rejected` 또는 `baseline_retained`로 기록한다.

## 16. 출력 산출물

### 설정 및 문서

- `configs/phase5_ranking.json`
- `docs/stages/phase_5_report.md`
- `experiments/registry.csv`

### Selection 산출물

- `artifacts/phase5/selection/data_audit.json`
- `fold_metrics.csv`
- `rank_metrics.csv`
- `portfolio_metrics.csv`
- `candidate_selection.json`
- `selected_model.json`
- `run.json`
- `manifest.json`

### Development Test 산출물

- `artifacts/phase5/development_test/data_audit.json`
- `rank_metrics.csv`
- `portfolio_metrics.csv`
- `gate_decision.json`
- `run.json`
- `manifest.json`

선택 모델은 불투명한 pickle만 남기지 않고 계수, 절편, tree 구조와 라이브러리 버전을 이식 가능한 형태로 기록한다.

## 17. 감사 로그와 manifest

최소 기록 항목:

- Experiment ID
- Git commit 및 source hash
- config hash
- 데이터 파티션 역할과 data hash
- 입력 파일별 bytes와 SHA-256
- 입력 파일의 최소·최대 날짜와 행 수
- 실제 최대 로드 날짜
- Train/Validation/Development Test별 loaded, calculated, evaluated, selected 행 수
- Final OOS 접근 여부
- 모델 후보와 하이퍼파라미터
- 선택 모델 hash
- fold 정의
- seed
- 패키지와 Python 버전
- 비용 설정
- 재현 명령
- 산출물별 SHA-256

Selection manifest에서는 Development Test 관련 행 수가 모두 0이어야 한다.

## 18. 테스트 계획

필수 테스트:

- 설정 스키마와 동결 hash
- 허용 Feature가 `reversal_5` 하나인지 검증
- target 수식과 날짜 정렬
- Point-in-Time Universe
- `t` 계산과 `t+1` 체결
- purge/embargo 경계
- Train 내부 적합
- Selection에서 Development Test reader 호출 전 거부
- Final OOS 경로 참조 거부
- 물리 파티션 역할·날짜·hash 검증
- 결측 Feature와 label 처리
- 후보 수와 하이퍼파라미터 불변
- 모델 결정성
- fold별 적합 범위
- 비용과 세금 계산
- Phase 3 기준선과의 체결 조건 일치
- candidate tie-break 결정성
- Development Test 단일 공개
- 산출물 byte determinism
- 전체 회귀 테스트

## 19. 완료 조건

Phase 5는 다음이 모두 충족될 때 완료한다.

1. 명세와 Experiment가 결과 확인 전에 등록됨
2. 물리 파티션과 manifest 검증 통과
3. Selection과 독립 재실행이 byte-identical
4. Validation 후보 선택이 사전 정의 규칙과 일치
5. Development Test는 동결 모델로 한 번만 실행
6. 전체 테스트 통과
7. 감사 로그와 산출물 hash 기록
8. 채택 또는 폐기 결정이 gate에 따라 기록됨

성능 gate 실패는 연구 실행 실패가 아니다. 해당 경우 Phase 5는 `baseline_retained` 또는 `rejected` 결론으로 완료할 수 있다.

## 20. 실패·중단 조건

다음 중 하나라도 발생하면 fail-closed로 중단한다.

- 입력 역할, 날짜, 크기 또는 hash 불일치
- Selection 과정에서 Development Test 접근
- Final OOS 경로 참조
- 등록되지 않은 Feature·target·모델 사용
- `t+1` 이후 정보의 Feature 또는 Universe 유입
- purge/embargo 적용 실패
- 동결 Selection manifest 없이 Development Test 접근
- Development Test 반복 공개
- 결과 확인 후 설정·gate 변경
- 필수 청산 또는 Corporate Action 처리 불일치
- 결정성·재현성 실패
- Phase 5 또는 전체 회귀 테스트 실패

## 21. 비목표 및 금지사항

- Phase 4 결과 수정
- 보류·폐기 Feature 재도입
- 신규 Feature 탐색
- 레짐 변수
- Entry Timing
- 분봉 모델
- Random split
- 포트폴리오·리스크 최적화
- 다른 target horizon 탐색
- Boosting, ensemble, deep learning
- Development Test 반복 평가
- Final OOS 접근
- 실거래 및 주문
- Phase 6 이후 작업

## 22. Codex Handoff

승인 후 구현 대상:

- `configs/phase5_ranking.json`
- `src/kospi100_data/phase5_partition.py`
- `src/kospi100_ranking/__init__.py`
- `src/kospi100_ranking/config.py`
- `src/kospi100_ranking/data.py`
- `src/kospi100_ranking/targets.py`
- `src/kospi100_ranking/models.py`
- `src/kospi100_ranking/walk_forward.py`
- `src/kospi100_ranking/portfolio.py`
- `src/kospi100_ranking/runner.py`
- `src/kospi100_ranking/cli.py`
- `tests/test_phase5_config.py`
- `tests/test_phase5_data.py`
- `tests/test_phase5_targets.py`
- `tests/test_phase5_models.py`
- `tests/test_phase5_walk_forward.py`
- `tests/test_phase5_runner.py`

권고 실행 명령:

```text
PYTHONPATH=src python -m kospi100_ranking.cli select \
  --config configs/phase5_ranking.json \
  --output artifacts/phase5/selection
```

Development Test는 Selection 완료·동결 및 별도 사용자 승인 후에만 실행한다.

```text
PYTHONPATH=src python -m kospi100_ranking.cli confirm-development-test \
  --config configs/phase5_ranking.json \
  --selection-manifest artifacts/phase5/selection/manifest.json \
  --output artifacts/phase5/development_test
```

회귀 테스트:

```text
PYTHONPATH=src python -m unittest discover -s tests -v
```

첫 실행 전에 config, source, dependency, 데이터 파티션 및 Experiment registry hash를 모두 고정한다.