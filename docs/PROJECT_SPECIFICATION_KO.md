# KOSPI 100 Technical Systematic AI 프로젝트 명세

**기준일:** 2026-08-22
**근거:** 저장소 파일, 실행 가능한 테스트, Phase 1 v24 감사, Phase 2·3 산출물, Phase 4 물리 입력 재검증
**상태:** Phase 0~4 완료, Phase 5·5B·5C·5D·5E·5F 연구 후보 모두 성과 실패, 거래 후보 없음

## 1. 목적과 역할 분담

목표는 KOSPI 100의 과거 시점별 실제 구성종목을 대상으로, 미래정보 없이 반복 실행 가능한 차트 기반 자동매매 시스템을 만들어 Walk-Forward, 최종 OOS, 500만 원 모의투자, 소액 실거래까지 연결하는 것이다.

- ChatGPT Work: 가설, 연구 설계, 변수 카드, 결과 분석, 채택·폐기 결정, 단계 명세 작성
- Codex: 저장소 코드 구현, 테스트, 리팩터링, 재현 실행, 자동화, CI와 배포 보조
- Git 저장소: 코드·명세·설정·실험 기록의 단일 기준 저장소

AI는 차트를 주관적으로 보고 주문하지 않는다. 모든 조건은 계산식, 입력, 계산 가능 시점, 코드, 테스트, 채택 기준으로 변환돼야 한다.

## 2. 변경하면 안 되는 연구 규칙

| 영역 | 확정 규칙 |
|---|---|
| Universe | 동시점 실제 KOSPI 100 구성종목. 현재 구성종목의 과거 소급 적용 금지 |
| 투자 | Long-only, 현금매매, 공매도·신용·레버리지·파생 금지, 현금 보유 허용 |
| Factor | OHLCV, 거래대금, KOSPI 100 지수, 동시점 Breadth와 기술적 파생변수만 사용 |
| 제외 정보 | 재무제표, DART 공시내용, 뉴스, 가치평가, 업종·기업 텍스트 |
| 신호 시점 | `t`일 공식 장 종료 뒤 `t`까지의 정보만 사용 |
| 체결 시점 | `t+1` 거래일 이후. 기본은 다음 날 시가 및 사전 고정 gap cap |
| 일봉 순서 불명 | 손절·익절이 모두 닿으면 STOP_FIRST |
| 분봉 시점 | 완성된 bar만 사용. 미완성 bar의 High/Low/Close/Volume 금지 |
| 가격 역할 | Raw 가격은 체결·원장, Point-in-Time 연속 가격은 Feature. Raw 덮어쓰기 금지 |
| 검증 | 시간 순서 분할, 필요 시 purge/embargo, Random split 금지 |
| 선택 | 변환·변수 선택·임계값·모델 적합은 Train 내부에서만 수행 |
| 실험 | 결과 확인 전 Experiment ID와 가설·후보군·선택 기준 등록 |
| 복잡도 | 규칙→선형→제한 Tree→Boosting→Ranking→필요 시 결합→딥러닝 순서 |
| 채택 기준 | ML 지표는 보조. 비용 차감 OOS Portfolio 성과와 위험 안정성이 최종 기준 |

기존 Point-in-Time Universe, Corporate Action 처리, 일봉 구조, Data Audit, data contract, Phase 0~3 결정은 치명적 오류가 없으면 소급 재설계하지 않는다. 오류 수정 시 이유·영향 범위·전후 차이를 결정 로그에 남긴다.

## 3. 연구 구간과 보호 규칙

| 구간 | 기간 | 사용 |
|---|---:|---|
| Train | 2011–2018 | 초기 변환·가설·모델 적합 |
| Validation | 2019–2021 | 사전 등록 후보 선택·기각 |
| Development Test | 2022–2023 | 동결 후보의 제한된 확인 |
| Final OOS | 2024–2025 | Phase 8에서 동결 릴리스에 한해 1회 평가 |
| Live shadow | 2026 이후 | 모의·실거래 운영 증거 |

