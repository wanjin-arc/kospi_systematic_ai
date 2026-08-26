# KOSPI 200 2011~2014 구형 DART 수치 후보 감사

## 결론

2011~2014 구형 DART 원문을 수치 후보 형태로 정리했다. 이 산출물은 원문 표에서
엄격한 총계 레이블을 찾고, 정정 보고서·접수일 다음 KRX 세션·PIT ticker–법인 identity를
함께 기록한 감사 자료다. 표준 XBRL account ID나 승인된 구형 계정 taxonomy가 없으므로
**모델 및 Agent B 입력은 0행**이며, 기존 2016~2023 펀더멘털 패널을 수정하지 않는다.

## 실제 실행

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe .\tools\extract_dart_kospi200_legacy_financials_v1.py `
  --raw-root .\data\incoming\v2_kospi200_dart_legacy_originals_raw `
  --membership-root .\data\incoming\v2_kospi200_membership_raw\normalized\membership_daily `
  --identity .\data\processed\v2_kospi200_identity_frozen\identity_spells.csv `
  --output-root .\data\processed\v2_kospi200_legacy_dart_numeric_audit
```

## 결과

| 항목 | 값 |
|---|---:|
| 감사 문서 | 2,451개 |
| 실제 ZIP 원문 | 2,437개 |
| 다중 XML ZIP | 571개 |
| 수치 후보 행 | 123,840개 |
| 최신 정정본 기준 비모호 후보 | 9,594개 |
| 2011 / 2012 / 2013 / 2014 비모호 후보 | 3,374 / 2,468 / 1,873 / 1,879개 |
| 모델 사용 행 | 0개 |
| Final OOS 접근 | 없음 |

후보는 자산·부채·자본·유동자산·유동부채·현금및현금성자산·매출/영업수익·영업이익·순이익·영업현금흐름·CAPEX의 표기와 정확히 일치한 행만 포함한다. 부분 계정, 비율, 날짜, 문장 중 단어는 포함하지 않는다.

## 정리된 파일

- `legacy_document_numeric_audit.csv`: 문서별 접수일, 다음 KRX 세션, 원문 hash,
  XML payload 수, parser 상태, 정정 선택 상태, identity 상태
- `legacy_financial_candidates.csv`: 모든 엄격 레이블 수치 후보와 원문 표 행
- `legacy_financial_selected.csv`: 최신 논리 보고서 기준 비모호 후보 및 충돌 제외 상태
- `manifest.json`: 입력·출력 hash, 계정별 coverage, 모델 금지 상태

출력 경로는 `data/processed/v2_kospi200_legacy_dart_numeric_audit/`다. Raw ZIP과
원 수집 폴더는 변경하지 않았다.

## 아직 학습에 쓸 수 없는 이유

구형 표에는 표준 XBRL `account_id`가 없고, 표 단위가 명시되지 않은 후보가 74,511개다.
또한 비모호 후보 중 statement scope가 `UNKNOWN`인 행이 4,967개다. CFS 표기·확정
identity·단위 확인을 동시에 만족하는 후보는 452행(187개 문서, 50개 종목)뿐이며,
11개 핵심 계정을 모두 갖춘 문서는 0개다.

따라서 다음 단계는 결과를 보고 임의 계정명을 매핑하는 일이 아니라, 별도 승인된
`legacy-account-taxonomy`를 만들고 단위·연결/별도·정정·PIT identity 조건을 계정별로
검증하는 것이다. 그 승인 전에는 이 자료를 Agent B, Agent C, Agent D 또는 백테스트에
연결하지 않는다.
