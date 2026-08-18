# 현재 상태 및 Codex 인계

**작성일:** 2026-08-18  
**목적:** Codex가 저장소를 처음 열었을 때 추측 없이 현재 상태를 이어받기 위한 진입 문서

## 결론

Phase 0~3은 구현·검증 완료다. Phase 4는 `P4-FEATURES-20260818-001`로 사전 등록됐고 일부 소스가 작성됐지만 실행 가능한 상태가 아니며 결과도 없다. Codex는 이를 “부분 구현”으로 취급해야 한다.

## 확인된 기준 상태

- 전체 회귀 테스트: 32/32 PASS
- Phase 1 v24 독립 감사: PASS
- Phase 2: deterministic engine과 synthetic reference 완료
- Phase 3: 19개 전략 실행 reconciliation 통과, byte-identical 재실행 통과
- Phase 3 선택: `H=20`, `N=10`, target weight 10%
- Phase 3 결정: 기준선 ACCEPTED, 거래 후보 FAIL
- Phase 3 final OOS access 기록: false

## Phase 4에 이미 존재하는 것

- `configs/phase4_features.json`
  - Experiment ID `P4-FEATURES-20260818-001`
  - Train 2011–2018, Validation 2019–2021
  - Development Test와 Final OOS 사용 금지
  - 10거래일 open-to-open KOSPI100 초과 log return label
  - purge 20, embargo 20
  - 횡단면 변수 21개, regime 변수 5개
  - 단변량 IC, HAC t, coverage, 연도 안정성, 중복 gate
  - 모델 학습·Portfolio backtest 금지
- `src/kospi100_features/config.py`
- `src/kospi100_features/features.py`
- `src/kospi100_features/labels.py`
- `src/kospi100_features/evaluate.py`
- `experiments/registry.csv`의 pending 사전 등록 행

## 확인된 결함

- `src/kospi100_features/runner.py` 없음
- `src/kospi100_features/cli.py` 없음
- `src/kospi100_features/__init__.py`가 없는 runner를 import하므로 package import 실패
- registry의 재현 명령이 현재 실행 불가
- Phase 4 단위 테스트와 통합 테스트 없음
- `artifacts/phase4/` 없음
- Phase 4 변수 카드/검증 보고서/결정 결과 없음
- Phase 4의 실제 데이터 계산·평가 결과 없음

## Codex가 Phase 4 재개 요청을 받았을 때의 구현 명세

사용자의 명시적 재개 요청 전에는 아래 작업을 시작하지 않는다.

### 입력

- `data/processed/v24/development/feature_price_panel.csv.gz`
- `data/processed/v24/development/full_history_ohlcv.csv.gz`
- `data/processed/v24/development/index_ohlcv.csv.gz`
- `data/processed/v24/development/corporate_actions.csv.gz`
- `configs/phase4_features.json`
- `work/v24_stage/phase1_final_v24/controls/feature_data_contract_v24.json`

### 구현 대상

1. `runner.py`: development manifest 검증, 데이터 로드, Feature 계산, label 결합, 평가, deterministic write
2. `cli.py`: `run --config --output` 명령
3. 데이터 경계: 경로와 max date를 이중 검사하고 2022년 이후 평가 행을 거부
4. Feature timing/continuity: future bar, CA reset crossing, nonmember ranking 차단
5. 결과 write: 아래 필수 산출물과 hash manifest
6. 테스트: config guard, timing, rolling-session continuity, CA adjustment/reset, label, purge, IC/HAC, redundancy, deterministic output, OOS 경로 거부

### 필수 산출물

- `artifacts/phase4/feature_metrics.csv`
- `artifacts/phase4/annual_ic.csv` 또는 동등한 구조화 결과
- `artifacts/phase4/redundancy_matrix.csv`
- `artifacts/phase4/feature_decisions.csv`
- `artifacts/phase4/regime_feature_audit.csv`
- `artifacts/phase4/data_audit.json`
- `artifacts/phase4/run.json`
- `artifacts/phase4/manifest.json`
- `docs/stages/phase_4_spec.md`
- `docs/stages/phase_4_report.md`
- 갱신된 `experiments/registry.csv`

### 완료 조건

- 기존 32개 회귀 테스트 포함 전체 테스트 통과
- package import 및 registry 재현 명령 성공
- Train/Validation만 사용, Development Test/OOS 미사용 증거
- 각 변수의 공식·입력·주기·lookback·계산 가능 시점·예상 방향·논리·실패 조건·중복·leakage 위험·검증·결정 포함
- 동일 설정 독립 재실행의 결정성 확인
- 모델 학습과 Portfolio backtest를 하지 않음
- 보고서는 한글

## Codex 첫 프롬프트

```text
이 저장소는 ChatGPT Work와 공동으로 사용하는 KOSPI 100 기술적 시스템 트레이딩 프로젝트다.
먼저 AGENTS.md, docs/PROJECT_SPECIFICATION_KO.md,
docs/CURRENT_STATE_AND_CODEX_HANDOFF.md, 현재 단계 명세,
experiments/registry.csv를 읽어라.

연구 규칙과 protected OOS 정책을 변경하지 말고, 현재 단계의 Codex Handoff만 구현하라.
구현 전 실제 코드와 테스트 상태를 확인하고, 불명확한 부분은 추측하지 말고 보고하라.
구현 후 관련 테스트와 전체 회귀 테스트를 실행하고, 실행하지 않은 작업을 완료로 표시하지 마라.
새 보고서는 한글로 작성하라.
```
