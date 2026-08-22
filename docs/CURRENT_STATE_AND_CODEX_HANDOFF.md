# 현재 상태 및 Codex 인계

**갱신일:** 2026-08-23
**목적:** 검증 완료 범위와 다음 승인 경계를 추측 없이 이어받기 위한 문서

## 결론

Phase 0~4는 완료다. 기존 Phase 5 `EXP-20260822-001`의 결과는 그대로 보존되어 있다. 사용자 승인에 따라 별도 Phase 4B `EXP-20260823-001`과 Phase 5B `EXP-20260823-002`를 실행했으며, Development Test는 로드·계산·평가·선택 모두 0행이다.

Selection 후보는 `tree_d3_l002`다. 입력은 `reversal_5` 하나이며, 깊이 3·최소 leaf 2%인 얕은 의사결정나무다. 이는 별도 승인 후 단 한 번 공개할 Development Test 후보일 뿐 거래 후보가 아니다.

새 Phase 5B는 21개 종목변수·5개 시장상태·6개 상호작용을 사용해 매일 종목별 점수와 횡단면 순위를 만들었다. `elastic_a005_l02`가 진단상 최선이었으나 연결 순초과수익률 -11.5013%p, 연도 gate 2/4로 전 후보가 기각됐다. 이 모델은 거래 후보나 Development Test 후보가 아니다.

Phase 5C `EXP-20260823-003`은 이 신호를 고정하고 causal EMA5·상위 10 목표/20위 fallback·20위 이탈·20세션 안전 상한을 적응적으로 진단했다. 연결 순초과수익률은 -1.0274%p로 개선됐지만 turnover 감소 33.87%와 평균 현금 17.61%가 사전등록 gate를 실패했다. Phase 5C 정책도 거래 후보나 Development Test 후보가 아니다.

Phase 5D `EXP-20260823-004`는 사용자 승인에 따라 평균 현금·최소 보유 gate를 제거하고 시장상태별 최대 보유를 risk-on 10, neutral 5, risk-off 0으로 바꿨다. 이미 소비된 2019~2021 재사용 진단에서 평균 보유 4.159개·평균 현금 63.34%로 가변 운용은 작동했지만 전략 -37.65%, 지수 +50.40%, 순초과 -88.05%p로 실패했다. 거래·Development Test 후보는 없다.

## 검증 상태

- 전체 회귀 테스트: 86/86 PASS
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

## Codex Handoff

- 현재 허용 작업: Phase 4B/5B 산출물·manifest·테스트 감사와 문서 검토.
- 사용자 결정을 기다릴 작업: 새로운 저회전율 ranking/portfolio 가설을 별도 Experiment로 설계할지 여부.
- 금지 작업: Development Test 선행 접근, 이번 결과를 보고 동일 Experiment 후보 재선택, Phase 6 시작, Final OOS 접근, 실거래·배포.
