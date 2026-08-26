# Phase 1C 2004~2018 확장 데이터 명세

## 목적

2004~2009 KRX KOSPI 100 구성종목·전 종목 일봉·KOSPI 100 지수를 기존 감사 완료 v24 2010~2018 데이터와 결합한다. 과거 Phase 결과는 변경하지 않으며 새 실험 전용 물리 파티션만 만든다.

## 입력과 경계

- KRX 원천: `data/incoming/v25_zip_import/krx_v25_technical_raw/`
- 기존 입력: `data/processed/v24/phase4b_train_internal_2018/`
- 실제 추가 구간: 2004-01-02~2009-12-30
- 기존 연결 구간: 2010-01-04~2018-12-28
- 2000~2003은 사용하지 않는다.
- 2019년 이후, Development Test, Final OOS는 읽지 않는다.

## Corporate Action 보수 규칙

확정 경제조건을 추정하지 않는다. 동일 종목코드의 연속 거래소 세션 사이에서 거래 가능 상태가 바뀌거나, 시가/전일 종가 비율이 0.75 미만 또는 1.25 초과이거나, 상장주식수 비율이 0.80 미만 또는 1.25 초과이면 Feature·label 연속성을 reset한다. 이는 예측 Factor가 아니며 포트폴리오 경제조건으로 사용하지 않는다.

## 산출물

`data/processed/v25_phase5i_train_internal_2004_2018/`에 5개 gzip CSV, manifest, partition 감사를 쓴다. Raw 파일은 수정하지 않는다.

## 완료 조건

- 첫 로드일 2004-01-02, 최대일 2018-12-28
- 일별 PIT 구성종목 99~100개이며 보정하지 않음
- 종목-날짜 중복 0, OHLC·거래가능 gate 검증
- Corporate Action 조건 추정 0, reset 경계만 기록
- 동일 입력 재실행 byte determinism
- Development Test 및 Final OOS 접근 0

## Codex Handoff

빌더는 `tools/build_phase1c_2004_2018_partition.py`다. 출력은 Phase 5I에서만 사용하고 기존 v24 파티션과 결과를 덮어쓰지 않는다.
