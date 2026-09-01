# v2 Phase 1 KOSPI 200·펀더멘탈 데이터 명세

## 입력

- KRX KOSPI 200 지수코드 `1028`의 2004~2023 구성종목
- 이미 확보한 KRX KOSPI 전체 개별종목 OHLCV·거래대금·시가총액·상장주식 수
- OpenDART `corpCode.xml`, `list.json`, `fnlttSinglAcntAll.json`
- OpenDART 표준 재무제표 허용기간 2015~2023

## 출력

- `data/incoming/v2_kospi200_membership_raw/`
- `data/incoming/v2_kospi200_dart_fundamentals_raw/`
- `data/processed/v2_kospi200_dart_receipt_overrides/receipt_overrides.csv`
- `data/processed/v2_kospi200_fundamentals_receipt_corrected/financial_facts_pit.csv`
- `data/processed/v2_kospi200_identity_frozen/identity_spells.csv`
- `data/processed/v2_kospi200_canonical_fundamentals/canonical_financial_accounts.csv`
- `data/processed/v2_kospi200_fundamental_factor_panel/fundamental_factor_panel.csv.gz`
- 파일별 hash·행 수·날짜·API 응답 상태·공개시점 audit manifest

## 데이터 경계

- 2024년 이후 KRX/DART 수집 금지
- `data/sealed/final_oos_v24/` 접근·스캔·로드 금지
- 재무제표의 사업연도와 접수연도가 다를 수 있으므로, 모든 연도별 공시목록으로 접수번호를 재대조한다.
- DART 접수일의 **다음 실제 KRX 세션**부터만 fact를 사용한다. 같은 날 또는 이전 날짜 사용은 금지한다.
- 접수일·원천 SHA-256·연결/별도 범위 표기 중 하나라도 확인되지 않은 fact는 `model_eligible=false`
- 정정공시 값의 과거 소급 금지
- 현재 stock code만으로 역사적 동일 법인을 확정하지 않음
- Raw 응답 수정 금지

## 테스트

- KOSPI 200 코드와 날짜 경계
- 실제 snapshot 수 보존과 무단 200개 보간 금지
- DART 2015 미만·2023 초과 거부
- 다음 KRX 세션 이전 사용 차단과 접수일 미확정 fact의 fail-closed 처리
- receipt override 원천 SHA-256 불일치 차단
- 사업연도와 접수연도가 다른 연차보고서의 receipt-date 보정
- ticker→corp-code 유일성 및 PIT membership 종목명과 DART 법인명 exact-match identity gate
- 표준 XBRL account ID만 허용하고 account-name fallback 금지
- 누적 interim flow의 causal TTM 변환과 결측 dependency 보존
- 같은 입력 재실행의 byte determinism
- 20개 Factor 산술·0분모·결측 보존
- 날짜·섹터 단면 변환의 미래정보 미사용
- 재실행 resume와 API key 비저장

## 완료 조건

실제 수집 후 membership coverage, 역사적 identity, 재무 taxonomy, CFS/OFS, 정정공시 snapshot과 20개 Factor 패널을 감사하고 hash를 고정한다. 미확정 identity와 계정은 추정하지 않고 모델 비적격으로 남긴다. 이 조건 전에는 Agent B 모델을 학습하지 않는다.

## Codex Handoff

수집 명령은 `docs/KOSPI200_V2_DATA_COLLECTION_KO.md`를 따른다. KRX 수집기는 구성종목만 요청하며 기존 KOSPI 전체 OHLCV는 재다운로드하지 않는다. 실제 데이터가 전달되면 정규화 결과를 먼저 감사하고 `v2_phase_1_report.md`를 작성한다. 모델·백테스트·Development Test는 별도 승인 범위다.
