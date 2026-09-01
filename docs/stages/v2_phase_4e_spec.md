# v2 Phase 4E — 무결성 복구 AI 점수모델 선택·동결 명세

## 1. 상태와 선행 관계

- Experiment ID: `EXP-20260901-001`
- 단계 역할: **모델 전용(model-only) 학습·선택·동결**
- 상태: 실행 완료, primary/reproduction 필수 산출물 `11/11` byte-identical 재현 후 동결
- 후속 단계: `v2 Phase 5R`, `EXP-20260901-002`
- 증거 수준: 이미 소비된 개발자료로 만드는 동결 후보이며 독립 OOS 또는 최종 Phase 5 통과 증거가 아니다.

기존 `EXP-20260831-001`은 모델 학습과 포트폴리오 평가를 한 단계에 묶었으나, 사용자가
AI 모델을 먼저 만들고 그 뒤 Phase 5R을 수행하도록 순서를 정정했다. 해당 Experiment는
실행·결과 생성 전에 superseded된 기록으로 보존하고 삭제하거나 재사용하지 않는다.

Phase 4E는 actual mechanical-reset·membership·identity 경계의 공통 라벨을 다시 만들고
Agent B·C·D의 시간순 OOF 점수를
비교한 뒤 한 개 primary score pipeline을 실제 직렬화 모델과 hash로 동결한다. 포트폴리오,
주문, 체결, 비용 차감 백테스트, 경제 gate 계산은 이 단계의 명시적 비목표다.

## 2. 연구 질문

1. 오류가 수정된 동일 20세션 품질 target에서 PIT Fundamental Agent B와 OHLCV-only
   Agent C 중 어느 구조가 더 안정적인 횡단면 예측력을 보이는가?
2. Train 내부 OOF 점수만 사용하는 양의 Ridge Agent D가 더 단순한 B 또는 C 단독보다
   예측력을 일관되게 개선하는가?
3. 2021년 이후 자료를 보지 않고 선택한 단일 score pipeline을 후속 Phase 5R의
   predict-only 입력으로 완전하게 동결할 수 있는가?

## 3. 입력과 물리 데이터 경계

### 허용 입력

- 날짜별 실제 PIT KOSPI 200 membership
- KRX 개별종목 OHLCV·거래대금·시가총액·상장주식 수
- 공식 KRX KOSPI 200 지수 코드 `1028`
- 실제 DART 접수일 다음 KRX 세션부터 유효한 표준 20개 Fundamental Factor 패널
- 역사적 ticker–security ID–DART corp-code identity
- 실제 가격과 상장주식 수가 역방향으로 기계적으로 변한 `mechanical_reset`, 거래정지,
  membership·identity 단절 감사자료
- config가 명시한 `corporate_action_file`: 미해결 후보 16,151건(유상증자 8,755건 포함)의
  evidence·hash·count 감사에만 사용한다. 이 파일에는 신뢰할 수 있는 effective date, ratio,
  PIT identity가 없으므로 라벨 경계·진입 차단·reset·강제청산 판단에는 사용하지 않는다.
- 날짜별 법정 매도세·농특세 및 동결된 commission·slippage 계약은 라벨 계산에만 사용

### 기간

- Technical 원천 이력: `2004-01-02` 이후부터
- Fundamental 사용 가능 시작: `2016-03-24`
- 모델 fit·OOF 선택에 허용되는 최종 정보일: 실제 마지막 KRX 세션 `2020-12-30`
- 모든 학습·선택 라벨은 **실제 `exit_date <= 2020-12-30`**인 행만 허용한다.
- `signal_date`가 2020년이라고 해서 자동 허용하지 않는다. `t+21` 종료가 2021년에
  발생하는 행은 학습·OOF metric·선택에서 제외한다.
- 2021년 이후 행·파일·partition은 Phase 4E 입력으로 열거나 로드하지 않는다.

모든 입력은 읽기 전에 허용된 별도 물리 partition인지 확인하고 파일·tree SHA-256,
행 수, 최소·최대일, 실제 loader 최대일을 기록한다. 전체 2004~2023 파일을 먼저 읽은 뒤
2020-12-30으로 필터링하는 방식은 허용하지 않는다.

### 절대 금지 경계