`data/sealed/final_oos_v24/`는 Phase 8 전 개발 코드와 도구가 읽어서는 안 된다. 저장소 내 경로명 차단만으로는 충분하지 않으므로 실제 Git 전환 시 봉인 데이터는 코드 저장소 밖의 읽기 제한 위치로 옮기고, Git에는 해시 manifest와 스키마 계약만 둔다.

## 4. 데이터 현황과 구조

### 4.1 Phase 1 v24 감사로 확인된 전체 자료

- 구성종목: 393,874행, 3,939거래일, 174개 종목, 2010-01-04~2025-12-30
- 전체 일봉: 633,766행, 174개 종목, 2008-01-02~2025-12-30
- Feature panel: 435,683행, rank eligible 392,966행, warm-up 41,809행
- KOSPI 100 지수: 3,939행
- Corporate Action: 98건(기계적 조정 42, continuity reset 56)
- 분봉: 1분 159파일·29,367,959행, 5분 159파일·15,027,364행
- 1분→5분 겹치는 구간의 159개 전 종목/지수 집계값 정확히 일치
- 독립 Phase 1 감사: PASS

개발 파티션은 2023년까지 물리 분리돼 있다. Phase 3가 실제 로드한 행은 Feature panel 384,245, 전체 일봉 555,949, 지수 3,453, Corporate Action 88, 편출 실행 69이다.

### 4.2 핵심 일봉 테이블

| 파일 | 키/주요 컬럼 | 역할 |
|---|---|---|
| `membership_daily.csv.gz` | `date, security_id, ticker, name, membership_spell_id, is_member, eligible_new_entry, tradable` | 날짜별 실제 Universe와 신규 진입 가능 여부 |
| `full_history_ohlcv.csv.gz` | 위 식별/상태 + `open, high, low, close, volume, trading_value, feature_volume, feature_trading_value, price_usage_role` | Raw 체결 가격과 전체 이력 |
| `feature_price_panel.csv.gz` | 전체 일봉 + `warmup_for_spell_ids, model_price_role, rank_eligible` | 가입 전 warm-up 포함 Feature 계산 패널 |
| `index_ohlcv.csv.gz` | `date, open, high, low, close, volume_thousand_shares, trading_value_million_krw, market_cap_source_field` | Benchmark와 Regime 입력 |
| `corporate_actions.csv.gz` | event ID, security ID, event type, feature handling/boundary, share/price multiplier, portfolio handling/terms | Feature 연속성과 보유 포지션 의무 처리 |
| `removal_execution.csv.gz` | membership spell, last member date, first nonmember session, execution date/open, qty multiplier, action | 편출 포지션의 실행 처리 |

고유 종목 식별자는 `security_id`다. `ticker`는 문자열이며 영문이 포함될 수 있으므로 정수 변환이나 문자 제거를 금지한다. 이름만으로 동일 종목을 판정하지 않는다.

### 4.3 Point-in-Time 및 전처리 계약

- Ranking은 해당 날짜 `is_member=true`, `eligible_new_entry=true`인 행만 사용한다.
- 가입 전 가격은 warm-up Feature에만 쓰고 가입 전 Ranking·매수에는 쓰지 않는다.
- 기계적 Corporate Action은 `as_of_date >= feature_boundary_date`일 때만 알려진 multiplier를 Feature window에 적용한다. Raw OHLCV는 변경하지 않는다.
- Reset event는 boundary를 넘는 rolling price/return Feature를 금지하고 새 segment에서 다시 시작한다.
- 편출 뒤 가격은 청산 실행에만 쓰며 Ranking에는 쓰지 않는다.
- 모델·체결 가격은 유한하고 양수인 OHLC 및 해당 `tradable`/eligibility flag를 요구한다.
- 거래정지 proxy인 `tradable=false`는 실행 가격에서 제외하지만 Raw 행은 감사용으로 보존한다.
- 일별 `trading_value / volume`은 정규장 VWAP로 해석하지 않는다.
- 분봉 Raw CSV.GZ는 불변이다. 정제·resample·Feature는 별도 파생 계층에 쓴다.
- 분봉 결측을 0이나 no-signal로 대체하지 않는다. 분봉 모델 표본에서만 제외하고 일봉 PIT Universe에서는 유지한다.
- 분봉 결과는 보유 종목·날짜 coverage와 제외 이유를 반드시 보고하고, 전체 역사 KOSPI 100 결과로 과장하지 않는다.

