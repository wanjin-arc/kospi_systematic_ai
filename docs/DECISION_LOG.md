# Decision Log

## Use Rules

- IDs are permanent and monotonic: `DEC-YYYY-###`.
- Do not edit a decided value to match a later result. Add a superseding decision that names the previous ID, reason, expected impact, and whether final OOS is invalidated.
- `Confirmed` means approved for the stated stage; `Pending verification` means the policy is fixed but its external/input fact must be audited.
- Detailed recommendation, reason, alternative, and impact for Phase-0 decisions are in `docs/RESEARCH_PROTOCOL.md` D01–D24.

## Phase-0 Decisions

| ID | Decision | Approved value / recommendation | Status | Supersedes |
|---|---|---|---|---|
| DEC-2026-001 | Research window | 2011-01-01 to 2025-12-31; 2026 reserved for paper/live shadow | Pending verification | — |
| DEC-2026-002 | Universe | Point-in-time KOSPI 100 memberships, effective-date governed | Pending verification | — |
| DEC-2026-003 | Price convention | Raw execution series plus as-of split-adjusted feature series; no dividend-adjusted feature series | Pending verification | — |
| DEC-2026-004 | Signal time | Official close of `t`; freeze before `t+1` | Confirmed | — |
| DEC-2026-005 | Execution time | Next session opening auction/session with adverse slippage | Confirmed | — |
| DEC-2026-006 | Entry gap policy | Pre-submitted +5% marketable buy limit; no hindsight cancellation | Pending broker verification | — |
| DEC-2026-007 | Daily stop/target ambiguity | Conservative stop-first rule | Confirmed | — |
| DEC-2026-008 | Holding candidates | 5, 10, 20 trading sessions | Confirmed | — |
| DEC-2026-009 | Agent B target | 10-session cross-sectional KOSPI 100 excess open-to-open return rank; limited variants | Confirmed | — |
| DEC-2026-010 | Agent C labels | 10-session triple barrier and within-candidate excess-return label | Confirmed | — |
| DEC-2026-011 | Benchmark | KOSPI 100 price index | Pending vendor verification | — |
| DEC-2026-012 | Costs | Calendar schedule; 2 bps/side commission proxy, date-specific sale cost, 10 bps/side slippage | Pending tax/broker verification | — |
| DEC-2026-013 | Holdings | Baseline 10 slots; compare 5/10/15 only in development | Confirmed | — |
| DEC-2026-014 | Sizing | Equal notional, maximum 10% per position, whole shares, cash retained | Confirmed | — |
| DEC-2026-015 | Partitions | Train 2011–18, validation 2019–21, dev test 2022–23, final OOS 2024–25 | Pending data verification | — |
| DEC-2026-016 | Walk-forward | Anchored annual refits through 2023; rolling window is robustness only | Confirmed | — |
| DEC-2026-017 | OOS protection | Separate sealed manifest; one frozen-release evaluation in Phase 8 | Pending technical implementation | — |
| DEC-2026-018 | Purge/embargo | 20 sessions, adjusted upward if label horizon grows | Confirmed | — |
| DEC-2026-019 | Baseline acceptance | Deterministic and audited reference; candidate requires positive net excess on validation/dev test | Confirmed | — |
| DEC-2026-020 | ML adoption | Pre-committed multi-fold, net Sharpe, dev-test, MDD, and 2× cost gates | Confirmed | — |
| DEC-2026-021 | Experiment recording | Registry row pre-result; immutable hashes/results | Confirmed | — |
| DEC-2026-022 | Paper entry | Phase 8 approval, frozen release, 60 sessions and 30 completed exits plus cases | Pending broker selection | — |
| DEC-2026-023 | Live entry | OOS/robustness/paper gates, 90 sessions, 50 exits, explicit capital approval | Confirmed | — |
| DEC-2026-024 | Kill switches | Hard operational stops plus 3% daily / 12% drawdown risk stop | Pending execution implementation | — |

## Phase-1 Decisions

| ID | Decision | Approved value / recommendation | Status | Supersedes |
|---|---|---|---|---|
| DEC-2026-025 | Authoritative data family | KRX official historical extract/Data Marketplace is primary; third-party libraries may only bootstrap or cross-check | Pending acquisition | — |
| DEC-2026-026 | Missing-source treatment | Missing historical constituents, events, or bars block the build; no current-universe or interpolated-price substitution | Confirmed | — |
| DEC-2026-027 | Final-OOS storage | Development through 2023 and sealed 2024–2025 outputs use separate directories and manifests | Implemented and synthetically tested | DEC-2026-017 implementation |
| DEC-2026-028 | Temporary storage format | Deterministic gzip CSV is permitted for validation in the dependency-limited runtime; Phase 1 gate still requires Parquet or DuckDB conversion | Temporary, gate not satisfied | — |
| DEC-2026-029 | Phase-1 status | Code and schema are ready; actual-data validation is blocked until an auditable KRX bundle is supplied or reachable | Blocked | — |
| DEC-2026-030 | Supplied-export normalization | Preserve original hashes; normalize the two user-supplied files with a deterministic adapter; do not infer missing source metadata | Implemented, provenance pending | — |
| DEC-2026-031 | Provisional calendar | Derive session dates from index observations for data alignment; leave official hours and early-close flags unknown | Implemented with warnings | — |
| DEC-2026-032 | 99-member sessions | Preserve all supplied 99-member sessions and fail the frozen exactly-100 gate; never invent or nearest-date-fill a constituent | Pending authoritative resolution | DEC-2026-026 application |
| DEC-2026-033 | Phase-1 partial-data status | Membership and index inputs are normalized, but the build remains blocked by missing stock OHLCV/actions/suspensions, provisional identity, and unresolved lineage | Blocked | DEC-2026-029 |

## Phase-1 Finalization and Phase-2 Decisions

| ID | Decision | Approved value / recommendation | Status | Supersedes |
|---|---|---|---|---|
| DEC-2026-034 | Phase-1 v24 final status | Production v24 independently audited: daily PIT data, 174 securities, 98 corporate actions, 318 intraday files, and sealed 2024–2025 partition | Completed | DEC-2026-029, DEC-2026-033 |
| DEC-2026-035 | Phase-2 engine boundary | Engine consumes pre-frozen orders and never creates features, ranks, signals, labels, or models | Confirmed | — |
| DEC-2026-036 | Deterministic execution order | Corporate actions before open; sells before buys; then priority, security ID, and order ID | Confirmed | — |
| DEC-2026-037 | Accounting precision | Decimal arithmetic; whole shares; statutory charges and proxy commissions rounded down to one KRW | Confirmed for research | DEC-2026-012 implementation |
| DEC-2026-038 | Unresolved corporate actions | Abort a run if a held position reaches an event without complete portfolio terms; never guess entitlements | Confirmed | — |
| DEC-2026-039 | Phase-2 status | 26/26 project tests, 17/17 Phase-2 tests, and 250/250 seeded accounting stress scenarios pass; deterministic artifacts and 7/7 reconciliation checks pass | Completed | — |

## Phase-3 Decisions

| ID | Decision | Approved value / recommendation | Status | Supersedes |
|---|---|---|---|---|
| DEC-2026-040 | Reference signal | Close above SMA200 and 126-session stock return above KOSPI100 return; rank descending by 126-session excess return; no rank-loss exit | Confirmed | — |
| DEC-2026-041 | Validation-only baseline selection | Among only `H={5,10,20}` and `N={5,10,15}`, select highest net Sharpe with frozen tie-breaks; selected `H=20, N=10` | Completed | DEC-2026-008, DEC-2026-013 implementation |
| DEC-2026-042 | Phase-3 status | Accept the deterministic/cost-aware reference; reject it as a trading candidate because Validation (−61.82 pp) and Development Test (−1.12 pp) net excess returns are negative | Completed | DEC-2026-019 application |
| DEC-2026-043 | Phase-4 boundary | Keep final OOS sealed and stop after Phase 3; do not begin feature research without explicit user approval | Confirmed | — |