- `data/sealed/final_oos_v24/` 열기·목록화·glob·집계·테스트 입력 사용
- 2021~2023 Phase 5R 평가 partition 접근
- 2024년 이후 자료 접근
- 2011~2014 저coverage legacy Fundamental 후보를 Agent B 학습에 사용
- v1 KOSPI 100 Phase 4 Feature partition을 v2 KOSPI 200 학습 입력으로 사용
- 기존 v2 Phase 4/4B/4C/4D 점수·라벨·포트폴리오 결과를 새 학습행으로 직접 재사용

## 4. Universe와 제외 security 계약

학습·OOF 점수·날짜별 횡단면 정규화의 Universe는 `signal_date=t`의 실제 PIT KOSPI 200
구성종목이다. 다음 두 security는 전 기간 학습행, 점수, percentile, 순위에서 제외한다.

| security_id | ticker | 감사용 회사 |
|---|---|---|
| `KRX_COMMON:005930` | `005930` | 삼성전자 |
| `KRX_COMMON:000660` | `000660` | SK하이닉스·과거 하이닉스 |

이름 문자열이 아니라 stable security ID와 6자리 ticker를 이중 검사한다. 시가총액은
Fundamental 가치비율의 동시점 분모로만 허용하며 표본 가중치나 모델 sample weight로
사용하지 않는다.

신호일 membership, 유효한 causal Feature history와 확인된 identity로 구성한 전체 eligible
Universe `U_t`를 B/C/D OOF scoring과 날짜별 percentile에 유지한다. `label_valid`는 fit과
metric의 target 행 선택에만 사용하며 현재 시점 `U_t` 또는 score 행을 제거하는 필터로
사용하지 않는다. Fundamental 행이 없다는 이유로 Agent C 점수행을 제거하지 않는다.

## 5. 공통 라벨 계약

- 신호시점: `t`일 장 종료 뒤
- 가상 진입시점: `t+1` 시가
- 종료시점: `t+21` 시가, 즉 20거래일 보유
- `target_net_active_20`: 종목의 실제 비용 차감 open-to-open 수익률에서 같은 진입·종료
  시점 공식 KRX1028 수익률을 차감
- `target_mae_20`: 진입일 저가부터 종료 전 마지막 보유일까지 실제 low로 계산한 MAE
- `target_quality_20 = target_net_active_20 - 0.5 × target_mae_20`
- 비용: 날짜별 법정 매도세·농특세, 매수·매도 각 2bp commission, 각 10bp adverse slippage

신호일부터 종료일까지 다음 중 하나라도 있으면 경제조건을 추정해 조정하지 않고
`label_valid=false`로 둔다.

- 실제 inverse price/share `mechanical_reset`
- membership·ticker·security identity 단절
- 필수 open·low·지수 관측 누락
- `exit_date > 2020-12-30`

라벨 무효 여부는 현재시점 score universe를 바꾸지 않는다. 무효 행은 학습과 metric에서만
제외하며, 예측 대상 행 자체를 삭제해서 미래 label availability를 현재 점수에 누설하지 않는다.

미해결 corporate action 후보 파일의 16,151건은 effective date·ratio·PIT identity가 없는
evidence-only 자료다. filing 날짜를 거래 효력일로 간주하거나 이 파일로 reset, 라벨 경계,
신규진입 차단 또는 강제청산을 만들지 않는다. 경계는 실제 inverse price/share
`mechanical_reset`과 membership·identity gap으로만 판정하며 경제조건은 추정하지 않는다.

## 6. 모델과 Feature 경계

### Agent B — PIT Fundamental

- 입력: 사전등록 20개 Fundamental Factor의 날짜별 percentile과
  `fundamental_available`
- Phase 4E 파생 percentile 열 suffix는 `__phase4e_percentile`로 고정하며 기존 실험의
  유사 suffix 열을 암묵적으로 대신 읽지 않는다.
- DART 접수일 다음 KRX 거래일부터 알려진 값만 사용
- 모델: `Ridge(alpha=10)` 단일 구조
- 결측 Feature 처리는 현재 Train 내부
  `SimpleImputer(strategy="median", keep_empty_features=true)`만 적합한다.
- 특정 fold의 Train에서 전부 결측인 Feature도 열을 삭제하지 않는다. 해당 fold에서는 imputer가
  `0`으로 채운 뒤 `StandardScaler`에서 zero-effect가 되게 하고 Ridge 계수를 `0`으로 둔다.
  모든 fold와 final fit의 Feature 이름·순서·개수는 사전등록 20개로 유지한다.
