# KOSPI 200 과거 DART 원문 수집 안내

`2011~2014`의 사업ㆍ반기ㆍ분기보고서 원문은 OpenDART 표준 전체 재무제표 API의
지원 범위 밖이다. 따라서 이 절차는 원문 ZIP과 접수번호ㆍ접수일만 보존한다. 원문
텍스트, 사업전망, 뉴스성 문장은 투자 Factor로 사용하지 않는다.

원문을 계정 수치로 정규화하고, 역사적 ticker-법인 동일성ㆍ정정공시ㆍ접수일을 감사하기
전에는 어떤 결과도 Agent B 입력이나 모델 학습에 사용하지 않는다.

## 실행

저장소 루트 PowerShell에서 실행한다.

```powershell
\.venv\Scripts\python.exe .\tools\collect_dart_kospi200_legacy_originals_v1.py `
  --start-year 2011 `
  --end-year 2014 `
  --output-root "C:\Users\seoji\Downloads\v2_kospi200_dart_legacy_originals_raw" `
  --max-requests 3000
```

키는 한 번만 입력하며 저장ㆍ출력되지 않는다. `--max-requests`는 **새 HTTP 요청**만
센다. 이미 있는 `disclosures/*.json`과 문서 ZIP은 재사용하므로, 일일 한도 또는
중단 뒤에는 다음 날 정확히 같은 명령을 다시 실행하면 된다. `--max-requests 0`은
허용하지 않는다.

출력에는 다음이 포함된다.

- `documents/<year>/<corp_code>/<rcept_no>.zip`: 원 공시문서
- `disclosures/`: 공시목록 응답과 접수 메타데이터
- `document_audit.csv`: 원문별 상태ㆍ정정 여부ㆍ접수일
- `ticker_corp_mapping.csv`: 현재 stock code 기반의 **미확정** 법인 연결
- `manifest.json`: 요청 수, 재개 상태, 파일 SHA-256

수집이 끝나면 최상위 폴더 전체를 ZIP으로 압축해 전달한다. `documents/`만이 아니라
`document_audit.csv`, `disclosures/`, `ticker_corp_mapping.csv`, `corp_codes.xml.zip`,
`manifest.json`도 반드시 포함해야 후속 분류와 PIT 감사가 가능하다.

## 범위와 제한

- 수집기는 `2011~2014`만 허용하며 2015년 이후나 봉인 OOS 경로를 읽지 않는다.
- OpenDART의 현재 종목코드-법인코드 파일은 과거 동일성 증명이 아니다. 이름ㆍ상장/합병
  이력과 함께 별도 fail-closed 감사가 필요하다.
- 원문을 받은 뒤에는 수치 계정만 추출하고, 실제 DART 접수일의 다음 KRX 세션부터만
  사용 가능하도록 정규화한다.
