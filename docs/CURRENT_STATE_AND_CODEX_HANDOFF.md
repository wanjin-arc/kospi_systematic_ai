# 현재 상태 및 Codex 인계

**갱신일:** 2026-09-01
**목적:** 검증 완료 범위와 다음 승인 경계를 추측 없이 이어받기 위한 문서

## 최신 결론 — v2 Phase 4F·Phase 5S

`EXP-20260901-003` Phase 4F는 DEC-105에 따라 기존 Phase 4E를 덮어쓰지 않고 새 코드·config·
artifact로 재실행했다. 같은 exact raw 6자리 ticker의 연속 거래소 세션에서
`abs(log(current listed_shares / prior listed_shares)) >= log(1.20)`인 사건 554건을 가격과
무관한 candidate로 표시했다. 결측·무한·0·음수 상장주식수는 별도 observation gap으로
fail-closed하도록 구현했으며 실제 2020년 이하 모델 모집단의 gap은 0건이었다. candidate/gap은
기술 Feature segment를 끊고 signal~exit 라벨을 무효화한다. 유효 라벨 중 경계 통과 행은 0이다.

모델 전용 OOF 재학습에서 `C_ONLY`가 선택됐다. 평균 Rank IC는 0.017810, 2019년 -0.011576,
2020년 0.047196으로 2년 중 1년만 비음수다. 사전등록 model gate는 통과했지만 매년 안정적이지
않으므로 독립 OOS·거래 승격 근거가 아니다. score panel 789,876행, sampled signal 23,722행,
최종 fit 23,190행이다. model-state hash는
`b558ecbfba2fd5022cb12f10c5df2499559642e4f5b4f1e9f781c223e7a41e4f`, bundle hash는
`47f10289d6c25ab7dbcb73d6429dbef0208b872d6ca0d12f770827cb23fa9792`이며
primary/reproduction 11개 파일이 byte-identical하다. 포트폴리오·주문·2021+ fit·OOS 접근은 0이다.

`EXP-20260901-004` Phase 5S는 이 bundle의 `C_ONLY`만 `include_controls=false`로 2021~2023
소비 개발자료에 predict했다. 점수 141,782행, strategy/neutral 각 1,800건을 합한 차단 주문
의도 3,600건을 생성했다. 로더 후보는 86건, 전일·당일 실제 member 후보는 37건, 원천 exact
ticker 후보는 223건이었다. stable identity, 승인 corporate-action terms와 canonical EX2가
불완전해 결정은 `REJECT_PHASE5S_UNRESOLVED_CA_AND_IDENTITY_CONTRACT`다. fit·engine·성과
metric·executable action·외부 주문·OOS 접근은 모두 0이며 10개 산출물이 재현본과
byte-identical하다. 따라서 70/20/10은 차단된 주문 의도 구조일 뿐 성과가 아니다.

다음 허용 작업은 역사적 issuer·share class·successor identity와 원문 권리조건·효력 거래세션·
KRX 동일배율 검증을 갖춘 승인 action terms ledger를 새 데이터 버전과 Experiment로
사전등록하는 것이다. 그 전에는 Phase 5 backtest engine·원장·경제 gate를 실행하거나 2021~2023
결과를 보고 비중·threshold·비용을 조정하지 않는다. 독립 성과 증거는 동결 뒤 새 forward
shadow에서만 쌓고 protected OOS는 계속 봉인한다.

상세 근거는 `docs/stages/v2_phase_4f_report.md`, `docs/stages/v2_phase_5s_report.md`,
`docs/DECISION_LOG.md`의 DEC-105·DEC-106을 따른다.

## 철회 이력 — v2 Phase 4E·Phase 5R

`EXP-20260901-001` Phase 4E는 2020-12-30 이하 물리 입력에서 AI 모델을 먼저 만드는
model-only 단계로 실행됐으나 DEC-105 후속 감사로 동결 판정을 철회했다. 당시
`C_ONLY` HistGradientBoosting이 평균 Rank IC 0.027545,
2019년 0.014653, 2020년 0.040437로 선택됐다. D soft fusion의 평균 IC 0.026551은 C를
엄격히 개선하지 못했다. fit 23,567행, Selection OOF 4,876행이며 primary/reproduction
필수 파일 11/11이 byte-identical이다. bundle SHA-256은
`da9b8111c3c9c59126746075bc019a5218d33c0259a1c22d0eea00ea3cd3c550`다.
포트폴리오·주문·2021년 이후 fit·protected OOS 접근은 모두 0이다.
추가 2004~2020 원천 감사에서 membership 841,657행의 비정규 ticker는 0행이었고, 시장 원천의
전역 normalization collision 4개 중 Phase 4E membership과 교차한 것은 0개였다. 따라서 이
특정 정규화 충돌이 C_ONLY에 유입됐다는 증거는 없다.

