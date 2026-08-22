# 현재 상태 및 Codex 인계

**갱신일:** 2026-08-23
**목적:** 검증 완료 범위와 다음 승인 경계를 추측 없이 이어받기 위한 문서

## 결론

Phase 0~4는 완료다. Phase 5는 `EXP-20260822-001`의 Train/Validation Selection과 독립 재실행까지 완료했으며, Development Test는 로드·계산·평가·선택 모두 0행이다. 따라서 Phase 5 전체 완료나 모델 채택으로 표시하지 않는다.

Selection 후보는 `tree_d3_l002`다. 입력은 `reversal_5` 하나이며, 깊이 3·최소 leaf 2%인 얕은 의사결정나무다. 이는 별도 승인 후 단 한 번 공개할 Development Test 후보일 뿐 거래 후보가 아니다.

## 검증 상태

- 전체 회귀 테스트: 62/62 PASS
- Phase 5 전용 테스트: 12/12 PASS
- Selection과 독립 재실행의 구조화 산출물 8개: byte-identical
- 입력 역할: `phase5_train_validation`
- 최대 로드일: 2021-12-30
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

## 다음 승인 경계

1. Development Test는 사용자 별도 승인 전 실행하지 않는다.
2. 승인하더라도 동결된 `tree_d3_l002` 한 개만 한 번 평가한다.
3. 결과를 본 뒤 Feature, 모델, fold, 비용, 포트폴리오, gate를 변경하지 않는다.
4. Final OOS는 계속 봉인한다.
5. Phase 6 명세·실행을 시작하지 않는다.

## Codex Handoff

- 현재 허용 작업: Selection 산출물·manifest·테스트 감사와 문서 검토.
- 사용자 결정을 기다릴 작업: 단일 Development Test 공개를 수행할지, Validation gate 실패만으로 `rejected`를 확정할지.
- 금지 작업: Development Test 선행 접근, 다른 후보 재선택, 신규 Feature 추가, Phase 6 시작, Final OOS 접근, 실거래·배포.
