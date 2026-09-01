# Phase 1C 2004~2018 확장 데이터 보고서

## 결과

2004~2009 KRX 원천자료와 기존 감사 완료 v24 2010~2018 자료를 결합해 Phase 5I 전용 물리 파티션을 만들었다. 2000~2003 자료는 포함하지 않았다. 기존 Phase 결과와 원본 자료는 변경하지 않았다.

- 출력: `data/processed/v25_phase5i_train_internal_2004_2018/`
- 역할: `phase5i_train_internal_2004_2018`
- 날짜: 2004-01-02~2018-12-28
- Feature 가격 패널: 415,778행
- 전체 OHLCV: 492,198행
- KOSPI 100 지수: 3,712행
- Corporate Action/reset 경계: 181행
- 데이터 hash: `8d561c1412b825b10d8ceb0fce11554813cb17f47ee9f209ba39bcf9c7c88ebe`

2004~2009 PIT 구성종목 수는 1,490거래일에 100개, 2거래일에 99개였다. KRX 원자료를 임의 보간하지 않았다. 2,985개 원천 파일의 inventory hash는 `fff91609aec9dec9449b8d9f81cfb61263791453f1b7357e1d4ebdb89b92526e`다.

## Corporate Action 처리

확인되지 않은 경제조건을 추정하지 않았다. 연속 거래소 세션에서 거래가능 상태가 바뀌거나, 익일 가격 비율이 0.75 미만 또는 1.25 초과이거나, 상장주식 수 비율이 0.80 미만 또는 1.25 초과인 128개 경계는 Feature·label 연속성을 끊는 `FEATURE_RESET_ONLY`로 처리했다. 이 표시는 투자 Factor가 아니며 가격 조정비율을 의미하지 않는다.

따라서 이 자료는 기술 Feature 학습에는 사용할 수 있으나, 2004~2010 구간의 미확정 Corporate Action 경제조건을 체결·손익 재현 근거로 사용해서는 안 된다. Phase 5I의 실제 Validation 거래는 2011년부터 시작한다.

## 검증

- 동일 입력으로 독립 재생성한 7개 파일: 모두 byte-identical
- 2019년 이후 로드 행: 0
- Development Test 입력·계산·평가·선택 행: 모두 0
- Final OOS 접근: 없음
- 로드 후 날짜 필터: 없음

## Codex Handoff

확장 파티션은 `tools/build_phase1c_2004_2018_partition.py`로 재생성한다. Phase 5I 외 기존 Phase 입력을 이 파티션으로 바꾸지 않으며, 2004~2010의 reset-only 경계를 경제조건이 확정된 Corporate Action으로 해석하지 않는다.