그러나 별도 라벨 경계 감사에서 전체 거래소 원천 exact ticker 후보 4,391건 중 로더의
ever-member·두 종목 제외 모집단 554건, 전일·당일 실제 구성종목 후보 247건을 찾았다.
두 종목 제외 전 양일 구성 후보는 248건이며 차이는 삼성전자 2018-05-04 액면분할 1건이다.
기존 OOF 4,876행 중 11행의 20세션 창이 후보를
가로질렀고, 그중 기존 유효 라벨 10행은 모두 비기계적 후보이자 2019~2020 선택 표본이었다.
최종 fit 유효 23,567행 중에는 75개 고유 비기계적 후보를 가로지른 행이 83개였다.
따라서 기존 Phase 4E는 `SUPERSEDED_PHASE4E_LABEL_INTEGRITY`, 이를 입력으로 쓴 Phase 5R은
`SUPERSEDED_PHASE5R_INVALID_PHASE4E_SOURCE`다. 기존 bundle·점수·주문 의도는 재사용하지 않는다.

후속 `EXP-20260901-002` Phase 5R은 2021~2023 predict-only 성과 평가 전에 데이터 회계
무결성에서 중단됐다. 첫 시도는 카카오 `035720`, 두 번째 시도는 아시아나항공 `020560`의
share-reset/EX2 계약에서 멈췄으며, 결과 파일에 기록된 포트폴리오 성과·경제 gate는 없다.
관측 상장주식 수와 가격의 역관계만으로 `READY` action을 만든 DEC-103은 권위 raw audit의
네 증거 요건과 충돌하므로 DEC-104가 유효 성과·경제 산출 전에 supersede한다.

현재 결정은 `REJECT_PHASE5R_UNRESOLVED_CA_AND_IDENTITY_CONTRACT`다. stable identity와
승인 corporate-action terms가 없으므로 canonical 포트폴리오·EX2 return, neutral core alpha,
공식 KRX1028 대비 방어력, MDD와 비용 stress를 모두 `NOT_EVALUATED`로 기록한다.
`EX2_PRICE_UNIT_SENSITIVITY`와 `EX2_ISSUER_CAP_VALUE_SENSITIVITY`는 비자기금융 진단이며
canonical return·상하한·경제 gate로 사용하지 않는다.

최종 무결성 감사는 C_ONLY 점수 143,323행과 차단 주문 의도 3,600건을 생성했다. 원천
share-reset 후보 223건 중 전일·당일 실제 구성종목 사건은 37건이며 ticker normalization
collision은 전역 4개, 실제 membership 교차 0개다. engine·성과 metric·실행 action·외부
주문은 0건이고 primary/reproduction 10개 파일은 byte-identical하다.

다음 허용 작업은 먼저 새 Experiment ID에서 DEC-105 candidate-only 라벨 경계와 기술 Feature
reset으로 Phase 4 모델을 전체 재학습·재선택하는 것이다. 그 다음 PIT issuer·share class·
successor stable identity map과 원문 권리비율·효력 거래세션·KRX 동일배율 교차검증을 갖춘
action terms ledger를 설계한다. 새 데이터 버전과 Experiment를 사전등록하기 전에는 Phase 5
backtest engine·원장·경제 gate를 실행하지 않는다. superseded Phase 4E bundle은 재사용하지
않고, 70/20/10 비중·비용·gate는 2021~2023 결과에 맞춰 바꾸지 않으며 protected OOS는 봉인한다.

상세 근거는 `docs/stages/v2_phase_4e_report.md`, `docs/stages/v2_phase_5r_report.md`,
`docs/DECISION_LOG.md`의 DEC-104·DEC-105를 따른다. 아래 내용은 이전 연구선의 역사 기록으로 보존한다.

## 결론

