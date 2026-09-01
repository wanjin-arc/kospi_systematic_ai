# v2 Phase 4F — 주식수 경계 안전 AI 모델 사전등록 명세

## 1. 단계 식별과 목적

- Experiment ID: `EXP-20260901-003`
- 단계: `v2 Phase 4F`
- 설정: `configs/v2_phase4f_share_change_safe_model.json`
- 선행·대체 대상: `EXP-20260901-001` Phase 4E
- 후속 단계: `EXP-20260901-004` Phase 5S
- 증거 지위: 2004~2020 소비 개발자료를 이용한 모델 전용 재학습·재선택

Phase 4F의 목적은 DEC-105에서 확인한 Phase 4E 라벨·기술 Feature 경계 누락을 수정하고,
동일한 B/C/D 후보와 시간순 OOF 선택 규칙으로 한 개의 재현 가능한 점수모델을 다시 동결하는
것이다. 이 단계는 포트폴리오, 주문, 체결, 수익률 또는 거래 적합성을 평가하지 않는다.

Phase 4E의 bundle·metric·hash는 역사적 오류 증거로만 보존하며 Phase 4F의 학습 초기값,
예측 입력 또는 승격 근거로 재사용하지 않는다.

## 2. 입력과 물리 데이터 경계

허용 입력은 다음으로 제한한다.

- 시점별 실제 KOSPI 200 구성종목: `2004-01-02`~`2020-12-30`
- KRX 일별 OHLCV·거래대금·상장주식수·시가총액: 최대 `2020-12-30`
- 공식 KRX KOSPI 200 지수코드 1028: 최대 `2020-12-30`
- 확정 수치 재무 Factor 패널: 실제 DART 접수일 다음 거래일부터 사용
- 비용표: `configs/kospi_sell_cost_schedule.csv`
- 미확정 corporate-action 후보: evidence·hash·count 감사 전용
- 기존 물리 release: `data/processed/v2_phase4e_ai_model_2004_2020_v2/`

모델·라벨 시작일은 `2011-01-03`, 펀더멘털 시작일은 `2016-03-24`, 학습과 모든 label exit의
최대 허용일은 `2020-12-30`이다. loader가 2021년 이후 행을 반환하면 즉시 중단한다.

`data/sealed/final_oos_v24/`는 경로 열기, 스캔, glob, 행 읽기, 요약, 집계 및 테스트 입력 사용을
모두 금지한다. `final_oos_accessed`는 항상 `false`여야 한다.

## 3. Universe와 identity 경계

Universe는 각 거래일의 실제 PIT KOSPI 200 구성종목이다. 다음 두 보통주는 membership,
모델행, 횡단면 순위, 점수 및 후속 주문 의도에서 모두 제외한다.

- 삼성전자 `005930` / `KRX_COMMON:005930`
- SK하이닉스 `000660` / `KRX_COMMON:000660`

공식 KRX 1028 지수 자체에서는 두 종목을 제거하지 않는다.

모델 identity에 쓰는 ticker는 원천의 정확한 6자리 숫자 `^\d{6}$`만 허용한다. membership의
비정규 raw ticker는 fail-closed한다. 시장 원천의 비정규 ticker를 숫자 추출이나 zfill로 PIT
구성종목 ticker에 변환하지 않으며, 그런 정규화가 구성종목 코드와 충돌하면 즉시 중단한다.
`KRX_COMMON:<ticker>`는 이 단계의 행 키일 뿐 합병·코드 변경을 가로지르는 영구 issuer identity
증거로 해석하지 않는다.

## 4. 주식수 변화와 관측 공백 계약

같은 exact raw ticker의 연속 거래소 세션에서 전일과 당일 상장주식수가 모두 유한한 양수일 때
다음을 만족하면 `UNRESOLVED_SHARE_CHANGE_CANDIDATE`로 표시한다.

```text
abs(log(current_listed_shares / prior_listed_shares)) >= log(1.20)
```

따라서 증가 경계 `1.20`과 로그 대칭 하락 경계 `1 / 1.20`을 모두 포함한다. 후보 판정은
상장주식수만 사용하며 시가·종가 또는 가격 역배율을 사용하지 않는다.

