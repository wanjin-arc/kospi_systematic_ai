# KOSPI 200 2011~2014 구형 DART 병합 감사

## 결론

사용자 승인에 따라 2011~2014 구형 DART 원문을 기존 2015~2023 표준 XBRL
canonical 계정과 **별도 파생 경로**에서 병합했다. Raw ZIP, 기존 canonical 파일,
기존 2016~2023 factor panel은 수정하지 않았다.

다만 병합본의 2011~2014 부분은 현재 모델 학습용 품질 gate를 통과하지 못한다.
따라서 이 병합본은 후속 원문 표 구조 검증을 위한 후보 패널이며, Agent B 재학습에
사용하지 않는다. 이 결정은 2016~2023 기존 Agent B 결과를 변경하지 않는다.

## 적용한 fail-closed 조건

- 2011-03-31 이후 보고기간만 허용한다. 2010년 K-GAAP 비교표는 제외한다.
- DART 접수일 다음 KRX 거래일의 PIT availability만 허용한다.
- frozen identity가 확정된 ticker/corp-code spell만 허용한다.
- 연결(CFS)로 명시된 표와 확인된 단위(원·천원·백만원·억원)만 허용한다.
- 정정공시는 동일 논리 공시의 최신본만 허용한다.
- 같은 공시·범위·계정에 서로 다른 금액이 있으면 선택하지 않는다.
- Final OOS 경로는 도구와 테스트에서 거부한다.

## 실제 결과

| 항목 | 값 |
|---|---:|
| 재추출 수치 후보 | 123,840행 |
| 최신·비모호 후보 | 9,602행 |
| strict legacy canonical 계정 | 330행 |
| 기존 XBRL canonical 계정 | 93,910행 |
| 병합 canonical 계정 | 94,240행 |
| 병합 factor panel | 296,861행 |
| 2011~2014 factor panel | 23,000행, 37 ticker |
| 2011~2014 30종목 이상 날짜 | 399일 |

2011~2014 부분의 factor coverage는 핵심 수익성·성장성 항목에서 지나치게 낮다.
예를 들어 ROE 1.78%, ROA 1.78%, 영업현금흐름/자산 0%, FCF yield 0.13%,
매출 성장률 0.22%다. 따라서 표본 행 수만으로는 학습 범위가 확장된 것처럼 보여도,
실질적인 20개 Factor 학습 입력으로는 부적합하다.

## 산출물과 해시

- strict legacy canonical:
  `data/processed/v2_kospi200_legacy_canonical_fundamentals/`
  (`7b7f68461c7d2594d85d1199bf03e02c44feeff7ca55df8273082064ca25e37a`)
- 병합 canonical:
  `data/processed/v2_kospi200_canonical_fundamentals_2011_2023/`
  (`122927869f1586b1f23e325677a2e81d0e44c723508c33f00a0c9c258bf54f29`)
- 병합 factor panel:
  `data/processed/v2_kospi200_fundamental_factor_panel_2011_2023/`
  (`b19056a0e31c6284fee055a416b167b8e817e1c5bf39f69c0d6b59249a3d4e9a`)
- panel audit:
  `artifacts/v2_phase1_legacy_2011_2014_factor_panel_audit/factor_panel_audit.json`

## 재현 명령

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe .\tools\build_kospi200_legacy_canonical_fundamentals_v1.py
.\.venv\Scripts\python.exe .\tools\merge_kospi200_canonical_fundamentals_v2.py
.\.venv\Scripts\python.exe .\tools\build_kospi200_fundamental_factor_panel_v2.py `
  --canonical .\data\processed\v2_kospi200_canonical_fundamentals_2011_2023\canonical_financial_accounts.csv `
  --factor-contract .\configs\fundamental_factor_contract_v2_legacy_2011.json `
  --output-root .\data\processed\v2_kospi200_fundamental_factor_panel_2011_2023 `
  --minimum-year 2011
```

## Codex Handoff

병합 산출물은 보존한다. 모델에 실제 포함하려면 주석·보조표가 아닌 재무제표 본문을
표 단위로 식별하는 별도 검증과, 20개 Factor별 2011~2014 coverage gate의 사용자
승인이 필요하다. 현재 상태에서 coverage 부족을 결측치 보간이나 임의 계정 매핑으로
해결하는 것은 금지한다.
