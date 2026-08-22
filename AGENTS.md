# KOSPI 100 Technical Systematic AI — Codex 작업 규칙

이 저장소는 ChatGPT Work가 연구·분석·의사결정 명세를 만들고, Codex가 코드 구현·테스트·리팩터링·자동화를 수행하는 공동 저장소다. 모든 보고서와 새 문서는 한글로 작성한다. 상세한 연구·운영 원칙의 원문은 `docs/PROJECT_MASTER_PROMPT_KO.md`를 따른다.

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

- Universe는 과거 시점별 실제 KOSPI 100 구성종목이다.
- Long-only 현금 주식만 사용하며 공매도·레버리지·파생상품은 금지한다.
- 투자 Factor는 OHLCV, 거래대금, KOSPI 100 지수, 동시점 Universe Breadth 및 그 기술적 파생변수로 제한한다.
- 재무·DART 공시내용·뉴스·밸류에이션·업종 전망·기업별 텍스트는 Factor로 사용하지 않는다.
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
- Phase 6 이후: 미구현.

Phase 5 Development Test를 사용자 승인 없이 실행하지 않는다. Phase 4·5 결과를 근거로 기존 변수·기간·임계값을 소급 변경하지 않는다.

## 구현 원칙

- Raw 데이터는 수정하지 않는다. 파생 데이터는 별도 processed 계층에 쓴다.
- 코드 작성 후 관련 단위 테스트와 전체 회귀 테스트를 실행한다.
- 실행하지 않은 코드는 완료로 표시하지 않는다.
- 기존 파일을 불필요하게 덮어쓰지 않고, 규칙·데이터 계약 변경은 버전을 올린다.
- 대용량 데이터, 원본 ZIP, 봉인 OOS, 임시 작업물은 Git에 커밋하지 않는다.
- 실험 결과는 코드·설정·데이터·산출물 해시와 재현 명령을 기록한다.
- 현재 기준 회귀 명령은 `PYTHONPATH=src python -m unittest discover -s tests -v`이며 2026-08-24 Phase 5G 감사에서 118/118 통과했다.

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
