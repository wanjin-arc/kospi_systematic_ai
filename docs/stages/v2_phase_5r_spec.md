# v2 Phase 5R — 동결 AI 모델 Predict-only 포트폴리오 무결성 감사 명세

## 1. 상태와 선행 관계

- Experiment ID: `EXP-20260901-002`
- 단계 역할: Phase 4E 동결 모델의 **predict-only 소비 개발 무결성 감사**
- 평가기간: `2021-01-01~2023-12-28`
- 상태: Phase 4E bundle 동결 완료. 두 번의 pre-output 시도 뒤 CA·identity 계약 미충족으로
  `REJECT_PHASE5R_UNRESOLVED_CA_AND_IDENTITY_CONTRACT`; canonical 성과는 `NOT_EVALUATED`
- 선행 Experiment: `EXP-20260901-001` (`v2 Phase 4E`)
- superseded 기록: `EXP-20260831-001`은 실행 전 연구 순서 정정으로 superseded

기존 Phase 5R은 2004~2023에서 모델 fit·선택과 포트폴리오 평가를 한 Experiment에
묶었다. 사용자가 먼저 Phase 4 데이터 경계 안에서 AI 모델을 만들고, 그 뒤 Phase 5R에서
평가하도록 순서를 정정했으므로 이 명세는 모델 학습 기능을 제거한다.

Phase 5R은 Phase 4E가 선택한 primary score pipeline과 bundle hash를 그대로 사용한다.
2021~2023 결과를 보고 B/C/D 중 다른 후보로 바꾸거나 fit·calibration·threshold 선택을
수행할 수 없다. 이 기간은 시간상 후행하지만 이미 소비된 개발자료이므로 독립 OOS 또는
최종 Phase 5 통과 증거가 아니다.

포트폴리오 성과 계산보다 corporate-action terms와 stable identity의 자기금융 가능성을
먼저 검사한다. 이 preflight가 실패하면 점수·주문 의도·후보 ledger까지만 보존하고
backtest engine, 보유수량 조정, 원장과 경제 gate를 실행하지 않는다.

## 2. 연구 질문

1. corporate-action·stable identity 계약이 자기금융 포트폴리오 평가에 충분한가?
2. 위 계약을 통과한 경우에만, 2020-12-30까지 완성된 라벨로 동결한 AI 점수가 비모델
   `NEUTRAL_CORE`보다 기본비용과 2배 비용 모두에서 경제적 alpha를 만드는가?
3. 삼성전자와 SK하이닉스를 매수하지 않는 포트폴리오가 공식 KRX KOSPI200 대비
   극단적으로 뒤처지지 않으면서 하방을 줄이는가?
4. 성과 차이를 대형주 제외효과, 비시총가중 유동성 core 구성효과, 동결 모델 alpha로
   분해할 수 있는가?

## 3. 입력과 물리 데이터 경계

### 필수 입력

- hash 승인된 `EXP-20260901-001` Phase 4E frozen bundle
- bundle 안의 `selected_primary.json`, B/C/D estimator state, Feature contract,
  fit/label cutoff 감사, component·bundle·tree·runtime hashes와 manifest
- 2021~2023 날짜별 실제 PIT KOSPI 200 membership
- 2021~2023 KRX 개별종목 OHLCV·거래대금·시가총액·상장주식 수
- 공식 KRX KOSPI 200 지수 코드 `1028`
- 2021~2023 실제 접수일 기준 PIT Fundamental Factor 갱신분
- config가 명시한 `corporate_action_file`: 미해결 후보 16,151건(유상증자 8,755건 포함)의
  evidence·hash·count 확인 전용이며 거래 판단 입력이 아니다.
- 날짜별 비용표와 결정론적 long-only 현금주식 실행 엔진

### 기간과 context

- 평가 시작: 첫 2021년 KRX 세션
- 평가 입력 최대일: `2023-12-28`
- 유효 성과 라벨·기간청산: `exit_date <= 2023-12-28`
- Feature lookback에 필요한 2020년 말 context는 Phase 4E bundle이 기록한 end-state 또는
  별도 `CONTEXT_ONLY` physical partition으로만 허용한다.
- context 행은 fit, selection, metric, 주문일 또는 평가 수익에 포함하지 않는다.
- 평가 partition을 읽은 뒤 날짜로 잘라 context와 평가를 구분하는 방식은 허용하지 않는다.