### 4.4 분봉 Coverage 주의

- 파일 가용 종목 158/174, 나머지 16개는 공급자 수집 실패 기록
- 일봉 종료일까지 1분 tradable member-day coverage 약 99.965%, 5분 약 99.331%
- 1분 주요 누락은 `0126Z0` 코드 수집 오류 12일
- 5분 주요 누락은 `003410` 722일과 `0126Z0` 12일
- 누락은 비무작위이므로 동일 표본의 단순 Entry baseline과만 비교한다.

## 5. 단계별 실제 구현 상태

| 단계 | 상태 | 확인된 구현 | 미구현/남은 항목 |
|---|---|---|---|
| 0 연구 규칙 | 완료 | Charter, protocol, bias checklist, decision log, registry schema | 새 규칙은 이후 결정 로그로만 추가 |
| 1 Data & Audit | 완료(v24 PASS) | PIT membership, 일봉/지수, CA, 편출, 분봉 QA, 물리 파티션, guarded access | 실운영용 DB/Parquet 전환은 미확인; OOS 물리 권한 강화 필요 |
| 2 Backtest engine | 완료 | Long-only/정수주/현금, 비용·세금·슬리피지, gap, halt, partial fill, stop/target, CA, 원장·metrics·reconciliation, deterministic output | 호가 깊이·실제 auction·broker semantics는 Phase 9 전 검증 |
| 3 Rule baseline | 완료 | SMA200 + 126일 초과모멘텀, 9개 조합, Validation-only 선택, Development Test 1회 | 거래 후보 탈락. 기준선으로만 유지 |
| 4 Feature research | 완료 | 21개 횡단면·5개 regime 변수, PIT/CA-aware feature·label, 단변량 IC/HAC/coverage/중복 평가, 2021년 이하 물리 입력 경계, 접근 감사, deterministic CLI·산출물 | `reversal_5`만 Phase 5 입력 후보. 모델·포트폴리오·거래 판정은 미수행 |
| 5 Ranking model | Selection/적응적·재사용 진단 완료·후보 기각 | reversal_5 단일 모델, Phase 4B/5B 다변수 모델, Phase 5C 점수 지속성, Phase 5D 시장상태별 가변 보유, Phase 5E 절대 알파·양수확률 no-trade | 모두 비용 차감 지수 초과 성과 실패. Development Test 미사용 |
| 6 Entry Timing | 미구현 | 분봉 Raw와 coverage audit만 있음 | 동일 표본 시가/5분/15분 baseline 및 timing model |
| 7 Portfolio/Risk | 미구현 | Phase 2의 실행 원장 기반만 있음 | Regime, exposure, sizing, risk rule, kill switch |
| 8 통합 검증 | 미구현 | 없음 | Walk-Forward, stress, sensitivity, 최종 OOS 1회 |
| 9 모의투자 | 미구현 | 없음 | 증권사 API, 주문상태, 계좌대조, 장애 기록 |
| 10 소액 실거래 | 미구현 | 없음 | 별도 승인과 bounded capital plan |

## 6. 코드와 산출물 역할