Phase 0~4는 완료다. 기존 Phase 5 `EXP-20260822-001`의 결과는 그대로 보존되어 있다. 사용자 승인에 따라 별도 Phase 4B `EXP-20260823-001`과 Phase 5B `EXP-20260823-002`를 실행했으며, Development Test는 로드·계산·평가·선택 모두 0행이다.

Phase 5G `EXP-20260823-007`은 2019년 이후 구간을 재사용하지 않고 2018년 이하 물리 파티션에서만 수행한 다중 기간 내부 진단이다. 21개 종목 변수·5개 시장 변수·6개 상호작용으로 5·10·20거래일 비용 차감 초과수익을 동시에 예측했다. 연결 순초과수익률 -3.6598%p, 2배 비용 -6.9593%p, 연도별 gate 2/4로 기각됐다. 평균 현금 83.60%, 평균 보유 1.77개이며 최소 보유·평균 현금 hard gate는 사용하지 않았다. 2019년 이후·Development Test·Final OOS 접근은 모두 0이다.

Selection 후보는 `tree_d3_l002`다. 입력은 `reversal_5` 하나이며, 깊이 3·최소 leaf 2%인 얕은 의사결정나무다. 이는 별도 승인 후 단 한 번 공개할 Development Test 후보일 뿐 거래 후보가 아니다.

새 Phase 5B는 21개 종목변수·5개 시장상태·6개 상호작용을 사용해 매일 종목별 점수와 횡단면 순위를 만들었다. `elastic_a005_l02`가 진단상 최선이었으나 연결 순초과수익률 -11.5013%p, 연도 gate 2/4로 전 후보가 기각됐다. 이 모델은 거래 후보나 Development Test 후보가 아니다.

Phase 5C `EXP-20260823-003`은 이 신호를 고정하고 causal EMA5·상위 10 목표/20위 fallback·20위 이탈·20세션 안전 상한을 적응적으로 진단했다. 연결 순초과수익률은 -1.0274%p로 개선됐지만 turnover 감소 33.87%와 평균 현금 17.61%가 사전등록 gate를 실패했다. Phase 5C 정책도 거래 후보나 Development Test 후보가 아니다.

Phase 5D `EXP-20260823-004`는 사용자 승인에 따라 평균 현금·최소 보유 gate를 제거하고 시장상태별 최대 보유를 risk-on 10, neutral 5, risk-off 0으로 바꿨다. 이미 소비된 2019~2021 재사용 진단에서 평균 보유 4.159개·평균 현금 63.34%로 가변 운용은 작동했지만 전략 -37.65%, 지수 +50.40%, 순초과 -88.05%p로 실패했다. 거래·Development Test 후보는 없다.

Phase 5E `EXP-20260823-005`는 비용 차감 절대 초과수익 Ridge와 그 값이 양수일 확률 Logistic을 고정하고 예상 순초과수익 0.5%·확률 60%를 모두 통과한 종목만 거래했다. 2019~2021 adaptive diagnostic에서 전략 +29.31%, 지수 +50.40%, 순초과 -21.09%p였다. 평균 현금 96.00%, 평균 보유 0.423개로 no-trade는 작동했지만 절대 알파 예측과 지수 초과 gate를 실패했다. 거래·Development Test 후보는 없다.

Phase 5F `EXP-20260823-006`은 논문의 시계열·병렬 입력·이상탐지 아이디어를 저장소 규칙 안에서 재구성했다. 8개 종목 기술변수의 5·20세션 경로와 5개 시장변수 경로를 평균·중앙값 HistGradientBoosting에 입력하고 Train-only IsolationForest 이상상태에서 신규매수를 보류했다. 전략 -7.83%, 지수 +50.40%, 순초과 -58.23%p, 연도 gate 0/3으로 실패했다. 거래·Development Test 후보는 없다.

## 검증 상태