모든 파일은 읽기 전에 role, hash, bytes, 행 수, 최소·최대일을 검증한다. 실제 loader는
`rows_loaded_by_role`, `maximum_loaded_date`, `fit_rows=0`, `selection_rows=0`을 감사파일에
기록한다.

### 절대 금지 경계

- Phase 5R 안에서 `fit`, `fit_transform`, 재적합, fine-tuning, calibration 수행
- B/C/D primary 재선택 또는 bundle 외 모델 로드
- Phase 4E model·Feature 순서·계수·imputer·scaler 변경
- 2024년 이후 자료 및 `data/sealed/final_oos_v24/` 접근
- v1 Development Test·KOSPI100 partition 사용
- 실제 주문·모의계좌 주문·외부 서비스·네트워크 주문 전송

## 4. Frozen bundle 검증과 predict-only 계약

Phase 5R은 실행 전에 다음을 모두 확인한다.

1. registry에 승인된 Phase 4E bundle hash와 실제 canonical tree hash가 일치한다.
2. `selected_primary.json`의 Experiment ID가 `EXP-20260901-001`이다.
3. fit maximum date와 valid label exit maximum date가 모두 `2020-12-30` 이하다.
4. `frozen_model_bundle.pkl` 안에 B/C/D estimator 세 개가 있고 component hashes가 일치한다.
5. bundle SHA-256, canonical tree hash, manifest hash와 Python·핵심 라이브러리 runtime hash가
   모두 동결값과 일치한다.
6. Feature column 이름·순서·dtype·결측 계약이 일치한다.
   B가 selected primary의 의존성이면 20개 고정 Feature 순서와 동결 imputer·scaler 상태도 검증한다.
7. `phase4e_model_gate_pass=false`이면 실행은 진단으로만 계속하며
   `phase5_gate_pass=false`를 변경 불가능하게 상속한다.

Fundamental percentile 열은 Phase 4E bundle 계약의 `__phase4e_percentile` suffix와 정확히
일치해야 한다. suffix가 다르거나 `corporate_action_file` 입력이 없으면 predict-only 실행을
시작하지 않는다.

선택 primary가 `B_ONLY`, `C_ONLY`, `D_SOFT_FUSION` 중 무엇이든 Phase 5R 전체에서 고정한다.
`include_controls=false`로 pin하고 selected primary의 의존 estimator만 실행한다. 다른 후보나
대조군은 inference·성과 계산·선택 대안 보고를 모두 금지한다. D가 선택된 경우에만 동결된
B·C upstream estimator와 D 결합 estimator를 의존성으로 함께 predict-only 실행한다.

Phase 5R 코드에서 estimator의 `fit` 계열 메서드가 한 번이라도 호출되면 실행 전체를
무효화하고 결과를 승격하지 않는다.

### Phase 4E v1 bundle 호환성 검증

사전등록 무결성 요구는 보존한다. 첫 verifier 호환성 정정 당시 Phase 5R은 registry 등록과
유효 산출물 생성 전이었으므로 다음 v1 호환성 검증을 적용했다. 이는 모델·prediction·
포트폴리오·경제 gate 변경이 아니다.

- bundle reload 뒤 estimator를 다시 pickle해 component/model-state bytes hash를 비교하지 않는다.
- manifest의 `component_sha256`가 `agent_b`, `agent_c`, `agent_d` 키와 유효한 SHA-256 값 형식을
  갖는지 확인한다.
- manifest `model_state_hash`와 Phase 5R config의 동결 model-state 참조
  `phase4e_model_hash`가 일치해야 한다.
- exact bundle SHA-256, artifact tree SHA-256, manifest SHA-256,
  `input_hashes.runtime_versions` exact map과 `data_version`을 검증한다.
- `phase5r_predict_only_diagnostic_allowed`가 true인지 확인한다. Feature dtype 미기록은 numeric
  coercion 뒤 비수치·누락·추가 열 fail-closed와 정확한 Feature order 검증으로 보완한다.

### 두 pre-output 중단과 DEC-103 supersede

첫 시도는 artifact와 공개 metric 0건 상태에서 `2021-04-15` `035720`의 관측 share reset을
처리하다 중단됐다. DEC-103은 `effective-day open / prior close`와 `listed_shares` 역비율이
맞으면 이를 `READY`로 전달하는 Phase 5R 전용 호환성으로 정정했으나, 두 번째 시도는
`2021-01-15` `020560`을 포함한 EX2 회계 계약에서 다시 중단됐다. 두 시도 모두 성과·경제
gate·유효 결과 산출물을 남기지 않았다.