- Fundamental 행이 없는 예측 종목은 B percentile `0.5`,
  `fundamental_available=0`으로 기록하고 제거하지 않음
- OHLCV·Agent C 원시 Feature 입력 금지

### Agent C — OHLCV-only

- 입력: causal OHLCV·거래대금·공식 KRX1028 상태
- 모델: 고정 shallow `HistGradientBoostingRegressor`
- DART·Fundamental·Agent B 원시 입력 금지
- 전체 허용 Universe에 독립 점수 생성
- C의 필수 Feature 또는 D meta-input이 Train fold에서 전부 결측이면 열을 삭제하거나 0으로
  대체하지 않고 해당 fold와 실행을 fail-closed한다.

### Agent D — Train-only soft fusion

- 입력: 동일 신호일의 **inner OOF** B percentile, C percentile,
  `fundamental_available`
- 모델: `Ridge(alpha=10, positive=true)`
- B hard Top N filter 금지
- 외부 OOF fold의 D는 그 fold 이전 시점에서 생성된 inner OOF 점수만으로 적합
- B 또는 C의 in-sample fitted prediction을 D 학습 입력으로 사용 금지

## 7. 시간순 OOF·purge·embargo

- Random split과 row shuffle을 금지한다.
- 초기 학습은 Feature별 first-valid date부터 시작한다.
- Fundamental이 필요한 B와 D의 날짜는 `2016-03-24` 이후로 제한한다.
- `2017`, `2018` anchored B/C OOF는 D meta-training 전용이며 primary 선택 metric에 넣지 않는다.
- primary 선택은 `2019`, `2020` anchored annual OOF만 사용한다.
- 각 평가 fold 시작 전 최대 label horizon 20세션을 training에서 purge한다.
- 평가 block 뒤 20세션 embargo는 해당 뒤쪽 행이 이후 training에 재진입할 때만 적용한다.
  forward-only 경계 앞에서 purge와 중복 차감하지 않는다.
- scaler, imputer, percentile calibration, 모델과 D 계수는 각 fold Train에서만 적합한다.
- 날짜별 metric은 각 날짜의 eligible Universe 안에서 계산하며 연도 전체 `nlargest(N)`를
  사용하지 않는다.

각 OOF 연도는 실제 Feature coverage와 purge 이후 행 수 감사를 통과해야 한다. 2017~2018
meta-training fold 또는 2019~2020 selection fold가 최소 표본 gate를 충족하지 못하면 임의로
표본을 보간하지 않고 `INSUFFICIENT_HISTORY`로 기록한다. 2021년 이후를 당겨 대체하지 않는다.

## 8. 모델 선택 규칙

항상 `B_ONLY`, `C_ONLY`, `D_SOFT_FUSION` 세 후보를 같은 OOF 날짜·라벨 계약으로 보고한다.

먼저 `B_ONLY`와 `C_ONLY`의 2019~2020 selection OOF를 다음 순서로 정렬해 최선 단독 후보를
고정한다.

1. OOF 일별 `target_quality_20` Spearman Rank IC 평균 내림차순
2. Rank IC가 비음수인 selection 연도 수 내림차순
3. 날짜별 score 상위 10개 `target_quality_20` 평균의 연도 평균 내림차순
4. 완전 동률이면 단순 구조 우선순위 `C_ONLY`, `B_ONLY`

D는 다음을 모두 만족할 때만 단독 후보보다 우선할 수 있다.

- D 평균 Rank IC가 위 규칙으로 정한 최선 단독 후보보다 **엄격히 큼**
- D의 비음수 selection 연도 수가 최선 단독 후보보다 적지 않음
- D의 날짜별 Top10 `target_quality_20` 연도 평균이 최선 단독 후보보다 작지 않음
- `2019`, `2020` 두 selection 연도 모두에 유효한 D OOF 점수가 존재
- D 입력이 전부 inner OOF였다는 감사 PASS
- Ridge 계수가 모두 비음수이고 실제 fitted state 직렬화 PASS

