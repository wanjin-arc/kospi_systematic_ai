# 현재 상태 및 Codex 인계

**갱신일:** 2026-08-22
**목적:** 저장소의 검증 완료 범위와 다음 단계 진입 조건을 추측 없이 이어받기 위한 문서

## 결론

Phase 0~4는 완료다. Phase 4는 2021년 이하 전용 물리 파티션, 실행 전 data hash 고정, 접근 감사, 기존 결과 불변 및 독립 byte determinism을 모두 통과했다. `reversal_5` 한 개만 Phase 5 입력 후보로 유지하며, 이는 모델 또는 거래 후보 채택이 아니다.

`reversal_5` 판정은 모델 또는 거래 후보 채택이 아니다. Phase 5 Ranking 모델은 아직 구현·등록되지 않았으며 사용자 승인과 새 Experiment ID 사전 등록 전에는 시작하지 않는다.

## 확인된 기준 상태

- 전체 회귀 테스트: 50/50 PASS
- Phase 1 v24 독립 감사: PASS
- Phase 2 deterministic engine 및 synthetic reference: 완료
- Phase 3: 19개 전략 reconciliation과 byte-identical 재실행 PASS
- Phase 3 선택: `H=20`, `N=10`, target weight 10%
- Phase 3 결정: 기준선 ACCEPTED, 거래 후보 FAIL
- Phase 4 전용 테스트: 18/18 PASS
- Phase 4 기존 실제 CLI 실행: 결과 보존
- Phase 4 물리 경계 재검증 CLI: PASS
- Phase 4 물리 파티션 독립 재생성: 6개 구성 파일 byte-identical
- Phase 4 재검증 독립 재실행: 8개 구조화 산출물 byte-identical
- Phase 4 결정: `reversal_5`만 `채택_Phase5후보`
- Phase 4 연구의 Development Test loaded/calculated/evaluated/selected: 모두 0행
- 로드 후 날짜 필터링: false
- Final OOS 접근: false

## Phase 4 구현 상태

- 설정: `configs/phase4_features.json`
- 재검증 설정: `configs/phase4_revalidation_20260819.json`
- 실행 API: `kospi100_features.runner.run_phase4`
- 재검증 CLI: `python -m kospi100_features.cli run --config configs/phase4_revalidation_20260819.json --output artifacts/phase4_revalidation_20260819`
- 단계 명세: `docs/stages/phase_4_spec.md`
- 실행 보고서: `docs/stages/phase_4_report.md`
- 구조화 결과: `artifacts/phase4/`
- 물리 경계 재검증 결과: `artifacts/phase4_revalidation_20260819/`
- 물리 파티션 빌더: `kospi100_data.phase4_partition`
- 실험 기록: `experiments/registry.csv`의 `P4-FEATURES-20260818-001`
- 재검증 실험 기록: `P4-REVALIDATION-20260819-001` (`completed`)

교정된 Phase 4 로더는 `phase4_train_validation` 역할, `max_date=2021-12-31`, 파일별 `min_date`·`max_date`·`rows`를 가진 manifest를 데이터 파일 read 전에 검증한다. 허용 파일 네 개만 hash 검증 후 읽고, 실제 날짜와 행 수를 manifest와 다시 대조한다. 로드 뒤 날짜 필터링은 허용하지 않는다. 기존 통합 development 파티션은 데이터 파일 read 전에 거부한다.

실제 입력은 `data/processed/v24/phase4_train_validation_2021/`에 생성돼 있다. 상류 빌더는 허용된 통합 development 파일의 source hash를 검증한 뒤 날짜 열만으로 스트리밍 cutoff를 적용했다. 2022~2023 행은 출력·집계·연구 계산에 보존하지 않았다. 이 준비 행위와 Phase 4 연구 실행을 분리해 기록하며, Phase 4 연구 실행 자체는 물리적으로 2021년 이하인 네 파일만 읽었다.

## Phase 4 결과 요약

- 후보 변수: 21개
- `채택_Phase5후보`: 1개 (`reversal_5`)
- `보류_학습방향불일치`: 16개
- `보류_검증방향불일치`: 2개
- `보류_검증불안정`: 1개
- `보류_연도불안정`: 1개
- 시장상태 변수 5개: 모두 `보류_Phase7`

`reversal_5`의 Validation coverage는 0.9994, 평균 일별 Spearman IC는 0.02439, HAC t값은 1.99이며 2019~2021의 세 연도 평균 IC가 모두 양수였다. 상세 수치는 `docs/stages/phase_4_report.md`와 `artifacts/phase4/feature_metrics.csv`를 따른다.

## 동결 hash

- Phase 4 source: `f199ed4de175c1643877ed064670c15b6618e0010542230f3b60bff265997deb`
- Phase 4 config: `2b65169985cf800c05863191e4f19bcb190865a92bd31b325f5be3f299cd7091`
- Phase 4 data: `b27027d8c4b4271ef9d80058890894791c339891a276d7c0bf747fead697da7f`
- Feature data contract: `4728adbdd7b48077a6e96714c920d541d19cae0e1f73aaaf9c98ebaee6c0aa2d`
- 재검증 source: `868457ef97de3c180bbd5d4edfd5ebe581569241fd4e16df21945577dc003844`
- 재검증 config: `71199d3c36e6d63775cfe5aaad4c8a59c3030f56f6a772130b3be12da0c75317`
- 재검증 data: `69590204b3c35e686267dac81fe1347c0e3639005586da2d2db32e35c76b840f`
- 재검증 artifact manifest: `77992184d3c413a3066be363e442ed1e6de4210ef72b1b1b2cccfbceb9fc2bb6`

## 다음 단계 제한

1. Phase 5는 사용자 명시적 승인 전 시작하지 않는다.
2. Phase 5는 새 단계 명세와 새 Experiment ID를 결과 확인 전에 등록한다.
3. Phase 4 결과를 보고 기존 변수 공식·기간·threshold를 소급 변경하지 않는다.
4. Development Test는 Phase 5의 동결 명세가 허용하는 시점과 용도 외에는 사용하지 않으며, Final OOS는 Phase 8 단일 릴리스 전까지 계속 봉인한다.
5. Phase 5에서도 모델 성능만으로 거래 후보를 주장하지 않고, 동결된 Phase 3 기준선과 동일한 universe·시점·비용·포트폴리오 제약 아래 후속 gate를 적용한다.

## Codex Handoff

- 다음 허용 작업: 사용자 승인 후 Phase 5 명세와 새 Experiment ID를 결과 확인 전에 등록한다.
- 허용 후보 입력: `reversal_5` 한 개. 추가 변수 또는 threshold 변경은 새 가설·Experiment ID가 필요하다.
- 아직 하지 않을 일: 승인 전 Phase 5 모델 학습, 포트폴리오 백테스트, Development Test 조회, Final OOS 접근, paper/live trading.
- 물리 파티션 재생성 명령: `PYTHONPATH=src python -m kospi100_data.phase4_partition --source-root data/processed/v24/development --output-root data/processed/v24/phase4_train_validation_2021`
- Phase 4 재검증 명령: `PYTHONPATH=src python -m kospi100_features.cli run --config configs/phase4_revalidation_20260819.json --output artifacts/phase4_revalidation_20260819`
- 전체 회귀 명령: `PYTHONPATH=src python -m unittest discover -s tests -v`
- 완료 상태: Phase 4 완료. 물리 입력은 `.gitignore` 대상이며 코드·hash·감사 산출물로 재현한다.