성과가 관측되기 전에 권위 문서 `docs/V25_KOSPI_RAW_AUDIT_KO.md`와 대조한 결과 DEC-103은
유효 성과·경제 산출 전 superseded됐다. 기계적 action을 회계상 확정하려면 다음 네 증거가 모두 필요하다.

1. PIT 안정 종목 identity와 당시 지수 편입
2. 원문 공시 또는 구조화 응답의 권리·분할 비율
3. 효력일과 실제 거래세션
4. KRX 가격·상장주식수의 동일 배율 교차검증

따라서 Phase 5R은 다음 fail-closed 계약을 사용한다.

- 같은 ticker의 연속 세션에서 20% 이상 `listed_shares` 변화가 보이면 추가 감사용
  `UNRESOLVED_SHARE_RESET_CANDIDATE`만 만든다.
- open·close·가격/주식수 역관계는 candidate ledger의 진단 필드일 뿐 `READY`, split ratio,
  cash-in-lieu 또는 보유수량·원가 변환을 만들지 않는다.
- `KRX_COMMON:<ticker>`는 역사적 stable security identity 증명이 아니다. issuer·share class·
  successor를 연결한 승인 identity map이 없으면 `stable_identity_contract_complete=false`다.
- 후보가 포트폴리오 또는 EX2 구성 경로에 하나라도 있거나 stable identity가 불완전하면
  backtest engine과 포지션 조정을 호출하지 않는다.
- 관측 역관계는 Feature·label reset 후보로 사용할 수 있지만 old-holder return이나 canonical
  benchmark return 변환에는 사용할 수 없다.
- selection, Feature, score, threshold, 사전등록 portfolio·경제 gate는 사후 변경하지 않는다.
- 최종 decision은 `REJECT_PHASE5R_UNRESOLVED_CA_AND_IDENTITY_CONTRACT`이고 모든 canonical
  성과·경제 gate는 `NOT_EVALUATED`다.

## 5. Universe와 제외 security 계약

신호일 `t`의 실제 PIT KOSPI 200 구성종목이 기본 Universe다. 다음 제외 ticker alias는
Feature inference, 횡단면 percentile, 점수, 순위, 유동성 core, 매수 후보와 주문에서
전 기간 제외한다.

| security_id | ticker | 감사용 회사 |
|---|---|---|
| `KRX_COMMON:005930` | `005930` | 삼성전자 |
| `KRX_COMMON:000660` | `000660` | SK하이닉스·과거 하이닉스 |

security ID와 정확한 6자리 숫자 ticker를 이중 검사한다. `KRX_COMMON:<ticker>`는 제외 rule의
alias일 뿐 역사적 stable identity 증명으로 간주하지 않는다. 두 종목은 공식 KRX1028과
EX2 민감도 진단에만 남는다. 시가총액은 Fundamental 가치비율의 PIT 분모와
`EX2_ISSUER_CAP_VALUE_SENSITIVITY`에만 사용하며 포트폴리오 보유비중에는 쓰지 않는다.

신호일 membership, 신규진입 가능, 유효 OHLCV, 동결 Feature의 최소 과거길이와 승인된
stable identity만 예측 전 무결성 필터로 허용한다. Fundamental
행이 없다는 이유로 C 또는 D 예측 후보를 제거하지 않으며 Phase 4E 계약에 따라 B 중립값과
availability flag를 사용한다.

미해결 corporate action 후보 파일은 effective date·ratio·PIT identity가 없으므로 filing
timing, 신규진입 차단, reset, 보유수량 조정 또는 강제청산에 사용하지 않는다. 16,151건과
그중 유상증자 8,755건은 evidence·hash·count만 감사한다. 실제 inverse price/share 변화는
Feature·label reset과 terms 복구 대상 후보로만 표시한다. 해당 후보를 보유·benchmark 경로가
가로지르면 경제조건을 추정하지 않고 Phase 5R 성과 평가를 중단한다.

## 6. 포트폴리오와 체결

정상/위험 국면 분류와 시총가중 보유비중을 사용하지 않는다. 선택 primary 모델과 관계없이
다음 규칙을 고정한다. 다만 CA·identity preflight가 실패한 현재 release에서는 주문 의도까지만
감사하고 체결·포지션·수익률 계산에는 적용하지 않는다.

