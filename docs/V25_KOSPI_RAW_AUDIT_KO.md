# v25 KOSPI 원시자료 및 기업행동 감사

## 범위와 분리 원칙

2026-08-25에 사용자가 제공한 `v25_kospi_raw.zip`과
`v25_kospi_dart_audit_raw.zip`은 각각 `data/incoming/v25_kospi_raw/` 및
`data/incoming/v25_kospi_dart_audit_raw_complete/`에 원본 그대로 보관한다.
중단된 압축 해제본 `v25_kospi_dart_audit_raw/`은 불완전할 수 있으므로 입력으로
사용하지 않는다. 원본 ZIP, incoming 자료, processed 감사 산출물은 Git에 넣지 않는다.

이 자료는 2011~2025년 유가증권시장 전체 종목 대상이다. 현재 v24 KOSPI 100
Point-in-Time 계약과는 Universe·기간·종목 식별 계약이 다르므로, v24 Phase 1~5의
입력, 결과, `corporate_actions.csv.gz`를 변경하거나 덮어쓰지 않는다.

## 수집 확인 결과

- KRX 원자료: 일별 KOSPI 시장 파일 3,688개, 종목코드 1,183개
- DART 원자료: 후보 공시 16,151건, 원문 ZIP 보관 14,052건,
  원문 비가용 감사 기록 2,099건
- DART 종목코드는 현재 코드 기준 매핑이므로 과거 시점의 동일성 증명이 아니다.

## 기업행동 처리 결론

`data/processed/v25_kospi_corporate_action_audit/`는 실행용 조정표가 아닌
차단형 감사 결과다. `corporate_action_resolution.csv`의 모든 행은
`UNRESOLVED_BLOCK_IF_IN_UNIVERSE`로 기록한다. 이 상태에서는 가격·주식수 배율을
추정하거나 Feature/포트폴리오에 넣지 않는다.

그 이유는 공시 접수일이 효력 거래일을 뜻하지 않고, KRX의 상장주식수 변화도
유상증자·상장·코드 변경과 기계적 분할을 단독으로 구별하지 못하기 때문이다.
기계적 조정을 확정하려면 종목별로 다음 네 증거가 일치해야 한다.

1. Point-in-Time 종목 식별과 당시 KOSPI 100 편입 여부
2. 원문 공시 또는 구조화 응답의 권리/분할 비율
3. 효력일과 실제 다음 거래세션
4. KRX 가격·상장주식수의 동일 배율 검증

## DART 구조화 응답 복구

기존 수집기의 세 API 경로를 다음과 같이 정정했다.

| 구분 | 정정 API |
| --- | --- |
| 회사분할 | `cmpDvDecsn.json` |
| 회사분할합병 | `cmpDvMgDecsn.json` |
| 주식교환·이전 | `stkExtrDecsn.json` |

기존 원본은 수정하지 않는다. 아래 명령은 API를 호출하지 않고, 2015년 이후의
기존 `101` 응답 중 재조회 가능한 항목만 계획 파일로 만든다.

```powershell
.\.venv\Scripts\python.exe .\tools\repair_dart_kospi_structured_v25.py `
  --source-root .\data\incoming\v25_kospi_dart_audit_raw_complete `
  --output-root .\data\processed\v25_kospi_dart_structured_repair `
  --max-requests 0
```

계획은 현재 442건이다. 실제 API 호출은 사용자가 요청 상한을 명시할 때만
수행하며, 예를 들어 하루 5,000건만 하려면 `--max-requests 5000`을 사용한다.
2011~2014년은 해당 구조화 API의 제공 범위 밖이므로 원문 공시/별도 KRX 증거로
검토해야 한다.

구조화 응답을 별도 경로에 수집한 뒤에는 다음처럼 감사표만 다시 생성할 수 있다.

```powershell
.\.venv\Scripts\python.exe .\tools\audit_v25_kospi_corporate_actions.py `
  --dart-root .\data\incoming\v25_kospi_dart_audit_raw_complete `
  --repaired-dart-root .\data\processed\v25_kospi_dart_structured_repair `
  --output-root .\data\processed\v25_kospi_corporate_action_audit
```

이 재감사도 자동 조정값을 만들지 않는다. 이를 KOSPI 100 연구자료로 승격하려면
별도 데이터 계약·PIT Universe 교차검증·사전등록 승인이 필요하다.

## PIT 구성종목 대조 결과

`C:\Users\seoji\Downloads\membership_daily.csv`와 KRX 일별 파일을 대조한
결과는 `data/processed/v25_membership_corporate_action_audit/`에 저장했다.

- membership 유효 범위: 2010-01-04~2023-12-28
- 대조 대상 범위: 2011-01-03~2025-12-30
- membership 날짜 3,202개, KRX 날짜 3,688개
- membership가 존재하는 날짜 중 100종목이 아닌 날짜: 26개(99종목)
- 겹치는 날짜에서 membership 종목이 KRX 파일에 없는 행: 0건
- 2024~2025 KRX 날짜 중 PIT membership가 없는 날짜: 486개