- 전체 회귀 테스트: 118/118 PASS
- Phase 5G 전용 테스트: 10/10 PASS
- Phase 5F 전용 테스트: 13/13 PASS
- Phase 5E 전용 테스트: 9/9 PASS
- Phase 5C 전용 테스트: 7/7 PASS
- Phase 5D 전용 테스트: 7/7 PASS
- Phase 4B/5B 신규 테스트: 10/10 PASS
- Phase 5 전용 테스트: 12/12 PASS
- 기존 Phase 5 Selection과 독립 재실행의 구조화 산출물 8개: byte-identical
- Phase 4B 구조화 산출물 6개와 Phase 5B 구조화 산출물 11개: 각각 byte-identical
- Phase 4B/5B 입력 역할: `phase4b_train_internal`
- Phase 4B/5B 최대 로드일: 2018-12-28
- Phase 4B/5B 최대 연구 신호일: 2018-12-12
- Phase 4B/5B의 2019~2021 로드·계산·평가·선택: 모두 0행
- Phase 5C의 2018년 이후 로드·계산·평가·선택: 모두 0행
- 로드 후 날짜 필터: 없음
- Development Test 입력·계산·평가·선택: 모두 0행
- Final OOS 접근: 없음
- Phase 5E 독립 재실행 구조화 산출물 10개: byte-identical
- Phase 5F 독립 재실행 구조화 산출물 11개: byte-identical

## Phase 5 Selection 결과

- Experiment ID: `EXP-20260822-001`
- 후보: Raw Rank 1개, OLS 1개, shallow tree 6개
- 선택 후보: `tree_d3_l002`
- 선택 모델 hash: `822ebea85b8c9745e3bfa5718d48ba0a383b5017298542a91184cc2e0bf54923`
- 2019~2021 연결 Validation 기본비용 수익률: 7.9429%
- 같은 기간 지수 수익률: 50.3994%
- 순초과수익률: -42.4565%p
- Sharpe: 0.2275
- 최대낙폭: -41.3658%
- Phase 3 대비 Sharpe 개선: +0.3281
- 연도별 순초과수익률 0 이상 fold: 0/3

Selection 우선순위상 tree 후보가 Raw Rank·OLS보다 높았지만, 사전등록 D20의 연도별 Validation 순초과수익률 조건은 이미 실패했다. Development Test 결과를 보더라도 모든 gate를 동시에 통과할 수 없으므로 모델 채택 가능성은 없다. 다만 명세상 단일 Development Test 공개를 수행할지는 사용자 별도 결정으로 남긴다.

## 동결 hash

- source: `1600bcd361ce90e0a7f56500fd1d74393e8123ca851f002f438f7a60e158c240`
- config: `e3ea32fa995e3302539b8a28ed7193c7e7ccb1cc2af7dea76d6dc3ba6ef1fb21`
- Selection data: `d4b817519bc7b9956b26bbc8e099356a0b1b3cb4e402674b59e93a1525162417`
- 후보 모델군: `e45ee94e6f798c9e5be4fda944c779a5889ef0ce28d03213b2a6fa05fc01bd87`
- dependency: `2e343fa4ec97652567f2231f4878c130d33f357ca2509f257ac4c87e6cde9b83`
- Selection manifest 파일 hash: `67adeabdd7178126e28b8d17972ea254e72598660853a05889eb8b37539ac5e3`

## 구현 및 산출물

- 설정: `configs/phase5_ranking.json`
- 물리 파티션 빌더: `kospi100_data.phase5_partition`
- Selection CLI: `python -m kospi100_ranking.cli select --config configs/phase5_ranking.json --output artifacts/phase5/selection`
- 코드: `src/kospi100_ranking/`
- 구조화 결과: `artifacts/phase5/selection/`
- 명세·보고서: `docs/stages/phase_5_spec.md`, `docs/stages/phase_5_report.md`

## Phase 4B/5B 구현 및 산출물

- 설정: `configs/phase4b_multifactor.json`, `configs/phase5b_multifactor_ranking.json`
- 물리 파티션 빌더: `kospi100_data.phase4b_partition`
- CLI: `python -m kospi100_multifactor.cli analyze|select`
- 코드: `src/kospi100_multifactor/`
- 구조화 결과: `artifacts/phase4b_multifactor/`, `artifacts/phase5b/selection/`
- 명세·보고서: `docs/stages/phase_4b_spec.md`, `phase_4b_report.md`, `phase_5b_spec.md`, `phase_5b_report.md`

## Phase 5E 구현 및 산출물

- 설정: `configs/phase5e_absolute_alpha.json`
- CLI: `python -m kospi100_absolute_alpha.cli freeze|run`
- 코드: `src/kospi100_absolute_alpha/`
- 구조화 결과: `artifacts/phase5e/adaptive_diagnostic/`
- 명세·보고서: `docs/stages/phase_5e_spec.md`, `docs/stages/phase_5e_report.md`

## 다음 승인 경계