## Phase-4B/5B Decisions

| ID | Decision | Approved value / recommendation | Status | Supersedes |
|---|---|---|---|---|
| DEC-2026-044 | Train 내부 다변수 재연구 | 기존 Phase 4·5 결과를 보존하고 2011~2018 내부 anchored fold에서 21개 종목변수·5개 시장상태·6개 상호작용을 별도 Experiment로 평가한다. 2019~2021, Development Test, Final OOS는 새 후보 선택에 사용하지 않는다. | Completed; user approved 2026-08-23 | — |
| DEC-2026-045 | 일별 점수·순위 및 10세션 보유 | 모든 적격 종목을 매일 동일하게 점수화·순위화하고 `t+1` 주문 우선순위로 사용한다. D09 target과 맞춰 10세션 보유, 최대 10종목·10%·no pyramiding을 적용하며 연결 및 모든 내부 연도의 순초과수익률 양수를 hard gate로 둔다. | Completed; all candidates rejected | DEC-2026-041의 보유기간을 Phase 5B 실험에서만 대체 |

## Phase-5C Decisions

| ID | Decision | Approved value / recommendation | Status | Supersedes |
|---|---|---|---|---|
| DEC-2026-046 | 적응적 점수 지속성 진단 | Phase 5B 결과를 본 상태를 명시하고 `elastic_a005_l02`를 고정한 채 2015~2018에서 causal EMA5, 상위 10 목표·20위 fallback/이탈, 20세션 안전 상한을 한 번 진단한다. 결과가 좋아도 거래·Development Test 후보로 자동 승격하지 않는다. | Completed; user authorized Phase 5C 2026-08-23; diagnostic failed | — |
| DEC-2026-047 | 소표본 연도 gate 해석 | 4개 fold의 80% 조건이 사실상 4/4가 되는 과도한 기각 위험을 인정한다. 향후 확인에서는 연결 기본비용·2배 비용 초과수익과 위험 한도를 hard gate로, 연도 양수 비율을 regime 진단으로 둘 것을 권고한다. 기존 D20은 사용자 별도 승인 전 변경하지 않는다. | Proposed; explicit approval required | None; D20 remains active |

## Phase-5D Decisions

| ID | Decision | Approved value / recommendation | Status | Supersedes |
|---|---|---|---|---|
| DEC-2026-048 | 현금·보유 수의 선택 결과화 | 평균 현금 10% 이하를 hard gate에서 제거하고 최소 보유 종목을 0개로 둔다. 현금과 보유 수는 점수·시장상태의 결과로 보고하며 최대 보유만 10개로 제한한다. | Confirmed; user approved 2026-08-23 | Phase 5C adaptive cash diagnostic only |
| DEC-2026-049 | 2019~2021 재사용 진단 | 이미 Phase 5에서 소비한 2019~2021을 Test/OOS가 아닌 재사용 진단으로 한 번 사용한다. 이 결과로 승격하지 않으며 Development Test와 Final OOS는 계속 봉인한다. | Confirmed; user approved 2026-08-23 | — |

## Phase-5E Decisions

| ID | Decision | Approved value / recommendation | Status | Supersedes |
|---|---|---|---|---|
| DEC-2026-050 | 절대 순초과수익 target | Phase 5E에 한해 D09 횡단면 순위 대신 `t+1` 시가부터 `t+11` 시가까지의 비용 차감 KOSPI 100 초과 로그수익률과 그 값의 양수 여부를 각각 회귀·분류 target으로 사용한다. 기존 D09와 과거 Phase 결과는 변경하지 않는다. | Confirmed; user approved 2026-08-23 | Phase 5E에 한해 DEC-2026-009 대체 |
| DEC-2026-051 | 이중 no-trade gate | 고정 Ridge 회귀와 Logistic 분류를 Train 내부에서만 적합하고, 예상 순초과수익 `>=0.5%` 및 양수 확률 `>=60%`를 모두 통과한 종목만 예상 순초과수익 순으로 최대 10개 매수한다. 최소 보유·현금 gate와 시장상태별 강제 capacity는 두지 않는다. | Confirmed; user approved 2026-08-23 | DEC-2026-048 확장, Phase 5D 시장 capacity 미사용 |
| DEC-2026-052 | Phase 5E 증거 지위 | 2019~2021은 이미 소비된 adaptive diagnostic으로만 사용한다. 경제성 gate를 계산하되 성과와 무관하게 승격하지 않고 Development Test와 Final OOS를 열지 않는다. | Confirmed; user approved 2026-08-23 | DEC-2026-049 확장 |

## Phase-5F Decisions

| ID | Decision | Approved value / recommendation | Status | Supersedes |
|---|---|---|---|---|
| DEC-2026-053 | 시계열 경로·강건 이중 회귀 | 8개 기술변수 rank의 현재값·5세션 변화·20세션 평균·표준편차·방향 지속성과 5개 시장변수의 현재값·5세션 변화·20세션 변동을 입력으로 고정하고, 얕은 HistGradientBoosting 평균·중앙값 회귀를 함께 사용한다. | Confirmed; user approved 2026-08-23 | Phase 5E Ridge·Logistic 구조 대체 |
| DEC-2026-054 | Train-only 시장 이상상태 veto | 외부 사건 라벨 없이 각 fold Train의 시장 기술변수만으로 IsolationForest를 적합하고 Train 점수 하위 5%를 이상 임계값으로 고정한다. 이상상태에서는 신규매수를 보류하고 기존 보유는 청산 신호를 낸다. | Confirmed; user approved 2026-08-23 | Phase 5D 강제 capacity와 다름 |
| DEC-2026-055 | Phase 5F 증거 지위 | 2019~2021은 이미 소비된 adaptive diagnostic으로만 사용한다. 논문은 아이디어 출처일 뿐 그 성과를 본 프로젝트의 증거로 간주하지 않으며, 결과와 무관하게 Development Test 후보로 승격하지 않는다. | Confirmed; user approved 2026-08-23 | DEC-2026-052 확장 |
| DEC-2026-056 | Phase 5F 결과 | 시계열 경로·평균/중앙값 회귀·시장 이상상태 veto는 기본비용 순초과수익 -58.23%p, 연도 gate 0/3으로 실패했다. 모델과 전체 Feature 묶음을 기각하고 같은 2019~2021에서 재조정하지 않는다. | Completed; rejected | DEC-2026-053, DEC-2026-054 적용 결과 |

## Phase-5G Decisions

| ID | Decision | Approved value / recommendation | Status | Supersedes |
|---|---|---|---|---|
| DEC-2026-057 | 2018년 이하 다중 기간 내부 진단 | 현재 데이터로 연구를 계속하되 이미 소비한 2019~2021을 재사용하지 않는다. Phase 4B의 21개 종목 변수·5개 시장상태·6개 상호작용으로 5·10·20거래일 비용 차감 초과수익을 동시에 예측하고, 2개 이상 양수이며 중앙값 0.2% 이상인 종목만 매일 순위화한다. 최소 보유 0개와 현금을 허용하며 결과와 무관하게 자동 승격하지 않는다. | Confirmed; user approved 2026-08-23 | Phase 5F 이후 신규 내부 진단 |
| DEC-2026-058 | Phase 5G 결과 | 2015~2018 연결 내부 진단에서 전략 +3.72%, 지수 +7.38%, 순초과 -3.66%p, 2배 비용 -6.96%p, 연도별 gate 2/4였다. MDD·활동성 gate만 통과했으므로 모델은 기각하고 같은 내부 기간에서 재조정하지 않는다. | Completed; rejected | DEC-2026-057 적용 결과 |

