# KOSPI 200 Fundamental+Technical Systematic AI — Codex 작업 규칙

이 저장소는 기존 KOSPI 100 Technical v1 기록과 새 KOSPI 200 Fundamental+Technical v2를 함께 보존한다. ChatGPT Work가 연구·분석·의사결정 명세를 만들고, Codex가 코드 구현·테스트·리팩터링·자동화를 수행한다. 모든 보고서와 새 문서는 한글로 작성한다. 상세한 연구·운영 원칙의 원문은 `docs/PROJECT_MASTER_PROMPT_KO.md`를 따른다.

## 작업 시작 순서

1. `AGENTS.md`
2. `docs/PROJECT_MASTER_PROMPT_KO.md`
3. `docs/PROJECT_SPECIFICATION_KO.md`
4. `docs/CURRENT_STATE_AND_CODEX_HANDOFF.md`
5. `docs/RESEARCH_PROTOCOL.md`와 `docs/BIAS_PREVENTION_CHECKLIST.md`
6. 현재 단계 명세와 `experiments/registry.csv`
7. 관련 코드·설정·테스트

문서와 코드가 충돌하면 실제 구현을 추측하지 말고 충돌을 보고한다. 연구 규칙 변경은 `docs/DECISION_LOG.md` 기록과 사용자 승인이 모두 있어야 한다.

## 절대 제약

- v2 Universe는 과거 시점별 실제 KOSPI 200 구성종목이다. 기존 KOSPI 100은 v1 재현 전용이다.
- Long-only 현금 주식만 사용하며 공매도·레버리지·파생상품은 금지한다.
- Technical Factor는 OHLCV, 거래대금, KOSPI 200 지수, 동시점 Universe Breadth 및 그 기술적 파생변수로 제한한다.
- Fundamental Factor는 확정 재무제표의 수치 계정과 동시점 시가총액으로 계산한 사전등록 비율만 허용한다. 결산일이 아니라 실제 DART 접수일 다음 거래일부터 사용한다.
- DART 공시 텍스트, 뉴스, 가이던스, 목표주가, 애널리스트 의견, 업종 전망, 기업별 임베딩은 Factor로 사용하지 않는다.
- Corporate Action, 거래정지, 코드 변경, 거래일·거래시간은 정합성과 체결 검증에만 쓴다.
- 일봉 신호는 `t`일 장 종료 뒤 계산하고 주문은 `t+1` 이후에만 가능하다.
- 분봉은 봉이 완전히 끝난 뒤에만 사용한다. 같은 봉의 손절·익절 순서를 알 수 없으면 사전 정의한 보수적 규칙을 적용한다.
- 모든 종목에 같은 계산 체계를 적용한다.
- Random split은 금지하고 시간 순서 Validation/Walk-Forward를 사용한다.
- scaler, winsorization, imputer, feature selection, threshold, hyperparameter는 각 Train 내부에서만 적합한다.
- 결과를 본 뒤 가설·변수·임계값을 소급 변경하지 않는다. 변경은 새 Experiment ID로 등록한다.

## Protected OOS

- `data/sealed/final_oos_v24/`의 2024–2025 자료는 Phase 8의 동결된 단일 릴리스 평가 전까지 열기·스캔·요약·집계·테스트 입력 사용을 모두 금지한다.
- 경로 존재와 봉인 manifest 확인 외에 `head`, `wc`, `find` 후 내용 읽기, glob 처리, 데이터프레임 로드도 금지한다.
- 일반 개발 경로는 `data/processed/v24/development/`뿐이다.
- OOS를 이용해 변수·모델·비용·포트폴리오 규칙을 바꾸면 해당 OOS는 영구적으로 무효다.
- 코드나 명령이 OOS 경로를 참조하면 즉시 중단하고 보고한다.

## 현재 단계