1. 매 20거래일 `t` 종가 뒤 리밸런싱한다.
2. 제외 두 종목을 뺀 PIT 구성종목 중 `t`까지 trailing 20세션 중앙 거래대금
   (`close × volume`) 상위 50개를 유동성 core로 정한다.
3. 거래대금 동률은 ticker 오름차순으로 결정한다.
4. core 50개에 각각 1.4%, 총 70%를 동일 배분한다.
5. 같은 core 안에서 동결 primary 점수 상위 10개에 각각 2.0%, 총 20%를 추가한다.
6. 상위 10개는 각 3.4%, 나머지 40개는 각 1.4%, 총 주식노출 90%, 현금 10%다.
7. 종목당 상한 3.4%, 상위 5종목 합계 17%를 유지한다.
8. 주문은 `t`에서 동결한 `limit_price = Close[t] × 1.05` one-sided buy limit다.
9. `t+1` 시가가 limit보다 높으면 `UNFILLED_GAP_LIMIT`; 하락 gap은 정상 체결한다.
10. 신호 생성기는 실제 `t+1` 시가·거래량을 읽어 주문 존재 여부를 바꾸지 않는다.
11. 손절·익절은 사용하지 않고 실제 진입일부터 20세션 ordinary open exit를 적용한다.
12. long-only, 현금주식, whole share, no leverage, no short, no pyramiding을 유지한다.

매수·매도에 각 2bp commission과 각 10bp adverse slippage, 날짜별 법정 매도세·농특세를
적용한다. 2배 비용 stress에서는 commission과 slippage만 2배로 하고 법정 세금을 제거하거나
축소하지 않는다. 기간말 미청산 포지션도 평가 종료일의 사전등록 청산·비용 계약으로
reconciliation한다.

## 7. Benchmark 분해

- `KRX1028_FULL`: 두 제외종목을 포함한 공식 KOSPI 200
- `EX2_PRICE_UNIT_SENSITIVITY`: 직전 구성종목을 유지한 채 권리조정 없이 관측 가격 단위를
  잇는 비자기금융 민감도
- `EX2_ISSUER_CAP_VALUE_SENSITIVITY`: 직전 구성종목을 유지한 채 관측 issuer 시가총액 변화를
  잇는 비자기금융 민감도
- `NEUTRAL_CORE`: 같은 trailing20 거래대금 Top50을 각 1.8%, 총 90% 보유하고 현금 10%를
  두는 비모델 대조군. 같은 리밸런싱·체결·비용을 적용한다.
- `EXPOSURE_MATCHED_KRX1028`: 전략의 실제 일별 주식노출만큼 공식지수, 나머지는 현금으로
  둔 비교선

두 EX2 민감도는 reset 당일 종목을 사후 제외하거나 survivor-only로 재가중하지 않는다.
그러나 holder multiplier, cash distribution, successor security와 subscription outflow가
완비되지 않아 canonical return, 자기금융 benchmark, 수익률 상·하한 또는 경제 gate가 아니다.

stable identity와 승인 action terms가 완성된 뒤에만 다음 차이를 경제성과로 보고한다.

- `Phase5R - NEUTRAL_CORE`: 동결 모델 alpha
- `CANONICAL_EX2 - KRX1028_FULL`: 두 대형주 제외효과
- `NEUTRAL_CORE - CANONICAL_EX2`: 비시총가중 core 구성·방어효과
- `Phase5R - KRX1028_FULL`: 전체 기회비용
- `Phase5R - EXPOSURE_MATCHED_KRX1028`: 현금노출을 맞춘 active 성과

현재 release는 `canonical_ex2_return_evaluable=false`이므로 위 다섯 차이와 neutral·exposure
matched 성과를 모두 `NOT_EVALUATED`로 기록한다.

## 8. Predict-only 평가와 금지된 선택

- 2021~2023 전체를 한 번의 chronological consumed-development holdout으로 실행한다.
- Phase 5R에서는 train/validation split, purge, embargo 또는 모델 선택을 새로 수행하지 않는다.
- 모델 Feature percentile에 필요한 횡단면 계산은 신호일 당시 허용 Universe만 사용한다.
- 모델의 Train-time scaler·imputer·calibration은 bundle에서 읽고 다시 적합하지 않는다.
- 날짜별 Top N은 각 날짜 안에서 계산하며 연도 전체 `nlargest(N)`를 금지한다.
- 결과 확인 후 모델, Top50, Top10, 70/20/10, 리밸런싱, 비용, benchmark 또는 gate를
  변경하지 않는다. 변경은 새 Experiment ID·새 승인 대상이며 현재 결과는 그대로 보존한다.