| DEC-2026-059 | v25 공식 99종목 PIT 스냅샷 | KRX [11006] 원응답을 권위 있는 PIT 기록으로 채택한다. 26개 날짜의 99종목은 결측으로 보정하지 않으며 편출 후 공석 상태로 보존한다. 이 결정은 v25 감사 후보에만 적용하며 v24 및 완료된 Phase 결과는 변경하지 않는다. | Confirmed; user approved 2026-08-25 | DEC-2026-032의 v25 적용 |

| DEC-2026-060 | Phase 4C KOSPI 전체 동시점 시장상태 후보 감사 | KOSPI 전체 OHLCV로부터 동시점 상승비율·중앙값 일수익률·일수익률 분산·20세션 상대 거래대금을 만들고, 이를 KOSPI 100의 21개 사전등록 기술 순위와 곱한 84개 상호작용 후보로 감사한다. KOSPI 전체 종목은 target Universe·개별 종목 학습행·직접 종목점수로 사용하지 않는다. 2011~2018 물리 입력과 anchored internal fold만 사용하고, 이 감사만으로 Feature·모델·거래 후보를 채택하지 않는다. | Confirmed; user approved 2026-08-25 | 기존 투자 Factor 범위의 시장상태 후보 확장 |

| DEC-2026-061 | Phase 5H 시장상태 상호작용 순위모델 비교 | Phase 4C의 결과 순위로 변수를 고르지 않고 4개 KOSPI 전체 시장상태, Phase 4B 고정 21개 종목순위 및 84개 상호작용 전체를 고정 입력으로 사용한다. 기존 Phase 5B와 동일한 7개 모델·비용·포트폴리오·gate를 2015~2018 내부 fold에서 비교하여 시장상태 추가의 증분효과를 진단한다. 2019년 이후 자료와 Development Test는 사용하지 않는다. | Confirmed; user approved 2026-08-25 | DEC-2026-060 후속 모델 실험 |

| DEC-2026-062 | 2004~2018 확장 학습 파티션 | 2004~2009 KRX PIT 구성종목·일봉·지수를 기존 v24 2010~2018과 별도 파티션으로 결합한다. 2000~2003은 제외하고, 미확정 Corporate Action의 경제조건을 추정하지 않으며 연속 세션의 가격·상장주식수·거래상태 단절에서 Feature와 label을 fail-closed reset한다. 기존 Phase 결과와 v24는 변경하지 않는다. | Confirmed; user approved 2026-08-25 | DEC-2026-001 연구 시작일을 Phase 5I 진단에서만 확장 |

| DEC-2026-063 | Phase 5I 지속성·5세션 교체 구조 | 2004년부터 적합한 고정 ElasticNet 점수를 매일 산출하되 EMA5, 3세션 연속 상위 10 진입, 3세션 연속 20위 밖 이탈, 5세션 교체, 최대 보유 20세션을 한 번 평가한다. 연결 기본비용과 2배 비용 순초과수익만 adaptive hard gate로 두고 연도별 비율은 진단한다. 결과와 무관하게 같은 구간에서 재조정하거나 Development Test 후보로 자동 승격하지 않는다. | Confirmed; user approved 2026-08-25 | DEC-2026-046 후속 구조 진단; D20 불변 |

| DEC-2026-064 | Phase 5I 결과 | 2004~2010을 실제 적합에 포함한 2011~2018 8-fold 진단에서 기본 비용 순초과수익률 -26.50%p, 2배 비용 -44.27%p, 연도별 2/8로 hard gate를 실패했다. 점수 지속성 구조는 비교 정책보다 turnover를 높였고 약한 미래수익 관계를 개선하지 못했으므로 기각한다. 같은 구간에서 추가 조정하지 않으며 Development Test 후보로 승격하지 않는다. | Completed; rejected | DEC-2026-063 적용 결과 |

## v2 Fundamental+Technical Decisions

| ID | Decision | Approved value / recommendation | Status | Supersedes |
|---|---|---|---|---|
| DEC-2026-065 | KOSPI 200 PIT Universe | 새 v2 연구 Universe를 날짜별 실제 KOSPI 200 구성종목으로 확장한다. 기존 KOSPI 100 코드·데이터·결과는 v1 재현용으로 보존하며 현재 구성종목의 과거 소급과 빈자리 임의 보간은 금지한다. | Confirmed; user approved 2026-08-25 | v1 Universe 규칙은 legacy로 제한 |
| DEC-2026-066 | PIT 펀더멘탈 Agent B | 실제 DART 접수일 다음 거래일부터 확정 재무제표 수치만 사용한다. 20개 수익성·가치·건전성·성장성 Factor와 단면 percentile·robust z-score를 후보로 두며 정정값 소급, 공시 텍스트, 가이던스, 뉴스는 금지한다. XGBRanker는 데이터 감사 뒤 별도 사전등록 후보로만 검토한다. | Confirmed; user approved 2026-08-25 | v1 Fundamental 금지를 v2에 한해 대체 |
| DEC-2026-067 | 실패 기록과 소비 기간 | 실패 experiment는 삭제하지 않는다. registry·요약·manifest·hash를 append-only로 보존하고 2004~2023을 consumed development로 표시해 독립 Validation/OOS로 재사용하지 않는다. 대용량 산출물 삭제는 요약 보존 뒤 별도 승인한다. | Confirmed implementation of user intent 2026-08-25 | 실패 기록 삭제 요청을 재현성 보존 방식으로 구체화 |
| DEC-2026-068 | v2 독립 평가 경계 | 기존 2024~2025 v1 Final OOS는 계속 봉인하며 v2로 전용하지 않는다. v2의 독립 증거는 모델·설정 동결 뒤 2026-08-26 이후 forward paper/shadow 기간에서 새로 축적한다. | Confirmed 2026-08-25 | 기존 D15~D17은 v1 재현에만 적용 |
| DEC-2026-069 | 역사적 ticker–DART identity 동결 | PIT membership 종목명과 DART 법인명의 정규화 exact match 및 ticker→corp-code 유일성을 동시에 요구한다. 수동 alias는 v1에서 비워 두며, 354개 ticker만 확정하고 90개는 fail-closed 제외한다. | Confirmed; user approved direct freeze 2026-08-26 | DEC-2026-065 구현 계약 |
| DEC-2026-070 | 표준 XBRL taxonomy와 Factor 패널 | account-name 추정 없이 표준 XBRL account ID만 사용하고, 누적 손익·현금흐름은 당시 공개된 전기 연차와 동기 누적값으로 TTM화한다. 2015~2023 원천에서 2016-03-24~2023-12-28 일별 20 Factor 패널을 생성하되 모델은 별도 사전등록 전 시작하지 않는다. | Confirmed implementation 2026-08-26 | DEC-2026-066 데이터 계약 구체화 |
| DEC-2026-071 | Fundamental Agent B 일별 Top 30 | 매일 실제 PIT KOSPI 200에서 시가총액 상위 200개를 먼저 제한하고, 최신 확정 재무상태와 기계적 분할·병합을 reset한 252세션 희석도를 입력으로 최대 Top 30을 산출한다. Equal composite·Ridge·얕은 HistGradientBoosting을 63세션 월말 순위 target의 expanding walk-forward로 비교하며 Phase 2에서는 주문·포트폴리오 백테스트를 하지 않는다. | Confirmed; user approved 2026-08-26 | DEC-2026-066 후속 모델 계약 |
| DEC-2026-072 | Fundamental Agent B 진단 결과 | 6개 consumed-development fold에서 Ridge(alpha=10)가 평균 Rank IC 0.0360, NDCG@30 0.5616으로 선택됐다. 연도별 IC는 4/6 양수이므로 일별 Top 30 후보 생성기로만 동결하고 독립 성과·거래 모델로 승격하지 않는다. | Completed; diagnostic handoff only | DEC-2026-071 실행 결과 |
| DEC-2026-073 | Technical Agent C 이중 예측 | Agent B Top 30 안에서만 14개 causal OHLCV Feature로 10세션 비용 차감 수익률과 양수 확률을 함께 예측한다. 예상 순수익 양수·확률 55% 이상만 최대 10개 후보로 내고 0종목을 허용한다. Phase 3에서는 포트폴리오 백테스트를 하지 않는다. | Confirmed; user approved 2026-08-26 | v1 Phase 5E 교훈을 v2 경계 안에서 재설계 |
| DEC-2026-074 | Technical Agent C 결과 | hist dual 평균 Rank IC -0.0072, linear dual -0.0083으로 두 후보를 모두 기각한다. 55% gate는 513/1,233일을 no-trade로 만들었지만 음의 순위 예측력을 해결하지 못했으므로 포트폴리오 단계로 넘기지 않는다. | Completed; rejected | DEC-2026-073 실행 결과 |
| DEC-2026-075 | 독립 Technical Agent C | Agent B Top 30 직렬 gate를 제거하고 PIT KOSPI 200 전체를 OHLCV만으로 평가한다. 5% 손절보다 10% 익절이 먼저 발생할 확률과 10세션 최대 불리 변동을 별도 분기로 예측해 Agent D용 독립 기술 점수를 만든다. | Confirmed; user approved 2026-08-26 | DEC-2026-073의 직렬 구조를 대체하지 않고 별도 비교 |
| DEC-2026-076 | 독립 Agent C 결과 | hist event dual은 평균 Rank IC 0.0347, bottom AUC 0.6359, 연도별 양수 IC 5/5였다. Agent B 점수와 일별 상관은 -0.0523으로 낮아 보완 가능성이 있으므로 Agent D 입력 후보로 채택하되 거래 모델로는 승격하지 않는다. | Completed; Agent D input candidate only | DEC-2026-075 실행 결과 |
| DEC-2026-077 | Agent D 독립 점수 결합 | C score 0.05/0.075를 각각 5%/11% 비중에 대응시키고 B는 종목 제거가 아니라 0/25/50/75% 순위 가산점 후보로만 사용한다. gap 5%, 손절 5%, 익절 10%, 최대 10세션·10종목을 고정하고 PIT 시총가중 proxy 대비 평가한다. | Confirmed; user approved 2026-08-26 | DEC-2026-076 후속 포트폴리오 계약 |

