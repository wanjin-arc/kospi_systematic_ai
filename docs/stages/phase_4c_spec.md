# Phase 4C KOSPI 전체 시장상태 상호작용 감사 명세

## 승인 범위

DEC-2026-060과 2026-08-25 사용자 승인에 따라 KOSPI 전체의 동시점 OHLCV 단면을 KOSPI 100 기술신호의 시장상태 후보로만 감사한다. KOSPI 전체 종목은 KOSPI 100 Universe를 대체하지 않으며 개별 종목 target, 직접 종목점수, 모델 학습 행으로 사용하지 않는다.

## 물리적 입력 경계

- KOSPI 100 입력: `data/processed/v24/phase4b_train_internal_2018/`.
- KOSPI 전체 참조 입력: `data/processed/v25_phase4c_market_reference_2018/`.
- 두 입력의 manifest 최대일은 2018-12-31 이하이어야 reader 호출 전에 검증한다.
- 2019~2021, Development Test, `data/sealed/final_oos_v24/`는 열거·로드·계산·평가·선택하지 않는다.

## 사전등록 후보와 계산

각 날짜 `t` 장 마감 후 KOSPI 전체의 상승비율, 중앙값 일수익률, 일수익률 분산 및 `log(거래대금_t / 과거 포함 20세션 평균 거래대금)`을 계산한다. 각 anchored internal fold에서 reference 변수의 평균·표준편차는 Train 날짜로만 적합한다. 이를 Phase 4B의 21개 종목 기술변수 일별 percentile rank와 곱해 84개 상호작용을 만든다.

직접적인 시장상태 변수는 같은 날짜의 모든 종목에 상수이므로 횡단면 IC를 낼 수 없다. 따라서 상호작용의 t일 값과 `t+1` 시가~`t+11` 시가의 10세션 KOSPI 100 초과수익률 rank의 일별 Spearman IC 및 HAC lag 10을 감사한다. purge와 embargo는 각 20세션이다.

## 비목표와 완료 조건

이 단계는 모델·포트폴리오·Development Test를 실행하지 않으며, 관측 결과와 무관하게 Feature·거래 후보를 승격하지 않는다. 산출물은 fold별 지표, 후보 요약, 결정표, 입력 감사, run 및 hash manifest다. 입력 경계·Train-only 표준화·결정성·기존 회귀 테스트를 모두 통과해야 한다.

## Codex Handoff

실행 전 KOSPI 전체 2011~2018 물리 참조 패널을 만든 뒤 아래 명령을 사용한다.

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe .\tools\build_phase1b_market_reference.py --raw-root .\data\incoming\v25_kospi_raw --output-root .\data\processed\v25_phase4c_market_reference_2018 --max-date 2018-12-31
.\.venv\Scripts\python.exe .\tools\run_phase4c_market_reference_audit.py --config .\configs\phase4c_market_reference_audit.json --output .\artifacts\phase4c_market_reference_audit
```
