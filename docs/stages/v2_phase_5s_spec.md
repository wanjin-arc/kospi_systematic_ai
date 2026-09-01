# v2 Phase 5S — 동결 모델 Predict-only 무결성 감사 사전등록 명세

## 1. 단계 식별과 목적

- Experiment ID: `EXP-20260901-004`
- 단계: `v2 Phase 5S`
- 설정: `configs/v2_phase5s_share_change_safe_integrity.json`
- 선행 Experiment: `EXP-20260901-003` Phase 4F
- 선행·대체 대상: `EXP-20260901-002` Phase 5R
- 평가기간: `2021-01-04`~`2023-12-28`
- 증거 지위: 이미 소비된 개발자료의 predict-only 무결성 진단

Phase 5S의 목적은 검증된 Phase 4F primary를 재학습 없이 2021~2023에 적용해 점수와 차단된
주문 의도를 만들고, portfolio accounting 전에 stable identity와 corporate-action 권리조건이
충분한지 fail-closed 감사하는 것이다. 이 단계는 포트폴리오 백테스트, 자기금융 원장, 성과
metric 또는 경제 gate를 실행하지 않는다.

## 2. 선행 모델 승인과 hash 계약

Phase 5S config의 다음 값은 Phase 4F primary와 reproduction 검증이 끝난 뒤 실제 64자리 hash로
교체한다. `PHASE4F_OUTPUT_PENDING` 상태에서는 preflight와 run을 금지한다.

- `phase4f_experiment_id=EXP-20260901-003`
- `phase4f_manifest_sha256`
- `phase4f_artifact_tree_sha256`
- `phase4f_bundle_sha256`
- `phase4f_model_hash`

loader는 Phase 4F manifest schema, bundle schema·type, Experiment ID, primary, Feature 이름과 순서,
component/model-state/bundle/tree/manifest hash, runtime version, fit/exit cutoff를 검증한다.
`SUPERSEDED` decision이거나 `phase5s_predict_only_diagnostic_allowed=true`가 아니면 중단한다.

Phase 5S는 동결 primary 한 개만 `include_controls=false`로 predict한다. B/C/D 재적합, imputer·scaler
재적합, threshold·가중치 선택, 후보 재선택은 모두 금지한다. Phase 4F model gate 실패를 상속한
진단 bundle은 점수 구조 감사만 할 수 있으며 Phase 5 gate를 통과할 수 없다.

## 3. 데이터·Universe와 접근 경계

허용 입력은 다음으로 제한한다.

- 시점별 실제 KOSPI 200 membership과 KRX 시장자료: `2004-01-02`~`2023-12-28`
- 실제 predict·감사 구간: `2021-01-04`~`2023-12-28`
- 공식 KRX KOSPI 200 지수코드 1028
- 확정 수치 재무 Factor와 동시점 기술 Feature
- 미확정 corporate-action 후보 파일: 증거·hash·count 감사 전용
- Phase 4F primary bundle과 manifest

삼성전자 `005930`과 SK하이닉스 `000660`은 score Universe, 횡단면 순위, liquidity core와 주문
의도에서 제외한다. 공식 KRX 1028 지수에서는 제거하지 않는다.

모델 identity에 사용하는 membership ticker는 exact `^\d{6}$`여야 한다. 시장의 비정규 raw
ticker를 구성종목 코드로 임의 변환하지 않으며 정규화 충돌 가능성이 있으면 fail-closed한다.
`KRX_COMMON:<ticker>`는 영구 issuer·share-class·successor identity의 증거가 아니다.

`data/sealed/final_oos_v24/`는 열기, 스캔, glob, 행 읽기, 요약, 집계 및 테스트 입력 사용을 모두
금지한다. 2021~2023 결과는 독립 OOS 또는 Test로 표현하지 않는다.

## 4. 주식수 후보와 corporate-action 계약

Phase 4F와 동일한 다음 경계를 사용한다.

```text
abs(log(current_listed_shares / prior_listed_shares)) >= log(1.20)
```

- 같은 exact raw ticker의 연속 거래소 세션만 비교한다.
- 전일·당일 상장주식수가 모두 유한한 양수여야 한다.
- 후보 판정은 listed shares만 사용하고 가격은 사용하지 않는다.
- 결측·무한·0·음수 관측은 `LISTED_SHARES_OBSERVATION_GAP`으로 fail-closed한다.
- 후보일·관측 공백일에서 기술 Feature segment를 초기화한다.
- 후보를 corporate-action 종류, 효력일, 배율 또는 old-holder 권리로 확정하지 않는다.
- executable `CorporateAction`, 보유수량 조정, cash-in-lieu, 강제청산을 생성하지 않는다.