따라서 2024~2025 KRX 가격자료는 현재 상태에서 KOSPI 100 학습·검증에 사용할 수
없다. 2024년 이후는 별도 승인된 비봉인 연구자료 계약 없이는 모델 입력으로 사용하지
않으며, 기존 봉인 OOS 경로에는 접근하지 않는다.

## 99종목 날짜 원인 확인

`membership_gap_transitions.csv`에서 99종목 날짜의 전후 종목 변화를 확인했다.
이는 특별 변경·합병·관리종목 제외 뒤에 일시적으로 99종목 상태가 된 구간이다.
KRX [11006] 원응답 26건이 모두 같은 99종목 count를 반환했고, 각 99개 종목은
동일 날짜의 KRX 일별 시장 파일에도 모두 존재한다. 본 v25 데이터 계약에서는 이를
정상적인 Point-in-Time 구성종목 상태로 확정한다.

- 2011-03-30: `005280` 이탈 후 다음 세션에 `138930` 등장
- 2011-06-07: `005270` 이탈. 당시 6월 정기 지수변경 시기와 일치
- 2013-06-11~13: `028670` 이탈. 팬오션의 회생절차 개시 시기와 일치
- 2014-11-19: `053000` 이탈 후 `000030` 등장. 우리금융지주와 우리은행 합병·신주상장 일정과 일치
- 2017-05-11~06-08: `042660` 이탈. 대우조선해양의 관리종목 지정에 따른 KOSPI 100 제외가 2017-05-11부터 반영됨

해당 날짜의 KRX [11006] 원응답을 재조회한 결과 26개 날짜 모두 공식 응답 자체가
99종목이었다. 따라서 100번째 종목을 추정해 보충하지 않으며, `OFFICIAL_PARTIAL_99`
상태로 보존한다. KRX는 지수 구성종목과 일별 시세를 공식 데이터 서비스로 제공한다.

26개 날짜의 KRX [11006] 원응답만 별도 수집하는 명령은 다음과 같다. 수집기는
공식 응답의 종목 수를 그대로 기록하고, 원응답을 새 `incoming` 경로에만 보관한다.
이미 보관한 응답은 `--reuse-raw`로 재사용할 수 있다.

```powershell
.\.venv\Scripts\python.exe .\tools\collect_krx_v25_membership_repairs.py `
  --gap-csv .\data\processed\v25_membership_corporate_action_audit\membership_gap_transitions.csv `
  --output-root .\data\incoming\v25_krx_membership_repairs
```

원본을 수정하지 않는 정규화 후보 생성:

```powershell
.\.venv\Scripts\python.exe .\tools\normalize_v25_membership.py `
  --membership-source C:\Users\seoji\Downloads\membership_daily.csv `
  --repair-root .\data\incoming\v25_krx_membership_repairs `
  --output-root .\data\processed\v25_membership_normalized
```

공식 행은 `source=KRX_11006`, `official_count=99`로 보존되며 누락 종목을
추정하지 않는다. `tradable`은 공란으로 남겨 추가 검증이 필요한 상태를 표시하고,
이 후보는 모델 릴리스가 아니다.

## 기업행동 정규화 상태

2026-08-25에 KRX 원시 일별 파일과 DART 완료 수집본·복구 구조화 응답을 다시
대조했다. 후보 16,151건 중 구조화 응답 `000`은 2,218건이지만, 효력 거래일·배율·
과거 종목 identity가 모두 검증된 행은 없다. 따라서 자동 조정은 0건이며, 모든 후보는
`UNRESOLVED_BLOCK_IF_IN_UNIVERSE`로 유지한다. 이는 누락을 숨기는 것이 아니라
잘못된 과거가격 보정을 방지하는 fail-closed 처리다.

`data/processed/v25_corporate_actions_normalized/`에 16,151건을 통일된 감사
스키마로 정리했다. 합병·회사분할·분할합병·주식교환은 reset/block 후보로,
무상증자·감자·주식분할 후보는 효력일과 배율이 확인될 때까지 block 후보로 남긴다.
확정된 기계적 조정은 0건이다.

이는 이미 수집한 자료가 부족하다는 의미가 아니라, 원문/구조화 응답만으로는
`effective_date`, `share_multiplier`, `price_multiplier`, 과거 종목 identity를
안전하게 자동 확정할 수 없다는 의미다. 이 네 값을 KRX 세션과 교차 확인한 승인
항목만 별도 terms 파일로 승격할 수 있다.

## KOSPI 전체 자료의 사용 범위

KOSPI 전체 원자료는 현재 KOSPI 100 모델의 학습 입력으로 병합하지 않는다. 현재는
시장 구조·커버리지·유동성 분포를 확인하는 참고용 진단 자료로만 사용한다. KOSPI 전체를
학습 Universe로 사용하는 것은 target, PIT universe, 비용, benchmark, 종목별 유동성
규칙이 달라지는 별도 실험이며, 기존 Phase 결과를 변경하지 않고 별도 승인·사전등록 후
수행한다.