- Phase 0~4: 완료.
- Phase 3 기준선: 재현 기준선으로 채택, 거래 후보로는 탈락.
- Phase 4: 2021년 이하 물리 입력 경계 재검증과 독립 재실행을 완료했다. 기존 단변량 결과와 `reversal_5` 후보 판정은 불변이며, 이는 Phase 5 입력 후보일 뿐 모델·거래 후보가 아니다.
- Phase 5: Train/Validation Selection 완료. `tree_d3_l002`를 Development Test 단일 공개 후보로 동결했으나, Development Test는 미승인이며 Phase 5 최종 채택·완료 상태가 아니다. Validation 연도별 순초과수익률 gate는 0/3 통과다.
- Phase 4B: 2011~2018 Train 내부 다변수 Feature 감사를 완료했다. 21개 종목변수·5개 시장상태·6개 상호작용을 별도 Experiment로 검증했으며 기존 Phase 4 판정은 변경하지 않았다.
- Phase 5B: 일별 종목 점수·횡단면 순위 모델 7개를 2015~2018 내부 Validation에서 평가했다. `elastic_a005_l02`가 진단상 최선이었지만 연결 순초과수익률 -11.50%p, 연도 gate 2/4로 전 후보를 기각했다. 거래 후보와 Development Test 후보는 없다.
- Phase 5C: `elastic_a005_l02`를 고정하고 causal EMA5·상위 10/20 순위 지속성 정책을 2015~2018에서 적응적으로 진단했다. 순초과수익률은 -1.03%p로 개선됐지만 사전등록 turnover·현금 gate를 실패해 정책을 기각했다. 거래 후보와 Development Test 후보는 없다.
- Phase 5D: 평균 현금·최소 보유 gate를 제거하고 시장상태별 최대 10·5·0종목을 허용했다. 이미 소비된 2019~2021 재사용 진단에서 순초과수익률 -88.05%p로 실패했다. 운용은 가변 보유를 구현했지만 종목 점수 예측력이 부족했으며 거래·Development Test 후보는 없다.
- Phase 5E: 비용 차감 절대 초과수익 Ridge와 양수 여부 Logistic을 결합한 no-trade 모델을 2019~2021 adaptive diagnostic으로 실행했다. 전략 +29.31%, 지수 +50.40%, 순초과 -21.09%p로 실패했으며 거래·Development Test 후보는 없다.
- Phase 5F: 종목 기술신호의 5·20세션 경로, 평균·중앙값 HistGradientBoosting, Train-only IsolationForest 시장 이상상태 veto를 결합했다. 2019~2021 adaptive diagnostic에서 전략 -7.83%, 지수 +50.40%, 순초과 -58.23%p로 실패했으며 거래·Development Test 후보는 없다.
- Phase 5G: 2018년 이하 Train 내부에서 5·10·20거래일 비용 차감 초과수익을 동시에 예측하는 Extra Trees 합의 모델을 평가했다. 연결 순초과수익률 -3.66%p와 연도별 2/4로 기각됐으며 승격 후보가 아니다.
- Phase 1C: 2004~2009 KRX 원천자료를 기존 2010~2018 감사 데이터와 별도 물리 파티션으로 결합했다. 2000~2003은 제외했으며 미확정 Corporate Action은 경제조건을 추정하지 않고 Feature·label reset 경계로만 사용한다.
- Phase 5I: 2004~2010 학습 173,390행을 실제 포함한 고정 ElasticNet·점수 지속성·5세션 교체 구조를 2011~2018 8개 내부 fold에서 평가했다. 기본 비용 순초과수익률 -26.50%p, 2배 비용 -44.27%p, 연도별 2/8로 기각했으며 거래·Development Test 후보가 아니다.
- v2 Agent C4: LSTM·CNN 공동 표현으로 10거래일 비용 차감 공식 KOSPI200 초과수익과 양수 여부를 직접 예측했지만 평균 Rank IC 0.0119·AUC 0.5032로 약해 승격하지 않았다.
- v2 Agent D4: C4의 양의 예상 초과수익·상위 5개·5세션 재조정으로 D3의 과매매를 줄였지만 최선 순초과수익률 -55.09%p·평균 현금 94.91%로 기각했다.
- v2 Agent D5: B2·C3와 5개 상호작용을 얕은 관계 확률 모델로 결합하고 2020년에 24개 가중치·임계값 정책을 선택했다. 모든 정책과 2021~2023 소비 개발 진단에서 주문 0건이어서 거래 후보로 기각했다. 표시상 +12.79%p는 현금 100% 효과이며 알파가 아니다.
- v2 Legacy DART 2011~2014: 2,437개 원문 ZIP을 수치 후보·정정·PIT 접수일·identity 감사로 정리하고 2015~2023 표준 XBRL canonical 계정과 별도 파생 패널로 병합했다. strict legacy canonical은 330행뿐이며 2011~2014 핵심 Factor coverage가 0~25%로 낮아 Agent B 학습에는 사용 금지다. 기존 2016~2023 패널·결과는 변경하지 않았다.
- v1 상태: KOSPI 100 Phase 3~5I는 재현 가능한 과거 기록으로 보존하되 새 후보 선택에는 사용하지 않는다. 실패 registry 행은 삭제하지 않는다.
- v2 Phase 1: 실제 KOSPI 200 PIT·OpenDART 재무제표 수집, receipt-date 보정, 역사적 ticker–DART identity 동결, 표준 XBRL taxonomy와 일별 20개 펀더멘탈 Factor 패널 감사를 완료했다. 444개 이력 ticker 중 354개 identity를 자동 확정하고 90개는 fail-closed로 제외했다.
- v2 Phase 2: `EXP-20260826-001`에서 PIT 시가총액 상위 200·20개 재무 Factor·기계적 reset 후 희석도를 사용해 매일 최대 Top 30을 산출했다. `ridge_a10`이 평균 Rank IC 0.0360, NDCG@30 0.5616으로 선택됐으나 연도 IC는 4/6 양수이므로 consumed-development Agent B 후보 생성기로만 동결했다. 포트폴리오 백테스트·독립 OOS·거래 승격은 없다.
- v2 Phase 3: `EXP-20260826-002`에서 Agent B Top 30 안의 14개 causal OHLCV와 선형·얕은 비선형 이중모델을 평가했다. hist dual 평균 Rank IC -0.0072, linear dual -0.0083으로 모두 기각했으며 포트폴리오 단계로 넘기지 않는다.
- v2 Phase 3B: Agent B와 독립적으로 전체 PIT KOSPI 200을 평가한 `hist_event_dual`은 평균 Rank IC 0.0347, bottom AUC 0.6359, 연도별 양수 IC 5/5였다. Agent B와 일별 점수 상관은 -0.0523이며 Agent D 입력 후보로만 동결했다. 실제 LSTM/CNN과 포트폴리오는 미실행이다.
- v2 Phase 4: `EXP-20260826-004`에서 Agent C 단독과 Agent B 순위 25·50·75% 결합을 실제 비용·t+1 시가·5% gap veto·-5%/+10% bracket·10세션 규칙으로 평가했다. `C100`이 최선이었지만 순초과수익률 -22.07%p, 양의 연도 1/5, MDD -31.98%로 기각했다. B 25% 이상 결합은 모두 C 단독보다 악화했으므로 다음 후보는 Agent B 재설계 전까지 없다.
- v2 Phase 2B: 공식 KOSPI200 63세션 초과수익에서 0.5×최대불리변동을 차감한 품질 target으로 Agent B를 재설계했다. `ridge_quality` 평균 IC 0.03284, 양의 연도 3/5로 독립 승격하지 않고 Agent D2 진단 입력으로만 보존한다.
- v2 Phase 3C: 2004~2023 PIT 가격과 공식 KRX 1028 지수를 사용해 기존 event 모델과 공식 초과수익 직접 모델을 비교했다. `hist_event_dual_v1`이 평균 공식지수 초과수익 Rank IC 0.04184, 양의 연도 5/5로 선택됐으며 Agent D2 입력 후보로만 동결했다.
- v2 Phase 4B: `EXP-20260826-007`에서 B2 Top80 선필터와 B2 비제거 위험보정을 C2 단독 대조군과 공식 KRX 1028 지수로 비교했다. 위험보정이 최선이었지만 전략 +6.40%, 지수 +38.63%, 순초과 -32.24%p, 양의 연도 2/5로 기각했다. 세 후보 모두 reconciliation을 통과했고 독립 재실행 16개 파일은 byte-identical이다.
- v2 Phase 3D: `EXP-20260826-008`에서 실제 PyTorch LSTM으로 10세션 변동성을, 실제 1D CNN으로 t+1 시가 2:1 barrier 성공확률을 예측했다. Train-only 위험가중치 0.5를 결합한 C3는 공식지수 초과수익 Rank IC 0.04776, AUC 0.66410, 양의 연도 5/5로 C2보다 개선됐으나 소비된 개발 진단 입력일 뿐이다.
- v2 Phase 4C: `EXP-20260826-009`에서 C3 점수 0.05/0.075를 5%/11% 비중에 그대로 대응했다. 점수의 91~96%가 임계값을 넘어 과도한 상시투자가 발생했고, B2 위험보정 최선도 전략 -16.28%, 지수 +38.63%, 순초과 -54.91%p, MDD -41.57%로 기각했다.
- 데이터 증거: 2004~2023은 이미 결과를 관찰한 개발 전용 기간이다. v2의 독립 성과 증거는 모델 동결 뒤 2026-08-26 이후 forward shadow에서 새로 쌓는다.
- Phase 6 이후: 미구현.