선택 primary의 평균 Rank IC가 양수가 아니거나 두 selection 연도 중 하나라도 Rank IC가
음수면 `phase4e_model_gate_pass=false`다. 이 경우에도 B/C/D 모델과 점수·지표·감사는
재현 가능하게 bundle에 보존한다. 사용자의 사전 일괄 수정 승인 범위에 따라 후속 Phase 5R의
predict-only 진단은 허용하되 `phase5_gate_pass=false`를 상속하며 통과·승격 후보가 될 수 없다.
NDCG, AUC, RMSE는 진단 지표이며 선택 규칙을 사후 대체하지 않는다. Phase 4E는
수익률·MDD·Sharpe로 모델을 재선택하지 않는다.

## 9. 출력과 frozen bundle

실제 출력 경로는 `artifacts/v2_phase4e_ai_model/`이며 최소 다음 파일을 포함한다.

- `frozen_model_bundle.pkl`
- `selection_metrics.csv`
- `oof_scores.csv.gz`
- `audit.json`
- `label_audit.json`
- `fold_boundaries.json`
- `feature_contract.json`
- `component_hashes.json`
- `selected_primary.json`
- `decision.json`
- `manifest.json`

`frozen_model_bundle.pkl` 하나에 B/C/D의 실제 fitted estimator 세 개와 추론에 필요한 상태를
직렬화한다. 개별 model 파일은 요구하지 않는다. `component_hashes.json`에는 세 estimator의
실제 직렬화 component hash를 기록한다. `selected_primary.json`에는 `experiment_id`,
`primary_agent`, `phase4e_model_gate_pass`, `diagnostic_allowed`, `model_state_hash`,
`selection_metrics`를 기록한다. Feature 이름·순서·dtype은 `feature_contract.json`과 manifest에,
fit 최대일과 라벨 exit 최대일은 manifest에 기록한다. 문자열 `TRAINED`나 파라미터 요약 hash를
실제 model component hash 대신 사용할 수 없다.

`frozen_model_bundle.pkl`의 bytes로 계산한 bundle SHA-256과, `manifest.json` 자신을 제외한
필수 산출물의 상대경로·bytes·SHA-256을 정렬해 계산한 canonical tree SHA-256은 서로 다른
값으로 별도 기록한다. manifest에는 bundle SHA-256, canonical tree SHA-256,
component hashes와 Python·핵심 라이브러리 runtime hash를 pin한다. primary와 독립
reproduction의 필수 파일은 byte-identical이어야 하며, 후속 Phase 5R은 이 hash 집합을 먼저
검증한 뒤 predict-only로 사용한다.

### 실행 후 v1 산출물 정합성 편차

위 사전등록 요구는 삭제하지 않는다. 실제 동결 v1 산출물은 다음 호환성 계약으로 해석하며
모델·예측·선택 결과를 변경하지 않는다.

- `selected_primary.json`의 사전등록 `diagnostic_allowed` 의미는 실제 필드
  `phase5r_predict_only_diagnostic_allowed`로 직렬화됐다.
- 실제 `feature_contract.json`은 dtype를 별도 기록하지 않았다. 후속 inference는 입력을
  numeric으로 coercion한 뒤 비수치·누락·추가 열을 fail-closed하고, manifest와
  `feature_contract.json`의 Feature 이름·순서를 정확히 검증한다.
- 별도 runtime hash 필드는 없으며 `manifest.json.input_hashes.runtime_versions`의 정확한
  versions map, `data_version`과 manifest 파일 SHA-256을 함께 pin해 runtime·data 계약을
  검증한다.
- 권위 무결성 값은 bundle SHA-256
  `da9b8111c3c9c59126746075bc019a5218d33c0259a1c22d0eea00ea3cd3c550`, artifact tree SHA-256
  `2cb97749c42406bd36d088b8504226a6b86296230ef51a316000156343a813e1`, manifest SHA-256
  `08bb74b3319a77af8ecc2f1426cb8cde07bc2f68ef44d1f860dde7e83716f6dc`다.
- sklearn estimator를 bundle에서 reload한 뒤 다시 pickle한 bytes의 component/model-state
  hash는 객체 identity와 pickle memoization 때문에 안정적인 무결성 비교값이 아니다. 실제
  bundle reload 32개 고정 probe prediction은 원본과 bit-identical했으므로 동결 모델 변경은
  금지하고 위 권위 hash·versions·Feature 계약을 사용한다.

## 10. 금지사항

