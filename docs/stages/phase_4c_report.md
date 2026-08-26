# Phase 4C KOSPI 전체 시장상태 상호작용 감사 보고서

## 실행 범위

Experiment `EXP-20260825-002`는 DEC-2026-060 및 사용자 승인에 따라 KOSPI 전체의 동시점 시장상태와 KOSPI 100 기술순위의 상호작용 84개를 감사했다. KOSPI 전체 종목은 Universe, 개별 종목 target, 직접 점수, 모델 학습 행으로 사용하지 않았다.

물리 입력은 KOSPI 100 `phase4b_train_internal_2018`과 KOSPI 전체 `v25_phase4c_market_reference_2018`뿐이다. 참조 입력은 1,969 거래일이며 최대 로드 날짜는 2018-12-28이다. KOSPI 100 연구 행의 최대 신호일은 label 완결성으로 인해 2018-12-12이다.

## 사전등록 계산과 결과

KOSPI 전체의 상승비율, 중앙값 일수익률, 일수익률 분산, 20세션 상대 거래대금을 각각 fold Train 날짜로만 표준화했다. 이를 Phase 4B의 고정 21개 일별 횡단면 기술순위와 곱해 84개 후보를 만들었다. purge·embargo는 각 20세션이며 평가는 2015~2018 anchored internal fold의 일별 Spearman IC와 HAC lag 10이다.

가장 높은 평균 내부 IC는 `risk_adjusted_momentum_63 × all_kospi_return_dispersion_1d`의 0.030512였지만, 네 fold 중 최소 HAC t는 0.221740이다. 따라서 이 수치는 안정적인 예측력의 증거가 아니다. 모든 후보의 결정은 `HOLD_AUDIT_ONLY_NO_PROMOTION`이며 Feature, 모델, 거래 후보로 승격한 것은 없다.

## 안전 감사와 재현성

- Development Test 입력·계산·평가 행 수: 모두 0
- Final OOS 접근: false
- 2018년 이후 로드 행 수: 0
- 미래 bar를 시장상태 변수에 사용: false
- label은 signal t 이후 t+1 시가 진입, t+11 시가 청산을 유지
- code hash: `2f9774b7200b6a9c6744ac26ab77236b8835da4a4231e4fe844e1774ce1022ad`
- config hash: `32ebc4de2b9e7db919956ae38024b157dce4f302961915d9ec38237a904506aa`
- data hash: `28bcd71a54c3af9a1cfd2001566150ad2640f89fab24de0f8365ebfff52ea628`

독립 재실행에서 `data_audit.json`, 두 CSV, `run.json`, `manifest.json`을 포함한 6개 산출물이 모두 byte-identical이었다.

## 검증

- Phase 4C 전용 테스트: 3/3 통과
- 전체 회귀 테스트: 140/140 통과

전체 테스트에서는 Windows cp949 출력 decoding 경고와 외부 라이브러리 warning이 있었으나 실패는 없었다.

## Codex Handoff

산출물은 `artifacts/phase4c_market_reference_audit/`에 있다. 다음 단계에서 새 변수를 모델에 넣으려면 별도의 Experiment ID, 모델 명세, 선택 gate 및 사용자 승인이 필요하다. Phase 4C 결과만으로 Phase 5나 Development Test를 실행할 수 없다.