| DEC-2026-078 | Agent D 결과 | 네 후보 중 `C100`이 최선이었지만 순초과수익률 -22.07%p, 양의 연도 1/5, MDD -31.98%로 gate를 실패했다. B 25% 결합부터 -34.95%p로 악화하여 단순 가중 결합을 기각한다. 다음 연구는 B 가중치 미세조정이 아니라 Agent B target·시간축·calibration 재설계로 분리한다. | Completed; rejected | DEC-2026-077 실행 결과 |

| DEC-2026-079 | Agent B2 품질·하방위험 결과 | 공식 KOSPI200 63세션 초과수익에서 0.5×MAE를 차감한 target은 Ridge에서 평균 IC 0.03284였으나 양의 연도 3/5에 그쳤다. 전체 점수와 Top80은 Agent D2 진단 입력으로만 보존하고 독립 승격하지 않는다. | Completed; diagnostic only | DEC-2026-078 후속 B 재설계 |
| DEC-2026-080 | Agent C2 장기이력·공식지수 결과 | 기존 `hist_event_dual_v1`이 공식 초과수익 Rank IC 0.04184와 양의 연도 5/5로 직접 excess 모델들을 이겼다. 핵심 모델은 유지하되 소비된 개발 결과이므로 Agent D2 입력 후보로만 사용한다. | Completed; diagnostic only | DEC-2026-076 확장 검증 |
| DEC-2026-081 | Agent D2 이중 결합 비교 | C2 단독 대조군과 함께 B2 Top80 선필터, `C2 percentile × (0.5 + 0.5 × B2 percentile)` 비제거 위험보정을 동일한 비용·체결·청산 규칙으로 비교한다. 결과 확인 전 세 후보와 공식 KRX 1028 benchmark를 동결한다. | Confirmed; user approved 2026-08-26 | DEC-2026-078 후속 재설계 |
| DEC-2026-082 | Agent D2 결과 | B2 위험보정이 전략 +6.40%, 공식 지수 +38.63%, 순초과 -32.24%p, Sharpe 0.202, MDD -22.03%, 양의 연도 2/5로 상대적 최선이었다. B2 Top80 직렬과 C2 단독보다 개선했지만 경제성 gate를 실패해 세 후보를 모두 기각한다. | Completed; rejected | DEC-2026-081 실행 결과 |
| DEC-2026-083 | Agent C3 실제 LSTM·CNN | 40거래일 OHLCV 6채널을 실제 PyTorch LSTM 변동성 분기와 1D CNN 2:1 성공확률 분기에 입력한다. 2017~2018에서 위험가중치 4개만 Train-only 선택하고 2019~2023은 소비된 개발 진단으로만 사용한다. | Confirmed; user approved 2026-08-26 | DEC-2026-080 후속 전면 재설계 |
| DEC-2026-084 | Agent C3 결과 | 위험가중치 0.5의 C3는 평균 공식지수 초과수익 Rank IC 0.04776, 2:1 AUC 0.66410, 양의 연도 5/5로 C2보다 개선됐다. 실제 딥러닝 기술 점수 입력으로 보존하되 독립 OOS·거래 후보로 승격하지 않는다. | Completed; diagnostic input only | DEC-2026-083 실행 결과 |
| DEC-2026-085 | Agent D3 고정 임계값 | 사용자 제시 방식대로 C3 점수 0.05·0.075를 각각 5%·11% 비중에 대응하고 t+1 시가·-5%/+10%·10세션을 적용한다. C3 단독과 B2 비제거 위험보정을 비교한다. | Confirmed; user approved 2026-08-26 | DEC-2026-081의 C2를 C3로 교체 |
| DEC-2026-086 | Agent D3 결과 | C3 점수의 91~96%가 고정 임계값을 넘어 과도한 투자가 발생했다. B2 위험보정 최선도 순초과 -54.91%p, turnover 292.06배, MDD -41.57%로 실패해 현재 매매정책을 기각한다. | Completed; rejected | DEC-2026-085 실행 결과 |

## Decision Entry Template

```markdown
### DEC-YYYY-### — Short title

- Date:
- Stage:
- Status: Proposed | Confirmed | Pending verification | Superseded | Rejected
- Decision owner:
- Related experiment IDs:
- Previous/superseded decision:
- Recommendation:
- Reason and evidence:
- Important alternative considered:
- Expected impact:
- Final-OOS impact: None | Invalidates current OOS | Requires a new OOS period
- Approval record:
```
## DEC-087 — Agent C4 다중과제 직접 초과수익 모델은 승격하지 않음 (2026-08-26)

40세션 LSTM·CNN 공동 표현으로 10세션 공식지수 초과수익과 양수 여부를 예측했으나 평균 Rank IC 0.0119와 AUC 0.5032에 그쳤다. C4는 D4 진단 입력으로만 사용하고 거래 후보로 승격하지 않는다.

## DEC-088 — Agent D4 저회전 no-trade 구조 기각 (2026-08-26)

