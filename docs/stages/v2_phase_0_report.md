# v2 Phase 0 전환 보고서

## 완료 내용

- 기본 연구 Universe를 KOSPI 200 PIT로 확장하는 문서 계약을 추가했다.
- 실제 DART 접수일 이후 확정 재무제표 수치만 사용하는 Fundamental Agent B를 추가했다.
- Technical Agent C와 Meta Agent D의 역할 및 결합 순서를 분리했다.
- 20개 펀더멘탈 Factor와 단면 percentile·robust z-score 계약을 구현했다.
- KRX KOSPI 200 2004~2023 수집기, OpenDART 2015~2023 수집기, PIT facts 정규화기를 구현했다.
- 과거 실패 기록은 삭제하지 않고 2004~2023을 consumed development로 등록했다.
- 기존 2024~2025 v1 Final OOS 봉인 규칙을 유지했다.
- 신규 12개 테스트와 전체 회귀 163/163이 통과했다.

## 수행하지 않은 내용

외부 API 호출, 실제 데이터 수집, 데이터 품질 감사, XGBRanker/CNN/LSTM 학습, 백테스트, Development Test, Final OOS, 주문·배포는 수행하지 않았다.

## 남은 차단 조건

- 역사적 KRX ticker↔DART corp code↔security ID 연결
- KOSPI 200 일별 구성 coverage와 공석 검증
- 일반기업·금융업 재무 taxonomy 분리
- 정정공시 snapshot과 CFS/OFS 중복 감사
- 20개 Factor의 실제 coverage와 stale age 감사

## Codex Handoff

사용자가 수집 결과를 전달하면 v2 Phase 1 감사부터 시작한다. 감사 결과를 보기 전에 데이터 Release/Experiment ID와 gate를 등록한다. 모든 차단 조건이 통과하기 전 모델을 학습하지 않는다.