v1 Phase 5 Development Test를 사용자 승인 없이 실행하지 않는다. v1 결과를 삭제하거나 v2의 독립 OOS로 재사용하지 않는다. 기각된 v2 Agent C를 포트폴리오 후보로 승격하거나 같은 기간에서 threshold만 재조정하지 않는다.

## 구현 원칙

- Raw 데이터는 수정하지 않는다. 파생 데이터는 별도 processed 계층에 쓴다.
- 코드 작성 후 관련 단위 테스트와 전체 회귀 테스트를 실행한다.
- 실행하지 않은 코드는 완료로 표시하지 않는다.
- 기존 파일을 불필요하게 덮어쓰지 않고, 규칙·데이터 계약 변경은 버전을 올린다.
- 대용량 데이터, 원본 ZIP, 봉인 OOS, 임시 작업물은 Git에 커밋하지 않는다.
- 실험 결과는 코드·설정·데이터·산출물 해시와 재현 명령을 기록한다.
- 현재 기준 회귀 명령은 `PYTHONPATH=src python -m unittest discover -s tests -v`이며 2026-08-26 구형 DART 수치 후보 감사에서 243/243 통과했다.

## 단계 완료 산출물

각 단계는 다음을 남겨야 한다.

- `docs/stages/phase_N_spec.md`: 입력·출력·가정·비목표·테스트·완료 조건
- `docs/stages/phase_N_report.md`: 실제 실행 결과·문제·미결정 사항
- `configs/`: 실행에 사용한 동결 설정
- `experiments/registry.csv`: 결과 확인 전 등록 및 종료 후 결과 갱신
- `artifacts/phaseN/`: 재현 가능한 요약·manifest·감사 결과
- `tests/`: 핵심 불변조건과 회귀 테스트