1. Development Test는 사용자 별도 승인 전 실행하지 않는다.
2. Phase 5B는 Validation gate 실패로 종료됐으므로 진단 모델을 Development Test에 공개하지 않는다.
3. turnover·현금·순위 지속성 규칙을 연구하려면 별도 Experiment와 새 검증 설계를 결과 확인 전에 등록한다.
4. 기존 Phase 5 Development Test를 승인하더라도 동결된 `tree_d3_l002` 한 개만 한 번 평가한다.
5. 결과를 본 뒤 동일 Experiment의 Feature, 모델, fold, 비용, 포트폴리오, gate를 변경하지 않는다.
6. Final OOS는 계속 봉인한다.
7. Phase 6 명세·실행을 시작하지 않는다.
8. Phase 5C 결과를 보고 같은 2015~2018에서 EMA·순위 band·현금 규칙을 다시 조정하지 않는다.
9. D20의 연도 80% 조건 변경은 `DEC-2026-047` 제안 상태이며 사용자 명시적 승인 전 적용하지 않는다.
10. 2019~2021은 Phase 5D에서 재사용 진단으로 명시적으로 소비됐다. 이후 Test/OOS 또는 새 선택 구간으로 부르지 않는다.
11. 평균 현금과 최소 보유 수는 hard gate가 아니지만, 이 변경만으로 종목 점수의 예측력 부족은 해결되지 않았다.
12. Phase 5E는 절대 순초과수익·양수 확률 no-trade 구조를 구현했지만 2019~2021 지수 초과에 실패했다. 같은 구간에서 target threshold나 모델 parameter를 다시 조정하지 않는다.

## Codex Handoff

- 현재 허용 작업: Phase 5G 산출물·manifest·테스트 감사와 문서 검토.
- 사용자 결정을 기다릴 작업: 2008년 이전 KOSPI 100 또는 외부 시장의 새 물리 데이터 업로드와 품질 감사.
- 금지 작업: 같은 2015~2018 결과 기반 threshold·모델·Feature 재튜닝, 2019~2021 재사용, Development Test 선행 접근, 동일 Experiment 후보 재선택, Phase 6 시작, Final OOS 접근, 실거래·배포.

## 2026-08-25 Phase 1C·Phase 5I 갱신

- Phase 1C: 2004~2009 KRX 원천자료와 기존 2010~2018 자료를 별도 물리 파티션으로 결합했다. 2000~2003은 제외했고 기존 Phase 입력과 결과는 변경하지 않았다.
- Phase 5I: 2004~2010 학습 173,390행을 실제 포함한 2011~2018 8-fold adaptive diagnostic을 완료했다.
- 결과: 기본 비용 순초과수익률 -26.50%p, 2배 비용 -44.27%p, 연도별 2/8로 `EXP-20260825-004`를 기각했다.
- 점수 관계: 모델은 `reversal_5`에 주로 양의 방향, 20일 추세·모멘텀에 음의 방향이었으나 미래 10거래일 수익 순위와의 관계는 매우 약했다.
- 데이터 경계: 최소 2004-01-02, 최대 2018-12-28, 2019년 이후 및 Development Test 로드 0, Final OOS 접근 없음.
- 검증: 전체 151/151 PASS, 독립 재생성 데이터 7개와 Phase 5I 산출물 9개가 각각 byte-identical이다.
- 현재 허용 상태: Phase 5I 보고서·manifest 감사와 새로운 독립 연구 설계 검토.
- 현재 금지 상태: Phase 5I를 거래 또는 Development Test 후보로 승격, 같은 2011~2018 결과를 이용한 재튜닝, Development Test 또는 Final OOS 접근.

## 2026-08-25 v2 KOSPI 200·펀더멘탈 전환

