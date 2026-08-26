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
