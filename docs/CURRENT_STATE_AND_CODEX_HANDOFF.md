# 현재 상태 및 Codex 인계

**갱신일:** 2026-08-19
**목적:** 저장소의 검증 완료 범위와 다음 단계 진입 조건을 추측 없이 이어받기 위한 문서

## 결론

Phase 0~4는 구현·실행·검증 완료다. Phase 3 기준선은 재현 기준선으로 채택됐지만 거래 후보 성과 gate를 통과하지 못했다. Phase 4는 사전 등록한 21개 기술 변수의 Train/Validation 단변량 화면을 완료했고, `reversal_5` 한 개만 Phase 5 입력 후보로 채택했다.

`reversal_5` 판정은 모델 또는 거래 후보 채택이 아니다. Phase 5 Ranking 모델은 아직 구현·등록되지 않았으며 사용자 승인과 새 Experiment ID 사전 등록 전에는 시작하지 않는다.

## 확인된 기준 상태

- 전체 회귀 테스트: 43/43 PASS
- Phase 1 v24 독립 감사: PASS
- Phase 2 deterministic engine 및 synthetic reference: 완료
- Phase 3: 19개 전략 reconciliation과 byte-identical 재실행 PASS
- Phase 3 선택: `H=20`, `N=10`, target weight 10%
- Phase 3 결정: 기준선 ACCEPTED, 거래 후보 FAIL
- Phase 4 전용 테스트: 11/11 PASS
- Phase 4 실제 CLI 실행: PASS
- Phase 4 독립 재실행: 8개 구조화 산출물 byte-identical
- Phase 4 결정: `reversal_5`만 `채택_Phase5후보`
- Development Test 계산·평가: 0행
- Final OOS 접근: false

## Phase 4 구현 상태

- 설정: `configs/phase4_features.json`
- 실행 API: `kospi100_features.runner.run_phase4`
- CLI: `python -m kospi100_features.cli run --config configs/phase4_features.json --output artifacts/phase4`
- 단계 명세: `docs/stages/phase_4_spec.md`
- 실행 보고서: `docs/stages/phase_4_report.md`
- 구조화 결과: `artifacts/phase4/`
- 실험 기록: `experiments/registry.csv`의 `P4-FEATURES-20260818-001`

Phase 4는 development manifest·partition·파일 hash와 canonical v24 계약을 검증한다. Feature·label·regime 및 평가 계산 입력은 2021-12-31 이하로 제한한다. Train/Validation에 purge 20을 적용하고, 이후 재학습 블록이 없어 실제 embargo 집합이 공집합임을 명시적으로 기록한다. 2022~2023 Development Test와 2024~2025 Final OOS는 선택에 사용하지 않았다.

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

## 다음 단계 제한

1. Phase 5는 사용자 명시적 승인 전 시작하지 않는다.
2. Phase 5는 새 단계 명세와 새 Experiment ID를 결과 확인 전에 등록한다.
3. Phase 4 결과를 보고 기존 변수 공식·기간·threshold를 소급 변경하지 않는다.
4. Development Test는 Phase 5 모델 선택에 사용하지 않으며, Final OOS는 Phase 8 단일 릴리스 전까지 계속 봉인한다.
5. Phase 5에서도 모델 성능만으로 거래 후보를 주장하지 않고, 동결된 Phase 3 기준선과 동일한 universe·시점·비용·포트폴리오 제약 아래 후속 gate를 적용한다.

## Codex Handoff

- 다음 구현 대상: 미등록 상태. 사용자 승인 후 `docs/stages/phase_5_spec.md`부터 확정한다.
- 허용 후보 입력: `reversal_5` 한 개. 추가 변수 또는 threshold 변경은 새 가설·Experiment ID가 필요하다.
- 아직 하지 않을 일: 모델 학습, 포트폴리오 백테스트, Development Test 조회, Final OOS 접근, paper/live trading.
- Phase 4 재현 명령: `PYTHONPATH=src python -m kospi100_features.cli run --config configs/phase4_features.json --output artifacts/phase4`
- 전체 회귀 명령: `PYTHONPATH=src python -m unittest discover -s tests -v`
- Phase 5 완료 조건: 현재 미정이며 Phase 5 명세와 registry 사전 등록으로 먼저 동결해야 한다.