- v1 KOSPI 100 Phase 0~5I는 종료된 legacy 연구선이다. 코드·registry·실패 결과는 재현용으로 보존한다.
- v2 Universe는 동시점 실제 KOSPI 200이며, 확정 재무제표 수치 Agent B와 OHLCV 전용 Agent C를 분리한다.
- KRX 2004~2023 구성종목과 OpenDART 2015~2023 재무제표를 실제 수집·감사했다. receipt-date 다음 KRX 세션 보정, 역사적 identity 동결, 표준 XBRL taxonomy, 일별 20개 Factor 패널을 실제 생성했다.
- identity는 이력 ticker 444개 중 354개를 자동 확정했고 90개는 명칭 불일치로 fail-closed 제외했다. Factor 패널은 2016-03-24~2023-12-28, 264,341행, 248개 ticker다.
- Fundamental Agent B는 `EXP-20260826-001`로 사전등록·실행했다. 시가총액 상위 200 안에서 최신 확정 재무상태와 희석도를 반영해 일별 Top 30을 생성하며 `ridge_a10`이 선택됐다. 평균 Rank IC 0.0360, NDCG@30 0.5616, 연도별 양수 IC 4/6으로 진단 후보일 뿐 거래 승격은 아니다.
- Agent C의 CNN/LSTM과 포트폴리오 백테스트는 실행하지 않았다.
- 이후 `EXP-20260826-002`에서 Agent B Top 30 안의 14개 causal OHLCV로 linear dual과 shallow hist dual을 실행했다. 평균 Rank IC는 각각 -0.0083, -0.0072로 둘 다 기각했고 포트폴리오 백테스트는 실행하지 않았다.
- `EXP-20260826-003`에서는 Agent B gate를 제거하고 전체 PIT KOSPI 200 OHLCV를 독립 평가했다. `hist_event_dual` 평균 Rank IC 0.0347, bottom AUC 0.6359, 연도 IC 5/5 양수로 Agent D 입력 후보가 됐다. Agent B와 점수 상관은 -0.0523이며 포트폴리오·LSTM/CNN은 아직 실행하지 않았다.
- 2004~2023은 consumed development이고 독립 평가로 재사용하지 않는다. 2024~2025 v1 Final OOS는 계속 봉인한다.
- 다음 허용 작업: Agent B와 독립 Agent C를 결합하는 Agent D의 고정 가중 후보·no-trade·gap veto·비중·청산 규칙 사전등록.
- 다음 금지 작업: 결과를 보고 Agent B/C 점수 가중치를 임의 선택, 직렬 Agent C 승격, 딥러닝 미실행 결과를 LSTM/CNN 결과로 표현, 과거 실패 registry 삭제, 2004~2023을 새 OOS로 명명, 2024~2025 봉인자료 접근, 실주문·배포.
## 2026-08-26 v2 Agent D 결과

- `EXP-20260826-004`를 실행해 Agent C 단독과 Agent B 순위 25·50·75% 결합을 비교했다.
- 진단상 최선은 `C100`으로 총수익률 8.49%, PIT KOSPI200 시총가중 proxy 30.57%, 순초과수익률 -22.07%p, Sharpe 0.183, MDD -31.98%, 양의 연도 1/5였다.
- B 25% 결합부터 순초과수익률이 -34.95%p로 악화했으며 네 후보 모두 승격 gate를 실패했다.
- 본 실행과 독립 재실행의 16개 파일이 모두 byte-identical이고 reconciliation은 모든 후보가 통과했다.
- v1 Development Test 물리 파티션과 Final OOS는 접근하지 않았다. 2019~2023은 이미 소비된 v2 개발 진단이다.
- 다음 허용 후보: 새 Experiment ID로 Agent B의 target·시간축·점수 calibration을 재설계하는 명세 작성.
- 다음 금지 작업: 동일 기간에서 B/C 가중치 미세탐색, Agent D 거래 승격, 기존 B 결과 소급 변경, 봉인 OOS 접근.
## 2026-08-26 Agent B2·C2 재설계

- 공식 KRX KOSPI200 지수코드 1028, 2004-01-02~2023-12-28, 4,945행을 `data/incoming/v2_kospi200_index_raw/`에 byte-identical로 동결했다.
- Agent B2 `EXP-20260826-005`: 공식지수 63세션 초과수익-0.5×MAE target의 `ridge_quality`가 평균 IC 0.03284였으나 양의 연도 3/5로 약했다. 전체 점수와 Top80 flag만 후속 진단 입력으로 보존한다.
- Agent C2 `EXP-20260826-006`: 2004년부터의 이력과 공식지수 causal Feature를 사용했다. 기존 `hist_event_dual_v1`이 평균 공식지수 초과수익 Rank IC 0.04184, 양의 연도 5/5로 신규 직접 excess 모델보다 우수했다.
- B2·C2 모두 포트폴리오 백테스트와 독립 OOS 승격은 하지 않았다. 본 실행과 독립 재실행은 각각 6개 파일 byte-identical이다.
- 다음 허용 작업: 새 Experiment ID로 Agent D2를 사전등록하고 B2를 hard gate가 아닌 C2 진입 위험 calibration으로 제한해 평가한다.
- 다음 금지 작업: 같은 2019~2023에서 B penalty·Top80·C 모델 깊이·비용을 재탐색하거나 v1 봉인 OOS에 접근하는 작업.