관측 주식수·가격 역관계는 진단값일 뿐 다음 네 증거를 대신하지 않는다.

1. PIT issuer·share class·successor stable identity
2. 원문 또는 권위 구조화 자료의 권리·분할 비율과 old-holder terms
3. 확정 효력일과 실제 거래세션
4. KRX 가격·상장주식수의 동일 배율 교차검증

평가 경로의 후보 중 하나라도 이 계약을 충족하지 못하거나 stable identity가 완전하지 않으면
portfolio accounting과 모든 성과 계산을 금지한다.

## 5. Predict-only 포트폴리오 의도

다음 구조는 성과가 아니라 주문 생성 규칙의 정적 감사를 위해서만 사용한다.

- 20거래세션마다 재조정
- 최근 20세션 거래대금 상위 50개 liquidity core
- core 50개 동일가중 합계 70%, 종목당 1.4%
- 동결 primary 점수 상위 10개에 합계 20%, 종목당 2% 추가
- 현금 10%, 최대 종목비중 3.4%
- signal `t` 장 종료 후 `t+1` 시가 주문 의도
- signal close 대비 5% 초과 gap 매수 제한
- 최대 보유 20세션
- 공매도·레버리지·피라미딩·손절·익절 없음

생성된 모든 주문은 `BLOCKED_NOT_SUBMITTED` 의도이며 외부 주문이 아니다. 실제 주문 제출,
계좌·네트워크 호출과 보유 원장은 0건이어야 한다.

## 6. Benchmark와 성과 비평가 원칙

공식 KRX 1028은 원시 참조 수준을 확인할 수 있다. EX2의 price-unit 및 issuer-cap-value
sensitivity는 권리조건이 없는 비자기금융 진단일 뿐 canonical return, 상하한 또는 경제 gate가
아니다. 사건 종목 제거·사후 재가중으로 수익률을 만들지 않는다.

아래 값은 config에 역사적 사전등록값으로 보존하지만 Phase 5S에서는 모두
`NOT_EVALUATED_PRE_EXECUTION_INTEGRITY_BLOCK`으로 기록한다.

- neutral core 대비 순초과수익·rolling 12개월
- MDD와 neutral 대비 MDD shortfall
- EX2 대비 연환산 초과수익·downside capture
- 공식 KRX 1028 대비 최악 연도·rolling 12개월
- 평균 주식 노출, 거래 수, 1배·2배 비용 stress

backtest engine import·호출, strategy/neutral NAV, closed trade, turnover, Sharpe, MDD, 연도별
수익률 및 Phase 5 경제 gate 판정은 금지한다.

## 7. 사전등록·preflight와 판정

`experiments/registry.csv`에 `EXP-20260901-004`가 정확히 한 행 존재하고 상태가
`preregistered`여야 한다. Phase 4F hash가 config에 반영된 뒤 preflight가 계산한 다음 값을
결과 관측 전에 registry에 동결한다.

- `code_hash`
- `config_hash`
- `data_version`
- `model_hash=phase4f_model_hash`
- `final_oos_accessed=false`

`data_version`에는 입력 tree·최대일·runtime·비용·engine config hash, Phase 4F 네 hash, gross ratio
1.20과 label/technical boundary 정책을 포함한다. 하나라도 바뀌면 기존 hash를 폐기하고 실행 전에
다시 동결한다. registry는 primary와 reproduction 완료 전까지 `preregistered`로 유지한다.

무결성 gate는 다음 네 항목이다.

1. Phase 4F model gate
2. stable identity contract 완전성
3. 모든 후보의 승인 corporate-action terms 완전성
4. canonical EX2 return 평가 가능성

현재 입력 계약에서는 stable identity와 승인 terms가 완전하지 않으므로 예상 decision은
`REJECT_PHASE5S_UNRESOLVED_CA_AND_IDENTITY_CONTRACT`다. 모든 gate가 우연히 true가 되더라도 이
실험에서 engine을 실행하지 않고 `INTEGRITY_CONTRACT_COMPLETE_NEW_EXPERIMENT_REQUIRED`로 종료한다.

## 8. 산출물