D3의 raw score 임계값과 일별 재주문을 제거해 turnover를 크게 낮췄지만, 최선 후보도 순초과수익률 -55.09%p와 평균 현금 94.91%로 실패했다. 같은 소비 기간에서 임계값을 재튜닝하지 않는다.

## DEC-089 — Agent D5 관계 확률 결합 최종 개발 진단 (2026-08-26)

사용자 승인에 따라 B2 품질점수와 C3 LSTMㆍCNN 점수의 비선형 관계를 얕은 확률
모델로 학습한다. B/C 결합비와 매수 임계값은 2020년 이하에서만 선택하고,
2021~2023은 이미 소비된 개발 진단으로 한 번 평가한다. 같은 구간의 여러 seed나
반복 백테스트는 독립 Test로 해석하지 않는다. 2011~2014 DART 원문은 수치계정ㆍPIT
identity 감사가 끝나지 않았으므로 이번 입력에서 제외하며, Final OOS는 접근하지 않는다.

## DEC-090 — Agent D5 무거래 결과 기각 (2026-08-26)

`EXP-20260826-012`의 2020 선택 정책 24개는 모두 주문 0건이었다. 2019~2020으로
재적합한 관계 모델의 2021~2023 AUC는 0.6214였지만 예측확률 최대값이 0.4064로
사전등록 최소 임계값 0.50에 미달해 진입 가능 행도 0개였다. 전략 0%와 공식 지수
-12.79%의 차이는 전액 현금 효과이므로 알파로 인정하지 않고 거래 후보를 기각한다.
같은 소비 개발기간을 보고 임계값을 낮추거나 가중치·모델을 다시 선택하지 않는다.

## DEC-091 — B XGBRanker·C LSTM/CNN·D 직렬 결합과 미래 검증 경계 (2026-08-26)

사용자 승인에 따라 다음 단일 연구 방향을 동결한다. Agent B는 확정 재무제표 21개 Factor의
`XGBRanker(rank:ndcg)`로 시가총액 상위 200 중 Top 30을 만든다. Agent C는 40세션 OHLCV의
실제 LSTM 변동성 분기와 1D CNN 2대1 성공확률 분기를 사용한다. Agent D는 B Top 30 안에서만
C가 진입과 비중을 결정하는 직렬 구조를 사용한다. 결합 가중치는 과거 개발자료의 nested anchored
walk-forward Train 내부에서만 선택하고, 단일 모델·가중치·임계값·hash를 동결한 뒤 2026-08-27
이후 새로 도착하는 자료에서만 독립 shadow 증거를 축적한다.

KIS 모의투자는 역사적 Test를 대체하지 않는다. 초기에는 신호와 주문 의도만 기록하며 네트워크와
주문 전송은 모두 금지한다. shadow 감사 후 사용자 별도 승인이 있어야 모의계좌 주문 단계로 이동한다.
이미 관측한 forward 기간은 후속 모델의 독립 OOS로 재사용하지 않는다.

## DEC-092 — Agent B3 XGBRanker 실행 결과 (2026-08-26)

`EXP-20260826-014`에서 표준 21개 Factor 패널을 XGBRanker `rank:ndcg`로 학습했다. 날짜별
query group과 정수 relevance를 사용하고 XGBoost 3.4.1, `ndcg_exp_gain=false`를 고정했다.
2019~2023 anchored fold의 평균 Rank IC는 약 -0.00253, 양의 연도는 1/5로 기존 Ridge B2의
0.03284 및 3/5보다 낮았다. 따라서 B3를 Agent B 대체 모델이나 Agent D 입력으로 승격하지
않고 산출물만 보존한다. 기존 B2 결과와 연구 규칙은 변경하지 않는다.

## DEC-093 — v2 라벨·점수 universe·체결·평가 오류의 버전 수정 (2026-08-31)

- 상태: Confirmed
- 결정 주체: 사용자
- 관련 Experiment: `EXP-20260831-001`
- 결정: reset/action 교차 라벨, 미래 label 존재 여부에 따른 점수행 제거, t+1 실제 시가를 본 뒤 주문을 삭제하는 gap veto, 날짜별이 아닌 연도 전체 Top N, purge·embargo 중복 차감, 선택구간 실패를 무시한 machine gate를 새 Phase 5R 계약에서 수정한다.
- 보존: 기존 실험·산출물·registry 값은 삭제·덮어쓰기하지 않고 영향받은 역사적 개발 진단으로 연결한다.
- 승인 기록: 사용자가 오류가 있으면 수정해 일괄 승인하도록 2026-08-31 명시했다.
- Final OOS 영향: 없음. 봉인자료는 접근하지 않는다.

## DEC-094 — Agent B/C 독립 full-universe scoring과 D train-only soft fusion (2026-08-31)

- 상태: Confirmed
- 결정 주체: 사용자
- 관련 Experiment: `EXP-20260831-001`
- 결정: B Top30/80 hard gate를 폐기한다. B와 C는 같은 20세션 비용 차감 active/downside 목표를 독립 예측하고 D는 이전 시점 inner OOF 점수만 양의 Ridge로 결합한다. B 결측은 중립점수와 availability flag로 처리한다.
- 대조군: `B_ONLY`, `C_ONLY`, `D_SOFT_FUSION`을 동일 체결·비용·포트폴리오로 비교하고 D가 C 단독을 개선하지 못하면 결합을 채택하지 않는다.
- 승인 기록: 사용자가 기존 결합의 의미를 확인한 뒤 잘못이 있으면 수정해 승인하도록 2026-08-31 명시했다.
- Final OOS 영향: 없음.

## DEC-095 — 삼성전자·SK하이닉스 제외와 비시총가중 정적 포트폴리오 (2026-08-31)

- 상태: Confirmed
- 결정 주체: 사용자
- 관련 Experiment: `EXP-20260831-001`
- 결정: `KRX_COMMON:005930`, `KRX_COMMON:000660`을 전 기간 모델 표본·횡단면 순위·점수·주문에서 제외한다. 시총가중 보유비중과 정의되지 않은 정상/위험 국면을 사용하지 않는다.
- 포트폴리오: 거래대금 Top50 동일비중 core 70%, 모델 Top10 추가비중 20%, 현금 10%를 20세션마다 고정 적용한다.
- 평가: 공식 KRX1028, 두 종목 제외 cap proxy, 동일 Top50 neutral core, exposure-matched KRX1028을 함께 보고해 제외효과와 모델 alpha를 분리한다.
- 승인 기록: 사용자가 두 대형주를 매수하지 않고도 공식 KOSPI 200에 선방하는지를 연구목적으로 명시하고 수정안을 일괄 승인했다.
- Final OOS 영향: 없음.

## DEC-096 — 소비 개발 후보와 최종 Phase 5 통과 증거 분리 (2026-08-31)

- 상태: Confirmed
- 결정 주체: 사용자
- 관련 Experiment: `EXP-20260831-001`
- 결정: 2004~2023은 학습·nested 진단용 소비 개발자료다. 이 기간의 gate 통과는 동결 후보만 만든다. 최종 Phase 5 통과는 동결 후 새 forward 252거래일·30건 청산과 모든 무결성·경제 gate를 요구한다.
- 사후변경: 결과 확인 후 같은 Experiment의 Feature·가중치·기간·gate를 변경하지 않는다.
- 승인 기록: 2026-08-31 수정 Phase 5R 일괄 승인.
- Final OOS 영향: 없음. 기존 봉인 OOS는 계속 금지한다.

## DEC-097 — Phase 4E model-only 선행과 Phase 5R predict-only 순서 정정 (2026-09-01)