## 9. 무결성 hard gate

- Phase 4E manifest·bundle·canonical tree·component·runtime hash 모두 일치
- Phase 4E fit·label exit 최대일 `2020-12-30` 이하
- Phase 5R `fit`·`fit_transform`·재선택 호출 0건
- Phase 5R 평가 입력 최소일 2021년 첫 KRX 세션, 최대일 `2023-12-28` 이하
- issuer·share class·successor를 연결한 역사적 stable identity contract 완성
- 평가 경로의 모든 corporate action이 네 증거 요건을 충족한 승인 terms 보유
- 관측 price/share 역관계만으로 `READY` action을 생성한 사례 0건
- unresolved action 또는 identity 공백이 있으면 backtest engine 호출 0건
- context 행의 fit·metric·주문 사용 0건
- actual mechanical_reset 후보·membership·identity 경계 교차 유효 성과행 0건
- unresolved CA 후보 파일을 filing timing·block·reset·forced-exit에 사용한 사례 0건
- label availability가 현재 score 행 수를 바꾼 사례 0건
- 미래 bar를 읽어 주문 존재를 결정한 사례 0건
- 제외 security의 Feature inference·점수·주문 0건
- train-time Feature 계약과 inference Feature 이름·순서·dtype 일치
- 성과 평가가 허용된 경우 비용·원장·기간말 청산·benchmark reconciliation PASS
- primary와 reproduction 필수 산출물 byte-identical
- Phase 5R 전용 및 전체 회귀 PASS

CA·identity gate가 실패하면 성과를 계산한 뒤 `INVALID`로 버리는 것이 아니라 engine 전에
중단하고 `REJECT_PHASE5R_UNRESOLVED_CA_AND_IDENTITY_CONTRACT`와 `NOT_EVALUATED`를 남긴다.
그 밖의 hard gate 실패도 경제 지표와 무관하게 승격을 금지한다.

## 10. 소비 개발 경제·방어 gate

다음은 CA·identity preflight를 통과한 경우에만 2021~2023 포트폴리오 동결 후보를 만드는
사전등록 gate이며 최종 Phase 5 통과가 아니다.
Phase 4E에서 `phase4e_model_gate_pass=false`이면 아래 지표는 진단값으로 계산하되 결과와
무관하게 `phase5_gate_pass=false`로 판정한다.

- 기본비용과 2배 비용 모두 `Phase5R - NEUTRAL_CORE > 0`
- 2021·2022·2023 중 최소 2개 연도에서 NEUTRAL_CORE 대비 비음수
- NEUTRAL_CORE 대비 최악 rolling 12개월 `-10%p` 이상
- 전략 MDD `-25%` 이상이며 NEUTRAL_CORE보다 5%p 넘게 악화되지 않음
- canonical EX2 대비 기본비용 연환산 초과수익 `-1%p` 이상
- canonical EX2 대비 downside capture 90% 이하
- 공식 KRX1028 대비 최악 calendar-year 열위 `-15%p` 이상
- 공식 KRX1028 대비 최악 rolling 12개월 열위 `-20%p` 이상
- cash-only보다 높은 절대 순수익
- 평균 주식노출 80% 이상
- 청산거래 30건 이상

모든 연도에서 공식지수를 이길 필요는 없다. 다만 대형주 제외효과를 분리한 뒤에도
동결 모델 alpha가 없거나 공식지수에 극단적으로 뒤처지면 후보로 통과시키지 않는다.
Phase 5R 결과로 Phase 4E primary를 다른 B/C/D 후보로 교체할 수 없다.

현재는 canonical portfolio와 EX2 return이 평가 불가능하므로 위 gate 전부를
`NOT_EVALUATED`로 기록한다. 두 EX2 민감도가 모두 같은 방향이라는 이유로 canonical EX2
gate를 통과 처리하지 않는다.

## 11. 출력

권장 출력 경로:

- `artifacts/v2_phase5r_integrity_soft_fusion/`
- `artifacts/v2_phase5r_integrity_soft_fusion_reproduction/`

