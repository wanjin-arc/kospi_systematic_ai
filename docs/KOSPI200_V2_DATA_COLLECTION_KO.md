# KOSPI 200 v2 데이터 수집 실행 안내

공식 근거: [KRX 지수 사업 안내](https://global.krx.co.kr/contents/GLB/02/0202/0202010101/GLB0202010101.jsp), [OpenDART 고유번호 API](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019018), [OpenDART 단일회사 전체 재무제표 API](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020)를 따른다.

## 1. KRX 구성종목 수집

PowerShell에서 저장소 루트 기준으로 실행한다.

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe .\tools\collect_krx_kospi200_v2.py `
  --start 2004-01-02 `
  --end 2023-12-31 `
  --sessions-root "C:\Users\seoji\Downloads\v25_kospi_raw\raw\market_stk" `
  --sessions-root-extra "C:\Users\seoji\OneDrive\바탕 화면\kospi_systematic_ai\data\incoming\v25_zip_import\krx_v25_technical_raw" `
  --output-root "C:\Users\seoji\Downloads\v2_kospi200_membership_raw"
```

이 명령은 기존 KOSPI 전체 OHLCV를 다시 받지 않는다. `--sessions-root`의 일봉 **파일명 날짜만** 읽어 거래일을 정한 뒤 KOSPI 200 구성종목 snapshot만 요청한다. 날짜별 실제 구성종목 수가 200보다 적더라도 원자료를 보존하고 임의 종목을 채우지 않는다.

KOSPI 200 지수 benchmark가 아직 없다면, 같은 명령 끝에 `--include-index`만 추가한다. 이 경우에만 지수 CSV 1개를 추가 요청한다.

## 2. OpenDART 재무제표 수집

KRX 수집 완료 후 실행한다.

```powershell
.\.venv\Scripts\python.exe .\tools\collect_dart_kospi200_fundamentals_v2.py `
  --membership-root "C:\Users\seoji\Downloads\v2_kospi200_membership_raw\normalized\membership_daily" `
  --output-root "C:\Users\seoji\Downloads\v2_kospi200_dart_fundamentals_raw" `
  --start-year 2015 `
  --end-year 2023 `
  --max-requests 35000
```

`--max-requests 0`은 코드 자체 요청 상한만 없앤다. OpenDART의 계정별 일일 호출한도는 그대로 적용되므로 권장하지 않는다. 기존 JSON은 재사용하므로 다음 날 같은 명령으로 이어갈 수 있다.

## 2-1. 특정 주식수 후보만 기업행위 공시 수집

Phase 5 pre-backtest 감사에서는 전체 KOSPI 200 공시를 다시 요청하지 않는다. 다음 옵션은
`share_reset_candidates.csv`의 `member_both_sessions=True` 37건만 scope로 사용하고, 사건일
전후 730일 안의 기업행위 공시만 원문 다운로드한다. 이 CSV에 없는 ticker의 공시는 조회하지 않는다.

```powershell
.\.venv\Scripts\python.exe .\tools\collect_dart_kospi_actions_v25.py `
  --krx-raw-root "C:\Users\seoji\Downloads\v25_kospi_raw" `
  --event-csv ".\artifacts\v2_phase5s_share_change_safe_integrity\share_reset_candidates.csv" `
  --event-window-days 730 `
  --start-year 2021 `
  --end-year 2023 `
  --output-root ".\data\incoming\v25_kospi_dart_audit_raw_37_events"
```

`--event-csv`를 지정하면 KRX 원시자료 전체 ticker 스캔을 하지 않는다. API 키는 기존과 같이
대화형 프롬프트로만 입력하며 파일·manifest에는 저장하지 않는다. 수집 결과는 여전히 후보 증거일
뿐이고, 원문·PIT identity·효력 세션·권리조건·KRX 교차검증을 모두 통과하기 전에는 회계나
백테스트 입력으로 승격하지 않는다.

## 3. 정규화

수집 ZIP/폴더를 저장소의 `data/incoming/` 아래로 옮긴 뒤 실행하거나 절대경로를 직접 지정한다.

```powershell
.\.venv\Scripts\python.exe .\tools\normalize_dart_kospi200_fundamentals_v2.py `
  --raw-root "C:\Users\seoji\Downloads\v2_kospi200_dart_fundamentals_raw" `
  --output-root ".\data\processed\v2_kospi200_fundamentals"
```

`availability_status=RESOLVED`인 facts만 모델 입력 후보가 된다. `UNRESOLVED_NOT_MODEL_ELIGIBLE`은 접수일 확인 전까지 사용하지 않는다.

## 4. 아직 추가로 필요한 감사

- KRX 종목코드와 DART 법인코드의 역사적 변경 연결
- 금융업/일반기업 계정 taxonomy 분리
- CFS 우선·OFS fallback 및 중복 보고서 검증
- 정정공시가 과거 날짜에 소급되지 않는지 snapshot 테스트
- 시가총액·상장주식 수·Corporate Action과 재무 희석도의 일치 검사
- KOSPI 200 지수와 일별 membership coverage

감사 완료 전에는 모델을 학습하지 않는다.
