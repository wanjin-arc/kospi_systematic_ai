# v2 Phase 0 연구 계약 명세

## 입력과 결정

- 날짜별 실제 KOSPI 200 Universe
- Long-only 현금 주식
- 분리된 Fundamental Agent B, Technical Agent C, Meta Agent D
- 2004~2023 consumed development, 2024~2025 v1 OOS 봉인 유지
- 독립 채택 증거는 동결 이후 forward data

## 비목표

이번 단계에서는 외부 데이터를 호출하거나 모델을 학습하거나 백테스트하지 않는다. XGBRanker·CNN·LSTM·결합 가중치·매매 임계값은 확정하지 않는다.

## 완료 조건

- 프로젝트 핵심 문서의 KOSPI 200·펀더멘탈 허용 계약 동기화
- 기존 실패 결과 append-only 보존과 consumed 기간 등록
- Factor 공개시점·정정공시·결측·시가총액 시점 계약 명시
- Protected OOS 불변

## Codex Handoff

v2 Phase 1에서 KRX/OpenDART 수집기를 실행하기 전 본 명세와 `docs/V2_FUNDAMENTAL_TECHNICAL_ARCHITECTURE_KO.md`를 읽는다. 수집 결과를 보기 전 데이터 감사 Experiment/Release ID를 등록하며 모델 코드는 실행하지 않는다.