| 경로 | 역할/상태 |
|---|---|
| `src/kospi100_data/` | 수집 파일 normalization, schema, Phase 1 pipeline/validation, v24 partition/audit, OOS guarded reader, Phase 4 Train/Validation 물리 파티션 빌더 |
| `src/kospi100_backtest/` | Phase 2 설정, 비용, 주문/체결/원장 엔진, metrics, deterministic I/O, synthetic demo |
| `src/kospi100_baseline/` | Phase 3 데이터 guard, CA-aware Feature, 주문 생성, 9조합 실행·선택, CLI |
| `src/kospi100_features/` | Phase 4 config/features/labels/evaluate/runner/CLI와 물리 입력 fail-closed 감사 |
| `src/kospi100_ranking/` | Phase 5 단일 Feature ranking 모델·포트폴리오 Selection |
| `src/kospi100_multifactor/` | Phase 4B 다변수 Feature 감사와 Phase 5B 일별 횡단면 모델 |
| `src/kospi100_rank_persistence/` | Phase 5C causal EMA·상위 10/20 순위 지속성 정책과 적응적 진단 |
| `src/kospi100_selective_ranking/` | Phase 5D 절대 점수·시장상태 기반 가변 보유와 2019~2021 재사용 진단 |
| `src/kospi100_absolute_alpha/` | Phase 5E 비용 차감 절대 초과수익 Ridge·양수확률 Logistic·no-trade adaptive 진단 |
| `configs/phase1.json` | 초기 Phase 1 논리 build 설정 |
| `configs/phase2_engine.json` | 동결된 Phase 2 실행·원장 설정 |
| `configs/phase3_baseline.json` | Phase 3 후보군·구간·비용·선택 규칙 |
| `configs/phase4_features.json` | Phase 4 원 연구 후보·기간·label·gate 동결 설정 |
| `configs/phase4_revalidation_20260819.json` | 원 연구 설정 hash를 유지한 물리 입력 경계 재검증 wrapper |
| `configs/kospi_sell_cost_schedule.csv` | 날짜별 KOSPI 매도세율 |
| `tests/` | Phase 1~5D 단위·통합·회귀 테스트. 현재 86개 통과 |
| `artifacts/phase2/` | synthetic 원장·metrics·reconciliation. 전략 수익 근거가 아님 |
| `artifacts/phase3/` | 민감도, 선택 결과, 실제 개발 백테스트 원장·metrics·manifest |
| `artifacts/phase4/` | 원 Phase 4 변수 지표·결정·감사·manifest |
| `artifacts/phase4_revalidation_20260819/` | 2021년 이하 물리 입력 경계 재검증 지표·결정·접근 감사·manifest |
| `artifacts/phase5/selection/` | reversal_5 단일 입력 Selection 결과. 거래 후보 gate 실패 |
| `artifacts/phase4b_multifactor/`, `artifacts/phase5b/selection/` | 2018년 이하 다변수 Feature·모델 진단. 전 후보 기각 |
| `artifacts/phase5c/adaptive_diagnostic/` | causal 점수 지속성·저회전율 정책 진단. 정책 기각 |
| `artifacts/phase5d/reused_validation_diagnostic/` | 시장상태별 0·5·10 가변 보유의 2019~2021 재사용 진단. 정책 기각 |
| `artifacts/phase5e/adaptive_diagnostic/` | 절대 순초과수익·양수확률 이중 gate의 2019~2021 adaptive 진단. 모델 기각 |
| `experiments/registry.csv` | 실험 사전 등록 및 결과·해시·결정 기록 |
| `work/v24_stage/phase1_final_v24/` | 1.3GB급 Phase 1 원본/production bundle. Git 추적 대상이 아님 |
| `data/processed/v24/development/` | 2023년까지의 개발 입력. Git 추적 대상이 아님 |
| `data/sealed/final_oos_v24/` | Phase 8 전 읽기 금지. 코드 저장소 밖 보관 권장 |

## 7. 핵심 설계 결정과 이유

