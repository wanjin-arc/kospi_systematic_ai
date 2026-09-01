# Phase 1B 시장참조 패널 명세

KOSPI 100 PIT Universe는 유지한다. KOSPI 전체 원자료는 종목별 target이나 투자 Factor가 아니라 동시점 시장참조 패널 후보를 만드는 데만 사용한다. 입력은 2011-01-01~2023-12-31 물리 파티션이며, 2024년 이후 파일은 reader 호출 전에 제외한다. DART는 정합성 감사에만 사용한다.

산출물은 일별 전체 KOSPI 관측 종목 수, 거래대금 합계, 상승비율, 중앙값 수익률, 수익률 분산이다. 이 단계는 Feature 채택·모델 학습·Development Test·Final OOS 접근을 수행하지 않는다.
# 실행 경계 및 감사

이 Phase는 KOSPI 100 PIT Universe와 기존 v24 개발 데이터를 변경하지 않는다. KOSPI 전체 원자료는 종목별 학습 표본이나 투자 Factor가 아니라, 향후 별도 Feature 감사에서 검토할 수 있는 **동시점 시장참조 패널**만 만든다. 모델 학습, 점수 산출, 포트폴리오 시뮬레이션, Feature 채택은 하지 않는다.

- 원시 입력은 `data/incoming/v25_kospi_raw/raw/market_stk/2011/`부터 `2023/`까지의 일별 KRX KOSPI 파일로 한정한다.
- 최대 허용일은 2023-12-31이다. 2024년 이후 파일·디렉터리는 열거하거나 reader로 열지 않는다.
- `data/sealed/final_oos_v24/`는 코드·명령·입력에서 참조하지 않는다.
- DART와 Corporate Action 자료는 데이터 정합성 감사에만 사용하며 Feature 또는 모델 입력으로 사용하지 않는다.

`artifacts/phase1b_market_reference/`에는 날짜별 관측 종목 수, 거래대금 합계, 전일 대비 상승비율, 중앙값 일수익률, 일수익률 분산을 담은 `all_kospi_market_reference.csv`와 입력 manifest hash·출력 hash·실제 최대 로드 날짜·행 수·post-2023 load 여부를 담은 `manifest.json`을 쓴다.

완료 조건은 Experiment ID 사전등록, 2023년 이하 연도 디렉터리만 reader가 열 수 있다는 테스트, 동일 입력의 byte determinism, 기존 v24 산출물 및 Phase 0~5 결과 미변경이다.

## Codex Handoff

구현 파일은 `tools/build_phase1b_market_reference.py`, 설정은 `configs/phase1b_market_reference.json`이다.

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe .\tools\build_phase1b_market_reference.py --raw-root .\data\incoming\v25_kospi_raw --output-root .\artifacts\phase1b_market_reference --max-date 2023-12-31
```

이 산출물은 Phase 4C의 별도 사전등록·Feature card·Train 내부 검증이 승인된 뒤에만 후보로 검토할 수 있다.