최소 출력:

- `scores.csv.gz`
- `official_krx1028_reference.csv`
- `share_reset_candidates.csv`
- `order_intents_blocked.csv`
- `ex2_share_reset_events.csv`
- `ex2_price_unit_sensitivity.csv`
- `ex2_issuer_cap_value_sensitivity.csv`
- `audit.json`
- `decision.json`
- `manifest.json`

무결성 차단 release에는 `strategy_returns.csv`, 비용 stress 수익, neutral·exposure-matched
수익, 체결·포지션 원장 디렉터리를 만들지 않는다. `decision.json`은 모든 canonical 성과와
경제 gate가 `NOT_EVALUATED`임을 명시한다.

Phase 5R manifest는 검증에 사용한 Phase 4E manifest·bundle·canonical tree·component·runtime
hash와 `include_controls=false`를 그대로 기록해 재현 실행에서도 동일성을 확인한다.

현재 결정은 `REJECT_PHASE5R_UNRESOLVED_CA_AND_IDENTITY_CONTRACT`다. 향후 승인 terms와
stable identity를 새 데이터 버전으로 복구한 별도 Experiment만 경제 gate를 실행할 수 있다.

## 12. 금지사항

- Phase 4E bundle 불일치 상태에서 fallback 모델 사용
- 2021~2023에서 model fit·재선택·calibration·threshold 탐색
- B/C/D 대조군의 2021~2023 성과를 보고 primary 교체
- 시총가중 portfolio core 사용
- 삼성전자·SK하이닉스 편입 variant를 선택 후보로 실행
- 관측 price/share 역관계만으로 split·ratio·cash-in-lieu·`READY` action 생성
- 미해결 종목을 reset 당일 제외하거나 사후 재가중해 survivor-only benchmark 생성
- 두 EX2 민감도를 canonical return·수익률 bound·경제 gate로 사용
- 결과를 보고 현금·보유수·비중·리밸런싱·비용·gate 변경
- 2004~2020을 Phase 5R 경제 선택자료로 다시 사용
- protected OOS, 2024년 이후 자료, 외부 주문·실주문·배포

## 13. 구현 파일

- `src/kospi200_phase5r/`: config, physical loader, bundle verifier, predict-only scorer,
  portfolio, benchmarks, audit, CLI
- `configs/v2_phase5r_integrity_soft_fusion.json` (`corporate_action_file` 필수)
- `tests/test_kospi200_phase5r_*.py`
- `artifacts/v2_phase5r_integrity_soft_fusion/`
- `docs/stages/v2_phase_5r_report.md`
- `experiments/registry.csv`
- `docs/DECISION_LOG.md`

Phase 5R `run` 실행 경로의 모델 fit 호출은 0건이어야 한다. 공용 modeling 모듈에 fit API가
있더라도 이 단계는 동결 bundle의 deserialization과 inference만 호출한다.

## 14. 테스트

- 기존 `EXP-20260831-001` 실행 산출물 0건 및 superseded 연결
- Phase 4E manifest·bundle·tree·component·runtime·Feature contract hash 불일치 fail-closed
- v1 component hash는 manifest 키·SHA-256 형식만 검사하고 estimator re-pickle 비교 0건
- manifest/config model-state hash 일치와 exact versions map·data_version·manifest SHA 검증
- Phase 4E fit/label cutoff가 2020-12-30을 넘으면 거부
- monkeypatch로 estimator `fit`·`fit_transform` 호출 0건 검증
- 2021 이전 평가행과 2024 이후 입력 거부
- context-only 행의 metric·주문 유입 0건
- `include_controls=false`와 selected primary 의존 estimator 외 inference 거부
- Phase 4E 모델 gate 실패 시 Phase 5R predict-only 진단은 실행하되 Phase 5 gate false 상속
- 두 제외 security의 score·rank·core·주문 0건
- trailing20 중앙 거래대금 Top50과 ticker tie-break
- 70% core + 20% Top10 + 10% 현금 exact sum
- t 종가 one-sided limit, 상승 gap 미체결, 하락 gap 체결
- 실제 t+1 open이 주문 존재에 영향 0건
- 20% 이상 share 변화는 unresolved candidate만 생성하고 executable action은 0건
- effective-day close·open mutation으로 후보가 `READY`로 승격되는 사례 0건
- 원천 ticker가 정확한 6자리 숫자가 아니면 숫자 추출·zfill로 다른 증권과 충돌시키지 않고
  fail-closed 또는 별도 unresolved identity로 기록