- 체결 가능한 label은 `t` close 신호 뒤 `t+1` open 진입을 기준으로 한다. 같은 날 종가 정보를 같은 날 체결에 쓰는 누수를 막기 위해서다.
- 기본 gap cap은 `Close[t] × 1.05`의 사전 주문 상한이다. 실제 시가를 본 뒤 유리하게 취소하는 사후 판단을 막는다.
- 비용은 편도 commission 2bp, adverse slippage 10bp, 날짜별 법정 매도세를 사용한다. 비용 없는 성과를 채택하지 않는다.
- Raw 체결 가격과 Feature 연속 가격을 분리한다. 미래 Corporate Action이 과거 Feature를 임의로 다시 쓰는 것을 막는다.
- Corporate Action 조건이 불명확한 보유 포지션은 fail-closed다. 권리·합병 비율을 추측하지 않는다.
- Phase 3의 `H=20, N=10`은 Validation net Sharpe가 9개 중 가장 높아 선택됐을 뿐, 수익성 증거가 아니다.
- Phase 3 결과: Validation 전략 -11.43%, KOSPI100 +50.40%, 초과 -61.82%p; Development Test 전략 -10.35%, KOSPI100 -9.23%, 초과 -1.12%p. 기준선은 재현용으로 채택, 거래 후보는 탈락했다.
- Phase 4는 모델을 학습하지 않고 단변량 방향·coverage·HAC 안정성·연도 안정성·중복만 평가하도록 사전 등록됐다.
- Phase 4 결과는 `reversal_5` 한 개만 사전 등록 gate를 통과했다. 이는 Phase 5 입력 후보일 뿐 모델·거래 후보가 아니다.
- Phase 4 연구 입력은 물리적으로 2021년 이하인 전용 파티션으로 고정했고 Development Test loaded/calculated/evaluated/selected가 모두 0임을 감사했다.

## 8. 현재 감사에서 확인된 제한과 다음 조건

1. Phase 4 구현·물리 입력 재검증은 완료됐다. Phase 5·5B·5C는 각 사전등록 범위에서 실행됐으나 거래 후보를 만들지 못했고 전체 회귀 79/79가 통과했다.
2. Phase 5C는 이미 소비된 2015~2018의 적응적 진단이므로 독립 채택 증거가 아니다. Development Test는 모델 연구에 사용하지 않았다.
3. 2021년 이하 물리 파티션은 대용량 파생 데이터라 Git에서 제외한다. 재현에는 허용된 development 원본, 동결된 source manifest와 `kospi100_data.phase4_partition`가 필요하다.
4. 기존 영문 보고서는 과거 기록으로 보존하고 새 보고서와 갱신 문서는 한글로 작성한다.
5. Final OOS는 Phase 8 단일 릴리스 전까지 계속 봉인하며 Phase 4~5C 연구에서 접근하지 않았다.
6. 실운영용 데이터 저장·권한 분리, broker semantics와 외부 서비스 연동은 후속 단계에서 별도 승인·검증이 필요하다.

## 9. 권장 저장소 구조

```text
KOSPI100-AI/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── .gitignore
├── .codex/                    # Codex 로컬 환경/공통 action 설정
├── docs/
│   ├── PROJECT_SPECIFICATION_KO.md
│   ├── RESEARCH_PROTOCOL.md
│   ├── BIAS_PREVENTION_CHECKLIST.md
│   ├── DECISION_LOG.md
│   ├── WORK_CODEX_GIT_WORKFLOW.md
│   ├── STAGE_SPEC_TEMPLATE.md
│   └── stages/
│       ├── phase_3_report.md
│       └── phase_4_spec.md
├── src/
├── tests/
├── configs/
├── experiments/
│   └── registry.csv
├── artifacts/                # 작은 summary/manifest만 Git 추적
├── data/
│   ├── contracts/            # schema, manifest, hash만 추적
│   ├── processed/            # Git 제외
│   └── sealed/               # Git 제외, 가능하면 저장소 밖 권한 분리
└── scripts/
```

Git에는 코드, 문서, 소형 설정, 실험 registry, 요약 CSV/JSON, manifest와 hash를 넣는다. Raw/분봉/ZIP/대형 원장/개발 데이터/OOS/비밀키는 넣지 않는다.
