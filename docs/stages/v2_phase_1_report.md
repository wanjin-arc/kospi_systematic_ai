# v2 Phase 1 KOSPI 200·펀더멘탈 원천 정규화·감사 보고서

## 실행 결과

KOSPI 200 point-in-time 구성종목과 OpenDART 표준 재무제표 원천을 정규화하고,
실제 접수일의 다음 KRX 세션 규칙을 감사했다. 모델 학습·백테스트·Development
Test·Final OOS 사용은 수행하지 않았다.

### KRX 구성종목

- 범위: `2004-01-02`~`2023-12-31`
- 요청 세션 4,946개, 정규화 snapshot 4,945개
- 2010-12-31은 KRX header-only 응답으로 `skipped_empty_sessions.txt`에만 기록했고 보간하지 않았다.
- 공식 snapshot 수: 199개 8일, 200개 4,475일, 201개 348일, 202개 114일
- 중복 ticker와 raw/normalized/checkpoint 불일치: 0건

201개와 202개는 KRX 정기·수시 변경 경계의 실제 point-in-time 응답이다. 수집기는
이를 200개로 임의 절단하지 않는다.

### OpenDART PIT 재무 facts

- 원천 재무제표 응답: 15,984개 파일, KOSPI 200 이력 구성종목 ticker 444개, 2015~2023 사업연도
- 공시목록 접수번호: 196,483개, 충돌 접수일: 0건
- 접수번호 재대조 성공: 10,860개 파일; 미확정 5,124개 파일은 추정하지 않았다.
- 보정 facts: 2,162,209행, model eligible 2,022,819행, eligible ticker 391개
- 연결 범위 표기 확인: 1,914,447 eligible 행; 별도 범위 표기 확인: 108,372 eligible 행
- `available_from`은 DART 접수일보다 엄격히 뒤의 실제 KRX 세션이며, PIT 위반: 0행
- 원천 JSON 변경: 없음. Final OOS 접근: 없음.

facts 파일 SHA-256은
`e67d4050a381442c00039a242f9fab02930eaacc6503229872af335aedaad6cc`이고,
receipt override SHA-256은
`d6b0f2dae72ee86b817ab0453d3e8c67f5f65050a2b1c39f33e8da069eb2383f`이다.

## 수정한 문제

초기 수집기는 재무제표의 `bsns_year`와 같은 달력연도 공시목록만 대조했다. 연차보고서는
다음 해에 접수될 수 있어, 예를 들어 2015 사업연도 보고서의 2016-03-30 접수번호를
초기 audit 값만으로는 확인하지 못했다.

원천을 수정하지 않고 모든 `disclosures/<corp_code>/<접수연도>.json`을 교차 대조하는
`receipt_overrides.csv`를 새로 만들었다. 정규화기는 override의 원천 SHA-256을 먼저
검증하고, 접수일의 다음 실제 KRX 세션을 계산한다. hash 불일치, 접수일 미확정,
마지막 개발 세션 밖의 접수일은 모두 `model_eligible=false`다.

원천 응답에는 당시 요청한 `fs_div` 파라미터가 반환되지 않는다. 따라서 빈 값을 OFS로
추정하지 않고, 재무제표 account detail의 연결/별도 표기가 확인된 경우만 provenance로
기록했다. 이 표기는 scope 검증용이며 Factor 입력 텍스트로 사용하지 않는다.

## 산출물·재현 명령

- `data/processed/v2_kospi200_dart_receipt_overrides/receipt_overrides.csv`
- `data/processed/v2_kospi200_fundamentals_receipt_corrected/financial_facts_pit.csv`
- `artifacts/v2_phase1_fundamental_audit/fundamental_audit.json`
- `data/processed/v2_kospi200_identity_frozen/identity_spells.csv`
- `data/processed/v2_kospi200_canonical_fundamentals/canonical_financial_accounts.csv`
- `data/processed/v2_kospi200_fundamental_factor_panel/fundamental_factor_panel.csv.gz`
- `artifacts/v2_phase1_factor_panel_audit/factor_panel_audit.json`

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe .\tools\build_dart_kospi200_receipt_overrides_v2.py
.\.venv\Scripts\python.exe .\tools\normalize_dart_kospi200_fundamentals_v2.py `
  --receipt-overrides .\data\processed\v2_kospi200_dart_receipt_overrides\receipt_overrides.csv `
  --output-root .\data\processed\v2_kospi200_fundamentals_receipt_corrected