전일 또는 당일 상장주식수가 결측, 무한, 0 또는 음수이면 이를 기업행동으로 추정하지 않고
`LISTED_SHARES_OBSERVATION_GAP`으로 표시한다. 최초 유효 관측은 이전 비교값이 없다는 이유만으로
공백으로 만들지 않는다.

두 경계의 처리 규칙은 다음과 같다.

1. signal일부터 exit일까지 후보 또는 관측 공백을 가로지르는 라벨은 무효화한다.
2. 무효 라벨의 모든 target 값은 비운다.
3. 후보일 또는 관측 공백일에서 종목 기술 Feature segment를 초기화한다.
4. 초기화 전 가격·수익률 이력이 초기화 후 rolling Feature에 들어가지 않게 한다.
5. 후보는 종류·효력일·권리·배율을 확정하지 않는 감사 증거다.
6. 후보에서 executable `CorporateAction`, 보유수량 조정, 현금배분 또는 강제청산을 만들지 않는다.
7. 가격과 상장주식수의 역관계로 별도 기록하는 `mechanical_reset`은 후보의 부분집합이어야 하며,
   후보 자체를 대체하지 않는다.

미확정 DART filing date는 reset·차단·강제청산·label timing 경계로 사용하지 않는다.

## 5. 신호·라벨과 시간 규칙

- 일봉 Feature는 `t`일 장 종료 뒤 계산한다.
- 진입 기준은 `t+1` 시가, 종료 기준은 `t+21` 시가이며 보유기간은 20거래세션이다.
- signal close 대비 5% 초과 gap 매수는 미체결 라벨로 처리한다.
- 비용 차감 종목수익률에서 공식 KRX 1028 동기간 수익률을 빼고, 20세션 MAE의 0.5배를 추가로
  차감한 `target_quality_20`을 예측한다.
- membership/identity, 필수 OHLC, 지수 시가, 비용일자, 주식수 후보·공백 경계 중 하나라도
  불완전하면 라벨을 fail-closed한다.
- label availability와 값은 score Universe 구성에 사용하지 않는다.
- random split은 금지하고 purge·embargo 각각 20세션의 시간순 OOF만 사용한다.

## 6. 모델과 선택 규칙

후보는 설정 파일에 고정된 다음 세 개뿐이다.

- `B_ONLY`: PIT 수치 재무 Factor 20개, 고정 Ridge alpha 10
- `C_ONLY`: causal OHLCV·지수 기술 Feature 17개, 고정 HistGradientBoosting
- `D_SOFT_FUSION`: B/C OOF percentile과 fundamental availability를 양수 Ridge로 결합

B와 C는 서로 독립적으로 종목 점수를 만들고 D는 B/C의 OOF 점수를 soft fusion한다. B는 C의
선필터나 hard gate가 아니다. 모든 preprocessing과 D 결합 적합은 각 Train 내부에서만 수행한다.

OOF 연도는 2017~2020이고 선택 지표는 2019~2020에서만 계산한다. 우선순위는 평균 Rank IC,
비음수 연도 수, Top10 평균 target quality, 단순성이다. D를 선택하려면 최선 단일 모델보다 평균
Rank IC를 엄격히 개선하고, Top10 quality와 비음수 연도 수에서 열등하지 않아야 한다.
포트폴리오 성과는 선택에 사용하지 않는다.

model gate는 양의 평균 Rank IC, 2개 선택연도 평가, 최소 1개 비음수 연도, 유한 Top10 quality,
정확한 score Universe와 D inner-OOF 계보를 요구한다. gate가 실패해도 최선 진단 모델과 실패
증거를 동결할 수 있으나 거래·성과 후보로 승격하지 않는다.

## 7. 실행 전 사전등록과 hash 동결

결과를 보기 전에 `experiments/registry.csv`에 `EXP-20260901-003`이 정확히 한 행 존재해야 하며
상태는 `preregistered`여야 한다. preflight가 계산한 다음 값을 그대로 동결한다.

- `code_hash`
- `config_hash`
- `data_version`
- `model_hash=TRAINING_PENDING`
- `final_oos_accessed=false`