## 2026-08-26 Agent D2 이중 결합 결과

- `EXP-20260826-007`에서 C2 단독, B2 Top80 선필터→C2, C2 전체 유지+B2 위험보정을 공식 KRX KOSPI200 지수로 비교했다.
- 위험보정이 최선으로 전략 +6.40%, 지수 +38.63%, 순초과 -32.24%p, Sharpe 0.202, MDD -22.03%, 양의 연도 2/5였다.
- Top80 직렬은 순초과 -49.28%p, C2 단독은 -66.44%p였다. B2는 위험을 줄였지만 공식 지수 초과수익을 만들지는 못했다.
- 세 후보 reconciliation은 모두 PASS이며 본 실행과 독립 재실행의 16개 파일이 모두 byte-identical이다.
- D2 전용 6/6, B2/C2/D2 관련 12/12, 전체 213/213 테스트가 통과했다.
- 2019~2023은 소비된 v2 개발 진단이다. v1 Development Test 물리 파티션과 Final OOS는 접근하지 않았다.
- 다음 허용 작업: 새로운 forward paper/shadow 평가 경계를 먼저 정한 후 별도 Experiment를 설계한다.
- 다음 금지 작업: 같은 기간에서 Top N·보정계수·C2 threshold·손절익절 재튜닝, D2 거래 승격, 봉인 OOS 접근, 실주문·배포.

## 2026-08-26 실제 LSTM·CNN Agent C3와 D3

- `EXP-20260826-008`: PyTorch 2.13.0 실제 LSTM이 10세션 변동성을, 실제 1D CNN이 t+1 시가 기준 +10%가 -5%보다 먼저 도달할 확률을 예측했다.
- C3는 공식지수 초과수익 Rank IC 0.04776, 2:1 AUC 0.66410, 양의 연도 5/5로 C2보다 개선됐다. Train-only 선택 위험가중치는 0.5다.
- `EXP-20260826-009`: C3 점수 0.05/0.075를 5%/11% 비중에 그대로 대응했다. 점수의 95.53%/90.90%가 각 임계값을 넘어 상시투자와 과도한 turnover가 발생했다.
- B2 위험보정 최선도 전략 -16.28%, 공식지수 +38.63%, 순초과 -54.91%p, MDD -41.57%, turnover 292.06배로 기각됐다.
- C3·D3 전용 10/10, 전체 223/223 PASS. C3 6개·D3 16개 독립 재실행 산출물은 모두 byte-identical이다.
- 결론: 실제 LSTM/CNN은 예측 진단을 개선했지만 다른 점수척도의 절대 임계값을 그대로 이전한 매매정책은 실패했다.
- 다음 허용 작업: 새 forward 기간에서 점수 확률 calibration과 순위 기반 비중을 결과 확인 전에 동결하거나, PIT 분봉 수집 후 별도 entry-timing 실험 설계.
- 다음 금지 작업: 같은 2019~2023에서 0.05/0.075·후보 수·보유·손익비 재튜닝, D3 거래 승격, 봉인 OOS 접근, 실주문·배포.
## 2026-08-26 v2 Agent C4/D4 추가 진단

- C4는 LSTM·CNN 공동 표현으로 10거래일 비용 차감 공식지수 초과수익과 양수 여부를 직접 학습했으나 평균 Rank IC 0.0119, AUC 0.5032로 약했다.
- D4는 양의 예상 초과수익·상위 5개·5세션 재조정·10세션 기간청산 구조로 D3의 과매매를 줄였지만 최선 순초과수익률 -55.09%p로 기각됐다.
- C4/D4 모두 독립 재실행 byte determinism과 전체 229개 테스트를 통과했다.
- 2019~2023은 소비된 개발기간이며 Final OOS는 접근하지 않았다. 다음 유효 검증은 동결 이후 forward 자료에서 수행한다.

## 2026-08-26 v2 Agent D5 관계 확률 결합

