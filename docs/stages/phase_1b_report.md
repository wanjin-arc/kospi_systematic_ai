# Phase 1B 시장참조 패널 실행 보고서

## 실행 결과

- Experiment ID: `EXP-20260825-001`
- 실행 범위: KRX KOSPI 전체의 동시점 시장참조 패널 구축만 수행
- 실제 입력: `data/incoming/v25_kospi_raw/raw/market_stk/2011/`부터 `2023/`
- 실제 최대 로드 날짜: 2023-12-28
- 산출 행 수: 3,202 거래일
- 입력 manifest SHA-256: `82e4356dec4c7dafef1931d626f7826a6189f55dd8055530f60c72d138dacbc0`
- 출력 CSV SHA-256: `c5f3f22b08ae4ad66132e71e6fbe8263fecc26c0961c112914871429e85696b8`
- 출력 manifest SHA-256: `ff112b97475d030587ddf25858932eb371bd0be6c446e7f386d31f70c1e85a88`

`artifacts/phase1b_market_reference/manifest.json`은 `post_2023_files_loaded: false`를 기록한다. 구현은 2011~2023이라는 허용 연도 디렉터리만 명시적으로 열거하므로, 2024년 이후 원시 파일을 reader로 열지 않는다. protected Final OOS는 참조하지 않았다.

## 산출물의 의미

패널은 전체 KOSPI의 관측 종목 수, 거래대금 합계, 상승비율, 중앙값 일수익률, 일수익률 분산으로 구성된다. 이는 KOSPI 100 종목을 추가하거나 개별 종목의 학습 행을 늘리는 자료가 아니다. 또한 아직 투자 Feature가 아니며, 별도의 Phase 4C 사전등록과 Train 내부 검증 없이는 어떤 모델에도 입력할 수 없다.

## 검증

- Phase 1B 전용 테스트: 2/2 통과
  - 2024 파일이 존재하는 합성 입력에서도 2023 이하 물리 디렉터리만 읽음
  - post-2023 설정값은 실행 전 `ValueError`로 거부됨
- 독립 재실행: CSV와 manifest 모두 byte-identical
- 전체 회귀 테스트: 137/137 통과

전체 테스트 중 Windows cp949 출력 decoding 경고와 외부 라이브러리 warning은 있었으나 테스트 실패는 없었다.

## 미결정 사항과 다음 경계

Phase 1B는 데이터 reference 산출물까지만 완료했다. 새 시장참조 변수를 쓸지, 어떤 계산식을 쓸지, KOSPI 100 기술변수와 결합할지는 아직 결정하지 않았다. 다음 단계는 Phase 4C 명세·Experiment 사전등록·Feature card를 별도로 승인한 뒤에만 시작할 수 있다. Phase 5 모델 재학습과 Development Test 접근은 이 보고서의 범위가 아니다.

## Codex Handoff

관련 구현: `tools/build_phase1b_market_reference.py`  
설정: `configs/phase1b_market_reference.json`  
산출물: `artifacts/phase1b_market_reference/`