본 실행은 `artifacts/v2_phase5s_share_change_safe_integrity/`, 독립 재현은
`artifacts/v2_phase5s_share_change_safe_integrity_reproduction/`에 쓴다. 최소 산출물은 다음과 같다.

- `scores.csv.gz`
- `share_reset_candidates.csv`
- `order_intents_blocked.csv`
- `ex2_share_reset_events.csv`
- `official_krx1028_reference.csv`
- `ex2_price_unit_sensitivity.csv`
- `ex2_issuer_cap_value_sensitivity.csv`
- `audit.json`
- `decision.json`
- `manifest.json`

manifest schema는 `v2-phase5s-share-change-safe-integrity-release-v1`이다. Phase 4F 네 hash,
입력·출력 hash, primary, fit·engine·성과·외부주문·OOS 접근 0건과 최종 decision을 기록한다.
두 실행의 필수 파일은 byte-identical해야 한다.

## 9. 테스트와 실행 명령

PowerShell에서 project Python과 `PYTHONPATH=src`를 사용한다.

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_kospi200_phase4f*.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m kospi200_phase5s.cli preflight --config configs/v2_phase5s_share_change_safe_integrity.json
.\.venv\Scripts\python.exe -m kospi200_phase5s.cli run --config configs/v2_phase5s_share_change_safe_integrity.json --output artifacts/v2_phase5s_share_change_safe_integrity
.\.venv\Scripts\python.exe -m kospi200_phase5s.cli run --config configs/v2_phase5s_share_change_safe_integrity.json --output artifacts/v2_phase5s_share_change_safe_integrity_reproduction
```

Phase 5S config의 `PHASE4F_OUTPUT_PENDING` 네 값을 실제 Phase 4F primary hash로 교체하고 registry
hash를 동결하기 전에는 위 preflight와 run을 실행하지 않는다.

핵심 테스트는 Phase 4F bundle schema·hash·runtime·Feature 계약, superseded source 거부,
fit 호출 부재, backtest engine import·호출 부재, exact raw ticker, gross ratio 경계, 후보 재계산
일치, executable action 0, blocked order intents, performance 미평가와 protected OOS 비접근을
검증한다.

## 10. 완료 조건

다음을 모두 만족하면 Phase 5S predict-only 무결성 감사를 완료로 기록한다. 이는 Phase 5 성과
통과나 70/20/10 구조의 거래 승격을 뜻하지 않는다.

1. 전용 테스트와 전체 회귀 테스트가 통과한다.
2. Phase 4F manifest·tree·bundle·model hash와 runtime·Feature 계약이 일치한다.
3. preflight와 registry의 code/config/data/model hash가 일치한다.
4. score 행 수가 predict 전후 동일하고 제외 두 종목의 점수·순위·주문 의도가 0이다.
5. fit 호출, executable corporate action, engine 호출, portfolio accounting, 성과 metric,
   외부 주문과 OOS 접근이 모두 0이다.
6. 모든 주문 의도가 `BLOCKED_NOT_SUBMITTED`다.
7. 모든 경제 gate가 `NOT_EVALUATED_PRE_EXECUTION_INTEGRITY_BLOCK`이다.
8. EX2 sensitivity가 비자기금융 진단이며 return·bound·gate로 사용되지 않았음을 기록한다.
9. primary/reproduction 필수 파일이 byte-identical하다.
10. 실제 감사 count와 decision을 registry와 `v2_phase_5s_report.md`에 사실대로 기록한다.

## Codex Handoff

- 선행 조건: Phase 4F primary/reproduction 검증 및 실제 manifest/tree/bundle/model hash 확정
- 설정 갱신: `configs/v2_phase5s_share_change_safe_integrity.json`의 네 pending hash만 실제값으로
  교체하고 config/data hash를 다시 계산
- 실행 전: 전용·전체 테스트, preflight, registry `EXP-20260901-004` 정확한 hash 동결
- 실행: predict-only primary와 reproduction을 같은 동결 상태에서 각각 한 번 수행
- 검증: fit·engine·성과·실행 action·외부 주문·OOS 접근 0, blocked intents와 byte determinism
- 예상 판정: `REJECT_PHASE5S_UNRESOLVED_CA_AND_IDENTITY_CONTRACT`
- 금지: Phase 4F 재학습, 2021~2023 결과 기반 포트폴리오·threshold·gate 변경, canonical EX2
  수익률 주장, protected OOS 접근, 실주문·배포