- 상태: Confirmed
- 결정 주체: 사용자
- 관련 Experiment: `EXP-20260831-001`, `EXP-20260901-001`, `EXP-20260901-002`
- 결정: 먼저 `EXP-20260901-001` Phase 4E에서 실제 `exit_date <= 2020-12-31`인 완성 라벨만으로 B/C/D OOF 모델을 선택하고 실제 fitted bundle·component hash를 동결한다. 포트폴리오·주문·백테스트는 Phase 4E에서 금지한다. 그 뒤 `EXP-20260901-002` Phase 5R은 동결 bundle을 검증해 2021~2023 소비 개발자료에서 선택 primary 하나만 predict-only로 평가하며 model fit·calibration·B/C/D 재선택을 금지한다.
- 기존 기록 보존: 모델 fit과 포트폴리오를 한 단계에 묶어 사전등록했던 `EXP-20260831-001`은 실행·결과 생성 전에 superseded됐다. registry 행과 명세 이력은 삭제하거나 결과가 있었던 것처럼 바꾸지 않고 `NOT_RUN` 상태로 보존한다.
- 증거 경계: 2021~2023 Phase 5R 통과는 소비 개발 포트폴리오 후보일 뿐이다. 최종 Phase 5 통과는 모델·포트폴리오·비용 hash 동결 뒤 새로 도착한 forward 자료에서만 판정한다.
- 승인 기록: 사용자가 2026-09-01 Phase 5R을 바로 실행하지 말고 Phase 4 데이터 경계에서 AI 모델을 먼저 만들도록 순서를 명시적으로 정정했다.
- Final OOS 영향: 없음. 기존 2024~2025 봉인자료는 계속 접근하지 않는다.

## DEC-098 — 미해결 Corporate Action 신규진입 차단과 causal 강제청산 (2026-09-01)

- 상태: Confirmed
- 결정 주체: 사용자
- 관련 Experiment: `EXP-20260901-001`, `EXP-20260901-002`
- 결정: 조건이 확인되지 않은 corporate action을 관측 가격·상장주식 수만으로 split·reset 또는 교환비율로 추정하지 않는다. filing 다음 첫 실제 KRX 세션부터 현재 PIT membership spell 종료일까지 해당 security의 신규진입을 차단한다. 이후 조건이 명확해져도 같은 spell 안에서는 결과를 보고 재허용하지 않는다.
- 기존 보유: filing 시점에 이미 보유 중인 포지션은 filing 정보가 알려진 뒤 만들 수 있는 다음 causal open 강제청산 주문으로 종료한다. 예정 세션에 거래정지·가격 누락으로 체결할 수 없으면 stale 보유를 명시하고 최초 후속 tradable open까지 이월하며 commission·slippage·법정 세금을 정상 적용한다.
- 라벨·시점: 차단기간에 가상 진입하는 학습 라벨과 unresolved event를 가로지르는 라벨은 무효화한다. filing 이전 Feature·신호·체결·성과를 소급 변경하지 않고, 미래 가격을 보고 차단일·청산일·경제조건을 선택하지 않는다.
- 대안 기각: 관측된 주식 수와 가격의 역관계만으로 경제조건을 복원하거나, 미해결 상태에서도 신규매수를 허용한 뒤 사후 보정하는 방식은 사용하지 않는다.
- 승인 기록: 사용자가 2026-09-01 미해결 corporate action의 reset 추정 금지, membership spell 종료까지 신규진입 차단, 기존 보유의 다음 causal open 강제청산을 명시했다.
- Final OOS 영향: 없음. 이 규칙은 Phase 4E·5R의 개발 계약이며 봉인 OOS 접근을 허가하지 않는다.

## DEC-099 — Phase 4E Universe·cutoff·선택 gate 정정 (2026-09-01)

- 상태: Confirmed
- 결정 주체: 사용자
- 관련 Experiment: `EXP-20260901-001`, `EXP-20260901-002`
- 승인 근거: 사용자의 사전 일괄 수정 승인 범위에 따른 최종 실행 전 계약 정정이다. 사용자가
  아래 세부 규칙을 각각 별도로 명시 승인한 것으로 표현하지 않는다.
- cutoff: Phase 4E의 물리 입력, fit 정보와 유효 label exit 최대일은 실제 마지막 KRX 세션
  `2020-12-30`으로 통일한다.
- Universe: 신호일 전체 eligible `U_t`를 B/C/D OOF scoring과 percentile에 유지한다.
  `label_valid`는 fit·metric target에만 적용하고 현재 score Universe를 제거하지 않는다.
- 기간 역할: 2017~2018 B/C OOF는 D meta-training에만 쓰고, 2019~2020은 primary selection에
  사용한다.
- 선택: 먼저 B/C를 mean IC, 비음수 연도 수, mean Top10, 단순성 `C_ONLY`→`B_ONLY` 순으로
  정렬한다. D는 최선 단독보다 mean IC가 엄격히 높고 비음수 연도 수와 mean Top10이 비열등하며,
  2019·2020 양쪽 D OOF, inner-OOF 입력, 비음수 계수를 모두 만족할 때만 선택한다.
- gate 실패 보존: 모델 gate 실패도 세 estimator와 감사 산출물을 재현 가능하게 보존하고
  `phase4e_model_gate_pass=false`로 기록한다. 사전 승인 범위의 Phase 5R predict-only 진단은
  허용하되 `phase5_gate_pass=false`를 상속한다.
- hash 계약: 단일 frozen bundle의 B/C/D estimator component hashes와 bundle·canonical tree·
  manifest·runtime hashes를 pin한다.
- Final OOS 영향: 없음. 2021~2023은 소비 개발 진단이고 기존 봉인 OOS는 접근하지 않는다.

## DEC-100 — DEC-098 실행 전 superseded와 미해결 CA evidence-only 전환 (2026-09-01)

- 상태: Confirmed
- 결정 주체: 사용자
- 관련 Experiment: `EXP-20260901-001`, `EXP-20260901-002`
- 승인 근거: 사용자의 사전 일괄 수정 승인에 따른 실행 전 오류 정정이다. 사용자가 DEC-098의
  filing 기반 차단·강제청산을 별도로 명시 승인했다고 표현하지 않는다.
- superseded: DEC-098은 관련 코드·실험 실행 전에 superseded한다. 기록은 삭제·수정하지 않고
  append-only 이력으로 보존하되 실행 계약으로 사용하지 않는다.
- 근거: 미해결 corporate action 파일의 16,151건(유상증자 8,755건 포함)은 신뢰할 수 있는
  effective date, ratio와 PIT identity가 없는 후보다.
- 결정: 해당 파일은 evidence·hash·count 감사에만 사용한다. filing timing으로 신규진입을
  차단하거나 reset·label 경계·강제청산을 만들지 않는다.
- 유효 경계: 실제 가격과 상장주식 수의 inverse mechanical reset 및 membership·identity gap만
  Phase 4E label과 Phase 5R 거래 무결성 경계로 사용하며 경제조건은 추정하지 않는다.
- Final OOS 영향: 없음. 개발 계약 정정이며 봉인 OOS 접근을 허가하지 않는다.

## DEC-101 — Phase 4E Agent B all-missing Feature 구현 coverage 정정 (2026-09-01)

- 상태: Confirmed
- 결정 주체: 사용자
- 관련 Experiment: `EXP-20260901-001`, `EXP-20260901-002`
- 발생 시점과 증거: Phase 4E 첫 실행은 2017 B fold의 YoY growth Feature 5개가 Train에서
  전부 결측인 상태를 기존 imputer 구현이 처리하지 못해 model fit, metric 계산과 산출물 생성
  전에 중단됐다. 모델 성과나 선택 결과는 관찰되지 않았다.
- Agent B 계약: `SimpleImputer(strategy="median", keep_empty_features=true)`를 사용한다.
  fold Train에서 전부 결측인 Feature도 삭제하지 않고 imputer `0`→`StandardScaler` zero-effect로
  처리하며 해당 fold Ridge 계수를 `0`으로 둔다. 모든 fold와 final fit의 Feature 순서는
  사전등록 20개를 유지한다.