`data_version`에는 물리 release manifest·입력 tree·최대일·비용표·runtime과 함께 gross ratio
1.20, listed-shares-only 후보, candidate-only 의미, 라벨 무효화 및 기술 segment reset 정책을
포함한다. source, config, 데이터 또는 runtime이 바뀌면 기존 hash를 폐기하고 실행 전에 다시
동결한다. registry는 본 실행과 reproduction이 모두 끝날 때까지 `preregistered` 상태를 유지한다.

## 8. 산출물

본 실행은 `artifacts/v2_phase4f_share_change_safe_model/`, 독립 재현은
`artifacts/v2_phase4f_share_change_safe_model_reproduction/`에 쓴다. 각 root는 새 디렉터리여야
하며 최소 다음 파일을 포함한다.

- `frozen_model_bundle.pkl`
- `selection_metrics.csv`
- `oof_scores.csv.gz`
- `audit.json`
- `label_audit.json`
- `fold_boundaries.json`
- `feature_contract.json`
- `component_hashes.json`
- `selected_primary.json`
- `decision.json`
- `manifest.json`

manifest는 schema `v2-phase4f-share-change-safe-model-release-v1`, Experiment ID, primary,
model-state·component·bundle·artifact-tree·입력 hash, Feature 순서, fit/exit 최대일, 경계 감사와
OOS 비접근을 기록한다. manifest를 제외한 두 artifact tree의 필수 파일은 byte-identical해야 한다.

## 9. 테스트와 실행 명령

PowerShell에서 project Python과 `PYTHONPATH=src`를 사용한다.

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_kospi200_phase4f*.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m kospi200_phase4f.cli preflight --config configs/v2_phase4f_share_change_safe_model.json
.\.venv\Scripts\python.exe -m kospi200_phase4f.cli run --config configs/v2_phase4f_share_change_safe_model.json --output artifacts/v2_phase4f_share_change_safe_model
.\.venv\Scripts\python.exe -m kospi200_phase4f.cli run --config configs/v2_phase4f_share_change_safe_model.json --output artifacts/v2_phase4f_share_change_safe_model_reproduction
```

핵심 테스트는 exact raw ticker, 정규화 충돌 거부, gross ratio 양방향 경계, 가격 독립 후보,
상장주식수 관측 공백, 라벨 crossing 무효화, target 제거, 기술 segment reset, 기존 Phase 4E/5R
모듈 byte 보존, 제외 종목, 시간 경계, registry hash와 결정론적 산출물을 검증한다.

## 10. 완료 조건

다음을 모두 만족하면 Phase 4F 실행을 완료로 기록한다. model gate 통과와 단계 실행 완료는 서로
다른 판정이다.

1. 전용 테스트와 전체 회귀 테스트가 통과한다.
2. preflight와 registry의 code/config/data hash가 정확히 일치한다.
3. 최대 입력·fit·exit가 `2020-12-30`을 넘지 않는다.
4. 삼성전자·SK하이닉스 학습행·점수·순위가 0이다.
5. 유효 fit 라벨의 share-change crossing과 listed-shares gap crossing이 각각 0이다.
6. 유효 Selection 행의 두 경계 crossing과 기술 pre-boundary history leakage가 0이다.
7. executable corporate action, 포트폴리오 접근, 주문, 2021+ fit, OOS 접근이 모두 0이다.
8. B/C/D 실제 fitted state와 model-state·bundle·tree·runtime hash가 기록된다.
9. primary/reproduction 필수 파일이 byte-identical하다.
10. 실제 결과와 gate 판정을 registry와 `v2_phase_4f_report.md`에 사실대로 기록한다.

## Codex Handoff

- 구현: `src/kospi200_phase4f/`, `src/kospi200_phase5s/`의 공유 안전 loader 계약,
  `configs/v2_phase4f_share_change_safe_model.json`, Phase 4F 테스트
- 실행 전: 전용·전체 테스트, preflight, registry `EXP-20260901-003` hash 동결
- 실행: primary와 reproduction을 같은 동결 상태에서 각각 한 번 수행
- 검증: label/technical boundary, 제외 종목, cutoff, model/bundle/tree hash와 byte determinism
- 후속 허용: 검증된 Phase 4F primary artifact hash를 Phase 5S config에 고정한 뒤 predict-only 감사
- 금지: 기존 Phase 4E bundle 재사용, 결과 기반 Feature·모델·threshold 변경, 포트폴리오 평가,
  protected OOS 접근, 실제 주문·배포