- `EXP-20260826-012`는 B2 펀더멘털 품질, C3 LSTM·CNN 점수와 B×C 등 5개 관계항을 얕은 확률 모델로 결합했다.
- 2019년 관계 적합, 2020년 B/C 비중·확률·순위 임계값 선택, 2019~2020 재적합 후 2021~2023 소비 개발 진단을 한 번 수행했다.
- 2020년 24개 선택 정책이 모두 주문 0건이었고, 2021~2023도 예측확률 최대 0.4064로 사전등록 최소 0.50을 넘지 못해 주문 0건이었다.
- 관계 AUC 0.6214, 전략 0%, 공식 KOSPI200 -12.79%로 표시상 +12.79%p였지만 이는 평균 현금 100%의 효과이므로 알파가 아니다.
- 본 실행과 독립 재실행의 19개 파일은 모두 byte-identical이고 Final OOS 접근은 없었다.
- Agent D5 전용 3/3과 전체 회귀 239/239 테스트가 통과했다.
- 2011~2014 구형 DART 원문은 구조 분류만 완료됐으며 수치계정·identity·PIT 감사가 끝나지 않아 모델 사용 0행이다.
- 다음 허용 작업은 동결 정책의 2026-08-26 이후 forward shadow 설계다. 같은 2020~2023에서 임계값·가중치·모델을 다시 맞추는 작업은 금지한다.

## 2026-08-26 v2 Legacy DART 2011~2014 수치 후보 감사

- 2,451개 감사 문서와 2,437개 ZIP 원문(다중 XML ZIP 571개)을 실제 파싱했다.
- 정정본·접수일 다음 KRX 세션·PIT identity를 함께 기록해 123,840개 수치 후보와 9,602개 최신 비모호 후보를 별도 processed 경로에 작성했다.
- 사용자 승인에 따라 2011년 1분기 이후·확정 identity·CFS 범위·확인 단위·최신 정정본만 허용해 strict legacy canonical 330행을 만들고, 기존 표준 XBRL 93,910행과 별도 파생 경로에서 병합했다.
- 병합 factor panel은 296,861행이지만 2011~2014는 37 ticker, 23,000행이며 핵심 Factor coverage가 0~25%로 낮다. 따라서 이 병합본은 후보 패널로 보존하고 Agent B 학습에는 사용하지 않는다. 기존 2016~2023 패널과 Agent B 결과는 변경하지 않았다.
- 상세 근거·해시·재현 명령은 `docs/KOSPI200_LEGACY_DART_MERGE_AUDIT_KO.md`에 있다.

## 2026-08-26 v2 Phase 6 미래 Shadow 준비

- `EXP-20260826-013`으로 B XGBRanker, C 실제 LSTM·CNN, D B Top30→C 직렬 실행 구조를 사전등록할 설계 계약을 작성했다.
- `configs/v2_phase6_forward_shadow.json`은 모델·가중치 hash가 아직 `TRAINING_PENDING`인 준비 상태다.
- `src/kospi200_forward_release/`는 미래 시작일, Protected OOS, 실계좌·네트워크·주문, 설정 내 secret, t+1 주문 시점을 fail-closed로 검사한다.
- 현재 KIS API 호출·모의주문·실주문은 0건이며, shadow 주문 의도도 모델 hash 동결 전에는 생성할 수 없다.
- 다음 허용 작업: XGBoost 정확한 버전 동결, B 최종 학습기와 D Train-only nested 선택기 구현, C 최종 재학습, source/config/data/model hash 동결.
- 다음 금지 작업: 2004~2023을 새 Test/OOS로 표현, 같은 기간 성과를 보고 임계값 재선택, v1 2024~2025 봉인자료 접근, KIS 주문·배포.

## 2026-08-26 Agent B3 XGBRanker 실행

- `EXP-20260826-014`를 표준 2016~2023 Factor 패널로 실행했다. XGBoost 3.4.1, `rank:ndcg`, 날짜별 query group, 63세션 purge/embargo를 사용했다.
- 평균 Rank IC 약 -0.00253, 양의 연도 1/5로 기존 Ridge B2보다 낮아 대체 모델로 기각했다.
- `artifacts/v2_phase6_agent_b_xgbranker/`에 fold·daily score·audit·manifest를 보존했다.
- B3는 Agent D나 미래 shadow에 연결하지 않는다. 기존 B2 판정은 불변이다.