- C/D 계약: C 필수 Feature 또는 D meta-input이 fold Train에서 전부 결측이면 대체 규칙을
  새로 만들지 않고 fail-closed한다.
- 재실행: 수정된 code/config와 runtime을 새 hash로 다시 동결하고 registry의 같은
  `EXP-20260901-001`을 재실행할 수 있다. 이는 성과 확인 뒤 재조정이나 새 모델 선택이 아니라
  pre-fit·pre-output 구현 coverage 정정이다.
- Phase 5R 영향: 새로 동결된 bundle hash와 B의 20개 Feature·imputer·scaler 계약을 검증한 뒤에만
  동일한 predict-only 계약으로 진행한다.
- Final OOS 영향: 없음. 2021년 이후 개발자료와 봉인 OOS에는 접근하지 않았다.

## DEC-102 — Phase 4E v1 bundle reload 해시 호환성 계약 (2026-09-01)

- 상태: Confirmed
- 결정 주체: 사용자
- 관련 Experiment: `EXP-20260901-001`, `EXP-20260901-002`
- 완료 증거: Phase 4E primary와 reproduction은 필수 산출물 `11/11`이 byte-identical했고
  정상 완료·동결됐다. 동결 뒤 모델 변경은 금지한다.
- 발견 사항: sklearn estimator를 동결 bundle에서 reload한 뒤 다시 pickle하면 객체 identity와
  pickle memoization의 영향으로 component/model-state bytes hash가 안정적으로 재현되지 않는다.
  반면 동일 bundle을 reload한 32개 고정 probe prediction은 원본과 bit-identical했다.
- 권위 무결성: bundle SHA-256은
  `da9b8111c3c9c59126746075bc019a5218d33c0259a1c22d0eea00ea3cd3c550`, artifact tree SHA-256은
  `2cb97749c42406bd36d088b8504226a6b86296230ef51a316000156343a813e1`, manifest SHA-256은
  `08bb74b3319a77af8ecc2f1426cb8cde07bc2f68ef44d1f860dde7e83716f6dc`다. manifest의 exact
  runtime versions map, `data_version`, Feature 이름·순서도 함께 권위 계약으로 사용한다.
- 실제 필드 정합성: 사전등록 `diagnostic_allowed` 의미의 실제 필드명은
  `phase5r_predict_only_diagnostic_allowed`다. 실제 Feature contract에는 dtype가 없으므로
  numeric coercion 뒤 비수치·누락·추가 열을 fail-closed하고 정확한 Feature order를 검증한다.
  별도 runtime hash 대신 exact versions map·`data_version`·manifest SHA-256을 pin한다.
- Phase 5R v1 호환성: manifest `component_sha256`의 키 `agent_b`, `agent_c`, `agent_d`와 각 값의
  SHA-256 형식을 확인하고, manifest `model_state_hash`와 config의 `phase4e_model_hash`가
  일치하는지 확인한다. estimator re-pickle hash 비교는 제거한다.
- 변경 허용 근거: Phase 5R은 registry 미등록·미실행 상태이므로 첫 실행 전 verifier
  호환성 정정이 가능하다. 모델·예측·경제규칙은 변경하지 않는다.
- Final OOS 영향: 없음. protected OOS 접근을 허가하거나 발생시키지 않는다.

## DEC-103 — Phase 5R observed split READY 호환성 정정 (2026-09-01)

- 상태: Confirmed
- 결정 주체: 사용자
- 관련 Experiment: `EXP-20260901-002`
- 중단 증거: 첫 Phase 5R 실행은 artifact·metric 0건 상태에서 `2021-04-15` `035720`의
  observed split 처리 중 중단됐다. 해당 `CorporateAction`은 `kind=SPLIT`, ratio와
  cash-in-lieu price를 모두 가졌으나 `source_status`가 `PIT_OBSERVED...` 형식이어서 backtest
  engine의 `READY` exact check를 통과하지 못했다. 경제 결과는 관찰되지 않았다.
- causal 감지: split 판정은 effective-day `open / prior session close`와 같은 두 세션의
  `listed_shares` ratio를 사용한다. effective-day 당일 `close` 사용은 제거한다.
- provenance와 회계 처리: 기존 `action_id`를 유지한다. ratio와 cash-in-lieu price가 완비된
  observed split은 보유수량·원가의 resolved accounting adjustment이므로
  `source_status="READY"`로 engine에 전달한다.
- 불변 범위: 모델, prediction, selection, Feature, threshold, portfolio와 경제 gate는 변경하지
  않는다. Phase 4E code·bundle·artifact에도 영향이 없다.
- 재실행: Phase 5R code/config/data hash를 새로 동결한 뒤 같은 `EXP-20260901-002`를 재실행할
  수 있다. 이는 성과 확인 뒤 재조정이 아니라 pre-output implementation compatibility 정정이다.
- Final OOS 영향: 없음. protected OOS 접근을 허가하거나 발생시키지 않는다.
- 보완 — 격리 범위: legacy Agent D 재현성을 위해 shared `mechanical_actions` 변경은 원복하고,
  causal split 처리는 Phase 5R runner 전용 `_phase5r_mechanical_actions` builder로 격리한다.
- 보완 — 판정 gate: authoritative evaluation sessions에서 동일 ticker의 직전 행이 정확히
  직전 거래 세션이어야 한다. `listed_shares` ratio와 effective-day `open / prior close` ratio는
  finite·positive여야 하며, 기존 최소 20% share 변화와 최대 15% inverse-adjustment 오차 gate를
  모두 통과해야 한다. effective-day `close`는 사용하지 않는다.
- 보완 — provenance·audit: 기존 `OBSERVED-SHARE-RESET` `action_id`를 유지한다. audit에는
  `prior_close`, `effective_open`, `share_multiplier`, `split_adjusted_open_ratio`와
  `uses_effective_day_close=false`를 기록한다.
- 보완 — 검증: Phase 5R 전용 테스트에서 effective-day close mutation 불변성, missing-session
  거부, engine 보유수량 `2→10` 조정과 원장 reconciliation이 통과했다.

## DEC-104 — DEC-103 유효 성과·경제 산출 전 superseded와 Phase 5R CA·identity fail-closed 종료 (2026-09-01)

- 상태: Confirmed
- 결정 주체: 사용자 사전 일괄 수정 승인 범위의 무결성 정정
- 관련 Experiment: `EXP-20260901-002`
- superseded: DEC-103은 유효한 포트폴리오 성과·경제 gate·산출물이 생성되기 전에
  superseded한다. DEC-103 기록은 삭제·수정하지 않지만 실행 계약으로 사용하지 않는다.
- 오류: `listed_shares` 변화와 `effective-day open / prior close`의 역관계만으로 관측
  share reset을 `READY` corporate action으로 확정하면 안 된다. 이 두 값은 유상증자·상장·
  코드 변경·합병 등과 기계적 분할을 단독으로 구별하지 못하며, old-holder의 수량·원가·현금흐름을
  자기금융 방식으로 복원하지 못한다.
- 권위 요건: `docs/V25_KOSPI_RAW_AUDIT_KO.md`에 따라 (1) PIT 안정 종목 identity와 당시
  편입, (2) 원문 공시 또는 구조화 응답의 권리·분할 비율, (3) 효력일과 실제 거래세션,
  (4) KRX 가격·상장주식수의 동일 배율 교차검증이 모두 일치한 승인 terms만 회계상
  corporate action으로 사용할 수 있다.