- stable identity 또는 승인 terms 미충족 시 backtest engine·포지션 조정·원장 생성 0건
- reset 당일 종목 제외·사후 재가중 0건
- 두 EX2 민감도의 `self_financing=false`, `canonical_ex2_return_evaluable=false`
- 공식 KRX1028만 원시 비교자료로 보존하고 NEUTRAL_CORE·exposure-matched·경제성과는
  `NOT_EVALUATED`
- primary/reproduction byte determinism
- Phase 5R 전용 및 전체 회귀 PASS

## 15. 실행 명령

Phase 4E bundle 승인·hash 동결과 `EXP-20260901-002` registry 사전등록 이후에만 실행한다.

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_kospi200_phase5r_*.py' -v
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m kospi200_phase5r.cli run --config configs/v2_phase5r_integrity_soft_fusion.json --output artifacts/v2_phase5r_integrity_soft_fusion
.venv\Scripts\python.exe -m kospi200_phase5r.cli run --config configs/v2_phase5r_integrity_soft_fusion.json --output artifacts/v2_phase5r_integrity_soft_fusion_reproduction
```

## 16. 완료 조건

1. Phase 4E selected primary와 bundle hash가 실행 전에 승인·동결돼 있다.
2. Phase 5R에서 fit·재선택이 0건이고 2021~2023 predict-only 실행만 발생한다.
3. 네 증거 요건과 stable identity가 미충족임을 확인한 즉시 engine 전에 fail-closed한다.
4. share-reset candidate·두 EX2 민감도·audit·decision·manifest가 해석 제한과 함께 보존된다.
5. canonical portfolio/EX2 performance와 모든 경제 gate가 `NOT_EVALUATED`로 기록된다.
6. primary와 reproduction의 허용된 감사 산출물이 byte-identical이다.
7. `REJECT_PHASE5R_UNRESOLVED_CA_AND_IDENTITY_CONTRACT`를 registry와 보고서에 보존하며
   모델이나 gate를 사후 변경하지 않는다.
8. protected OOS·2024년 이후 자료·체결·포지션 원장·실제 주문 접근이 모두 0이다.

## 17. Forward 최종 Phase 5 gate

이번 2021~2023 Phase 5R은 통과하지 않았고 포트폴리오 후보도 만들지 못했다. 향후
CA·identity 계약을 복구한 소비 개발 Phase 5R이 통과하더라도 그 결과는 후보일 뿐이다.
최종 Phase 5 통과는
Phase 4E model bundle과 Phase 5R portfolio/config/code/cost hash를 새 forward 자료 도착 전에
다시 동결한 별도 Experiment에서만 판단한다.

- 최소 126거래일·30건 청산 전에는 판정하지 않고 `PROVISIONAL`만 허용
- 최종 판정은 최소 252거래일·30건 청산 필요
- 모든 무결성 hard gate와 기본·2배 비용 경제·방어 gate 충족 필요
- forward 결과를 본 뒤 재적합, primary 교체, threshold·비중·두 제외종목 변경 시 해당
  forward 증거 무효
- 권위 있는 법령 근거의 2026 비용표를 별도 승인·동결하기 전 forward portfolio 실행 금지

기존 2024~2025 봉인 OOS는 계속 접근하지 않으며 v2 최종 증거로 전용하지 않는다.

## Codex Handoff

다음 구현은 issuer·share class·successor를 연결하는 stable identity map과 네 증거 요건을
모두 갖춘 승인 corporate-action terms ledger부터 시작한다. holder multiplier, cash
distribution, successor value, subscription outflow를 표현하는 self-financing 회계와
unresolved-event preflight를 별도 데이터 버전·새 Experiment ID로 등록한다. 이 계약과
전용·전체 회귀가 모두 통과하기 전에는 backtest engine·원장·경제 gate를 실행하지 않는다.
superseded Phase 4E bundle은 재사용하지 않는다. DEC-105 새 Experiment에서 보수적 경계로
재학습·동결한 모델만 사용할 수 있다. 70/20/10 비중·제외 두 종목·비용·gate는 이번 결과에
맞춰 변경하지 않으며, protected OOS와 실제 주문은 계속 금지한다.