.\.venv\Scripts\python.exe .\tools\audit_kospi200_fundamentals_v2.py
.\.venv\Scripts\python.exe .\tools\freeze_kospi200_identity_v2.py
.\.venv\Scripts\python.exe .\tools\build_kospi200_canonical_fundamentals_v2.py
.\.venv\Scripts\python.exe .\tools\build_kospi200_fundamental_factor_panel_v2.py
.\.venv\Scripts\python.exe .\tools\audit_kospi200_factor_panel_v2.py
```

## 역사적 identity 동결

PIT membership 4,945개 파일의 ticker·종목명 spell과 DART `corpCode.xml` 및 실제
수집 audit의 ticker→corp-code를 대조했다. 자동 확정은 정규화 exact name match와
corp-code 유일성을 동시에 만족해야 한다.

- 이력 ticker: 444개, 종목명 spell: 598개
- 자동 확정 ticker: 354개
- 완전 미확정 ticker: 90개
- 수동 alias: 0개
- identity 출력 SHA-256: `d9abe7647f7eb36670cc93c4ebae3490979f3fb022fabe3fba11b100886b25eb`

90개에는 회사명 변경·약칭으로 보이는 사례도 있지만 외부 증거 없이 동일 법인이라고
간주하지 않았다. 해당 이름 spell은 모델 입력에서 제외된다.

## Canonical taxonomy와 20 Factor 패널

account-name fallback 없이 표준 XBRL account ID만 사용하는 taxonomy를 동결했다.
자산·부채·자본·유동항목·현금·매출·영업이익·순이익·영업현금흐름·CAPEX 11개
canonical 계정이 모두 존재한다.

- canonical 계정 행: 93,910행
- 중복·상충 계정 제외: 0건
- 계정별 ticker coverage: 279~316개
- 일별 Factor 패널: 264,341행, 248개 ticker
- 기간: 2016-03-24~2023-12-28
- 일별 ticker 수: 중앙값 140개, 최대 167개. 초기 5개 세션은 30개 미만이므로 모델 입력에서 제외한다.
- KRX membership·시가총액 입력: 각각 2,214개 세션
- 20개 Factor coverage: 최저 `free_cash_flow_yield` 56.71%, 최고 `current_ratio` 99.60%
- Factor 패널 SHA-256: `0ba2cb148b7e076d221a62b8b323ff18063518700b1dd597c5005ac46a0ab857`
- 동일 입력 재실행: byte-identical

누적 분기 손익·현금흐름은 당시 사용 가능했던 전기 연차 + 당기 누적 - 전기 동기 누적으로
TTM화했다. 결측 dependency는 채우지 않았다. 재무상태는 새 공시 전까지
`as-of available` 상태로 유지하며, 이는 미래값 보간이 아니다.

## 상태와 남은 조건

v2 Phase 1 데이터 구축·감사는 완료했다. PIT facts는
`PASS_PIT_FACTS_MODEL_NOT_STARTED`, identity는 `PASS_FAIL_CLOSED_IDENTITY_FREEZE`,
canonical 계정은 `PASS_CANONICAL_ACCOUNTS_MODEL_NOT_STARTED`, Factor 패널은
`PASS_FACTOR_PANEL_MODEL_NOT_STARTED`다.

다음 단계는 Agent B 모델 사전등록이다. target 기간, fold, baseline, XGBRanker 후보와
하이퍼파라미터, 채택 gate를 새 Experiment ID로 동결하기 전에는 학습·백테스트하지 않는다.
2004~2023은 consumed development이므로 독립 Validation/OOS라고 부르지 않는다.

검증은 v2 관련 전용 테스트 30/30, 전체 회귀 테스트 181/181을 통과했다. 실제 Factor
패널을 같은 입력으로 두 번 생성했으며 SHA-256이 동일했다.

## Codex Handoff

- receipt 보정: `tools/build_dart_kospi200_receipt_overrides_v2.py`
- 정규화: `tools/normalize_dart_kospi200_fundamentals_v2.py`
- PIT 감사: `tools/audit_kospi200_fundamentals_v2.py`
- identity: `tools/freeze_kospi200_identity_v2.py`
- canonical 계정: `tools/build_kospi200_canonical_fundamentals_v2.py`
- Factor 패널: `tools/build_kospi200_fundamental_factor_panel_v2.py`
- Factor 감사: `tools/audit_kospi200_factor_panel_v2.py`
- 다음 구현은 Agent B 사전등록 명세와 registry 등록이다. 결과 확인 전에 target·fold·모델 후보·gate를 고정한다.