- 포트폴리오 비중·주문·체결·원장·백테스트 생성
- 2021~2023 수익을 보고 모델·Feature·계수·선택 gate 변경
- Phase 5R의 Top50 core, alpha tilt, 현금, benchmark 또는 경제 gate 계산
- 기존 Phase 4 결과를 새 OOF라고 표현
- 결과 확인 후 같은 Experiment에서 모델 family·hyperparameter·target 변경
- protected OOS, 외부 주문, 모의계좌, 실계좌, 네트워크 주문 전송

## 11. 구현 파일

- `src/kospi200_phase4e/`: config, physical loader, mechanical-reset-aware labels, B/C/D OOF,
  selection, bundle, audit, CLI
- `configs/v2_phase4e_ai_model.json` (`corporate_action_file` 필수)
- `tests/test_kospi200_phase4e_*.py`
- `artifacts/v2_phase4e_ai_model/`
- `artifacts/v2_phase4e_ai_model_reproduction/`
- `docs/stages/v2_phase_4e_report.md`
- `experiments/registry.csv`
- `docs/DECISION_LOG.md`

## 12. 테스트

- 모든 label의 `exit_date <= 2020-12-30`
- 2021년 이후 파일을 loader가 읽기 전 거부
- actual inverse price/share mechanical_reset·membership·identity 단절 교차 유효 라벨 0건
- unresolved CA 후보 16,151건과 유상증자 8,755건의 evidence/hash/count 일치 및
  filing 기반 block·reset·forced-exit 0건
- label availability 변화로 현재 score 행 수가 달라진 사례 0건
- 제외 security의 Feature·라벨·학습행·OOF 점수 0건
- Agent B PIT receipt-date와 Feature 경계
- Agent C OHLCV-only 입력 경계
- D inner OOF-only 및 positive coefficient
- purge 단일 적용과 조건부 embargo
- 날짜별 percentile·Top N metric
- 실제 직렬화 component·bundle·canonical tree·runtime hash pin
- primary/reproduction byte determinism
- 포트폴리오·Order 객체와 실행 엔진 호출 0건
- Phase 4E 전용 및 전체 회귀 PASS

## 13. 실행 명령

아래 명령은 명세·Decision Log·registry·config가 결과 확인 전에 동결되고 물리 입력 감사가
통과한 뒤에만 실행한다.

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_kospi200_phase4e_*.py' -v
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m kospi200_phase4e.cli run --config configs/v2_phase4e_ai_model.json --output artifacts/v2_phase4e_ai_model
.venv\Scripts\python.exe -m kospi200_phase4e.cli run --config configs/v2_phase4e_ai_model.json --output artifacts/v2_phase4e_ai_model_reproduction
```

## 14. 완료 조건

1. 입력의 물리 최대일과 모든 유효 label exit 최대일이 `2020-12-30` 이하다.
2. 모든 무결성·입력 경계·OOF·purge·embargo 테스트가 통과한다.
3. 세 후보의 OOF 지표와 선택 규칙이 결과 확인 전 동결돼 있다.
4. 실제 B/C/D fitted state가 단일 bundle에 직렬화되고 component·bundle·tree·runtime hash가 있다.
5. primary와 reproduction 필수 파일이 byte-identical이다.
6. 모델 gate 실패도 `phase4e_model_gate_pass=false`와 함께 재현 가능하게 보존한다.
7. 포트폴리오·주문·Phase 5R 평가·protected OOS 접근이 모두 0이다.
8. 전체 회귀가 실패하면 Phase 5R을 실행하지 않는다. 모델 gate만 실패한 경우에는 사용자 승인
   범위의 predict-only 진단을 허용하되 `phase5_gate_pass=false`를 상속한다.

## Codex Handoff

먼저 2020-12-30 이하 물리 partition과 label exit-date guard를 구현한다. 그 뒤 mechanical-reset-aware
라벨, B/C 독립 anchored OOF, D inner-OOF stacker, 고정 선택 규칙과 실제 model serialization을
구현한다. 전용·전체 테스트와 독립 reproduction이 모두 통과한 경우에만 registry의 실제
code/config/data/model/bundle hash를 기록한다. Phase 4E 보고서와 bundle 검토가 끝나기 전에는
Phase 5R을 실행하거나 2021년 이후 자료를 열지 않는다.