단계 보고서의 마지막에는 `Codex Handoff`를 두고 구현 대상, 파일, API, 테스트, 실행 명령, 완료 조건을 명확히 적는다.

## 기본 단계 완료 프로토콜

사용자가 특정 Phase의 구현을 요청하면 다음을 기본적으로 수행한다.

1. 해당 Phase 명세와 Handoff를 읽는다.
2. 필요한 코드·테스트·설정·문서를 구현한다.
3. 전체 회귀 테스트와 해당 Phase 테스트를 실행한다.
4. 테스트 실패 시 commit·push·PR을 하지 않고 중단한다.
5. 테스트가 모두 통과하면 변경 사항을 검토한다.
6. 해당 Phase branch에 commit한다.
7. 원격 저장소에 push한다.
8. draft PR을 생성한다.
9. 최종 응답에 변경 내용, 테스트 결과, commit hash, branch, PR 주소를 보고한다.

사용자가 별도로 “commit하지 말 것”, “push하지 말 것”, “PR을 만들지 말 것”이라고 지정한 경우에는 해당 지시를 우선한다.

다음 작업은 절대 자동으로 수행하지 않는다.

- protected OOS 접근
- 연구 규칙 변경
- 과거 Phase 결과 변경
- 실제 주문
- 서버 배포
- 계좌·외부 서비스 변경

## 단계 명세 동기화 규칙

사용자가 특정 Phase의 인수검사, 명세 확정, 또는 구현 준비를 요청하면 Codex는 다음을 수행한다.

1. 관련 문서·설정·코드·테스트를 읽기 전용으로 검토한다.
2. 불일치와 위험을 보고한다.
3. 사용자가 명세 확정 또는 문서 작성을 명시적으로 요청한 경우,
   `docs/stages/phase_N_spec.md`가 없으면 새로 작성한다.
4. 기존 명세가 있으면 사용자에게 갱신 권한을 확인한 뒤 수정한다.
5. 명세에는 입력, 출력, 기간, 데이터 경계, 금지사항, 구현 파일,
   테스트, 실행 명령, 완료 조건, Codex Handoff를 포함한다.
6. 명세 작성 자체는 Phase 실행·데이터 처리·OOS 접근으로 간주하지 않는다.