- 현재 자료 판정: 로더의 `KRX_COMMON:<ticker>`는 ticker 재포장일 뿐 역사적으로 안정된
  security identity 계약이 아니며, 미해결 corporate action 파일에는 승인 가능한 효력일·
  비율·PIT identity가 없다. 관측 가격·주식수 역관계는 Feature·label reset 또는 추가 감사의
  **후보**로만 쓸 수 있고 보유수량·원가·수익률 변환에는 쓸 수 없다.
- 실행 이력: 첫 Phase 5R 시도는 `2021-04-15` `035720` 처리에서, 두 번째 시도는
  `2021-01-15` `020560`을 포함한 EX2 회계 계약 감사에서 각각 중단됐다. 두 시도 모두
  사용자에게 공개하거나 산출물에 기록한 포트폴리오 수익·성과 metric·경제 gate는 0건이다.
- Phase 5R 처리: 미해결 share-reset 후보 또는 안정 identity 공백이 평가 경로에 하나라도
  있으면 backtest engine과 보유수량 조정을 호출하지 않는다. 점수·주문 의도·후보 ledger까지의
  무결성 감사만 허용하고 canonical 포트폴리오·EX2 성과는 `NOT_EVALUATED`로 기록한다.
- EX2: `EX2_PRICE_UNIT_SENSITIVITY`와 `EX2_ISSUER_CAP_VALUE_SENSITIVITY`는 이전 구성종목을
  사후 제거하거나 재가중하지 않는 비자기금융 민감도 진단이다. 둘은 canonical return도,
  수익률 상·하한도, 경제 gate의 대체물도 아니다. `canonical_ex2_return_evaluable=false`이면
  EX2 경제 gate는 자동 실패가 아니라 `NOT_EVALUATED`다.
- 최종 결정: `REJECT_PHASE5R_UNRESOLVED_CA_AND_IDENTITY_CONTRACT`. 공식 KRX1028 대비
  방어력, neutral core 대비 alpha, MDD, 비용 stress와 연도별 성과는 모두 관측·판정하지 않는다.
- 재개 조건: 네 증거 요건을 충족하는 승인 corporate-action terms ledger와 역사적 stable
  identity map을 별도 데이터 버전으로 동결하고, 새 Experiment ID와 실행 전 hash를 등록해야
  한다. Phase 4E 동결 모델·70/20/10 포트폴리오·비용·gate를 2021~2023 결과에 맞춰 바꾸지 않는다.
- Final OOS 영향: 없음. 2004~2023은 계속 소비 개발자료이고 protected OOS 접근은 허가하거나
  발생시키지 않는다.
- 완료 증거: 동결 C_ONLY 점수 143,323행과 차단 주문 의도 3,600건을 생성했으나 engine·성과
  metric·실행 action·외부 주문은 모두 0건이다. 원천 정확한 6자리 ticker의 share-reset 후보
  223건, 로더의 과거 구성종목 집합 후보 86건, 실제 전일·당일 구성종목 사건 37건, 원천
  ticker normalization collision 4개를 기록했다. primary/reproduction 10개 파일은 모두
  byte-identical했다. 후속 2004~2020 원천 감사에서 membership 841,657행의 비정규 ticker와
  실제 Phase 4E membership에 교차한 normalization collision은 각각 0건이었다. 시장 원천의
  비정규 17,916행·전역 collision 4개는 동결 모델 membership 밖이었으며, 이 사실은 Phase 4E
  모델 오염 부재의 보조 증거일 뿐 stable identity·position accounting 승인으로 해석하지 않는다.

## DEC-105 — Phase 4E 미해결 주식수 변화 라벨 경계 누락과 동결 철회 (2026-09-01)

- 상태: Confirmed
- 결정 주체: 사용자의 전반 오류 점검·필요한 모델 규칙 수정 일괄 승인 범위
- 관련 Experiment: `EXP-20260901-001`, `EXP-20260901-002`
- 발견: 기존 `mechanical_reset`은 연속 거래세션의 상장주식수 변화가 20% 이상이면서 가격이
  15% 이내 역배율로 움직인 경우만 경계로 삼았다. 권리조건을 모르는 유상증자·감자·합병 등
  비기계적 주식수 급변은 `unresolved_action=false`로 남아 raw-price 20세션 라벨을 통과했다.
- 실제 영향: 2004~2020 전체 거래소 원천 exact ticker 후보는 4,391건, 로더의 ever-member·
  삼성전자/하이닉스 제외 모집단은 554건, 전일·당일 실제 구성종목 후보는 247건이었다.
  두 종목 제외 전 양일 구성 후보는 248건이며 차이 1건은 삼성전자 `005930`의 2018-05-04
  50:1 액면분할이다. 247건 중 기존 mechanical reset은 40건이었다. OOF 4,876행 중
  11행의 signal~exit 창이 후보를 가로질렀고, 기존 `label_valid=true`인 10행은 모두
  비기계적 후보이자 2019~2020 선택 표본이었다. 최종 fit 유효 23,567행 중에는 75개 고유
  사건을 가로지른 83행이 있었으며 83행 모두 기존 `mechanical_reset=false`였다.
- 민감도: 그 10행만 사후 metric에서 제외해 기존 OOF prediction을 공식 일별 횡단면 Rank IC로
  다시 계산하면 C 평균 0.0263383, D 0.0252909, B -0.0036835로 C 순서는 유지된다. 그러나
  이전 연도 OOF 학습과 2020 fold 학습도 같은 누락 라벨의 영향을 받을 수 있으므로 이 사후
  민감도는 모델 유지 근거가 아니다.
- label-only 재학습 민감도: 누락 83행만 무효화해 같은 OOF 절차를 메모리에서 다시 적합하면
  B 평균 IC 0.0034867(비음수 2/2), C 0.0197609(1/2), D 0.0194729(1/2), 최종 fit
  23,484행, D fit 9,220행이었다. C 연도 IC는 2019년 -0.0297703, 2020년 0.0692920이며
  독립 메모리 실행 2회의 metric은 같았다. model-state hash도
  `725ddd903ea91e5633c476d6f2dedd95a0fda12ab40b1bd97b029f06e0424c64`로 달라졌다.
  기술 Feature segment reset을 아직 적용하지 않은 메모리-only 감사이므로 artifact·모델 후보로
  승격하지 않는다.
- 오류 판정: `EXP-20260901-001`의 동결 결정은
  `SUPERSEDED_PHASE4E_LABEL_INTEGRITY`로 철회한다. 기존 bundle·hash·metric은 삭제하지 않지만
  후속 predict·성과·거래 입력으로 사용하지 않는다. 이를 사용한 `EXP-20260901-002` 점수·주문
  의도도 `SUPERSEDED_PHASE5R_INVALID_PHASE4E_SOURCE`로 보존한다. Phase 5R의 CA·identity
  pre-execution 차단 결론 자체는 유효하다.
- 새 사전등록 규칙: 같은 raw ticker의 연속 거래세션에서 유효한 상장주식수 비율의 절대 로그가
  `log(1.20)` 이상이면 가격 역배율 여부와 무관하게 `UNRESOLVED_SHARE_CHANGE_CANDIDATE`로
  표시한다. 이는 corporate action 종류·권리·배율·보유수량 조정을 확정하지 않는 candidate-only
  경계다. 해당 날을 가로지르는 라벨은 무효화하고 기술 Feature segment도 그 날부터 초기화한다.
- 재실행: 새 Experiment ID, config/code/data hash를 결과 확인 전에 등록한 뒤 Phase 4 OOF 전체를
  재학습·재선택한다. 검증된 새 bundle만 별도 Phase 5 predict-only 감사에 사용할 수 있다.
- Final OOS 영향: 없음. 감사와 재실행은 2020년 이하 소비 개발자료로 제한하고 protected OOS는
  계속 봉인한다.
