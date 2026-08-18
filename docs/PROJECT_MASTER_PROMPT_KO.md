# KOSPI 100 Technical Systematic AI 프로젝트 지침

## 1. 목표

KOSPI 100을 대상으로 과거 10년 이상의 가격 데이터를 이용해 **차트 기반 자동매매 시스템**을 빠르게 구축한다.

우선순위는 사용자의 금융·프로그래밍 학습보다 실제 작동하는 시스템 제작이다.

전체 흐름:

> 데이터 → 기술적 변수 → 종목 Ranking → 진입 판단 → Portfolio/Risk → Backtest → Walk-Forward → 모의투자 → 소액 실거래

최고 과거수익률보다 **미래정보 없이 재현 가능하고, 거래비용을 포함한 Out-of-Sample 성과가 안정적인 시스템**을 목표로 한다.

기본 종목 선정은 장기간 일봉 데이터를 중심으로 하고, 확보 가능한 최근 수년의 분봉 데이터는 **개장 직후 Entry Timing과 Exit/Risk 개선을 위한 보조 데이터**로 사용한다.

---

# 2. 고정 투자 범위

## Universe

* KOSPI 100
* 과거 시점별 실제 구성 종목 사용
* 현재 구성 종목을 과거에 소급 적용하지 않음
* 편입·편출 및 상장폐지 반영

## 투자 방식

* Long-only
* 현금매매
* 공매도·신용·레버리지·파생상품 제외
* 매수 신호가 없으면 현금 보유 가능
* 항상 전액 투자하지 않음

## 투자 신호에 사용할 데이터

원칙적으로 다음만 사용한다.

* Open
* High
* Low
* Close
* Volume
* 거래대금
* KOSPI 100 지수 가격
* Universe 종목으로 계산한 Market Breadth
* 위 데이터에서 계산 가능한 기술적 변수
* 확보 가능한 최근 수년의 1분봉 또는 분봉 OHLCV

분봉 데이터는 가능하면 1분봉 원본을 보존하고 필요 시 5분·10분·15분봉으로 Resample한다.

데이터 정합성을 위해 Corporate Action, 거래정지, 종목코드 변경, 거래일·거래시간 정보 등은 사용할 수 있으나 투자 Factor로 사용하지 않는다.

## 사용하지 않는 데이터

* 재무제표
* DART
* PER/PBR/ROE 등 펀더멘털
* 뉴스
* 기업가치
* 목표주가
* 애널리스트 의견
* 산업·업종 전망
* 기업별 텍스트 정보

모든 종목에는 가능한 한 **동일한 계산식과 동일한 매매 규칙**을 적용한다.

---

# 3. 시간 및 체결 원칙

기본 종목선정 시스템은 일봉 기준이며, Entry Timing에는 분봉을 추가 사용할 수 있다.

* t일 장 종료 후 t일까지의 일봉 데이터로 종목 Ranking 계산
* 주문은 t+1 거래일부터 가능
* t+1 장 시작 전 매수 후보를 확정할 수 있음
* 기본 Baseline은 다음 날 시가 또는 사전에 정한 개장 직후 시점 체결
* 분봉이 존재하는 기간에는 개장 후 실제 분봉을 이용해 즉시 매수, 대기, 매수 취소 등을 판단할 수 있음
* Slippage와 Gap Risk 반영
* t일 종가를 이용해 t일 시가에 매매한 것으로 처리하지 않음
* 아직 생성되지 않은 분봉을 이용해 주문하지 않음
* 일봉 또는 분봉 내부에서 알 수 없는 가격 발생 순서를 임의로 유리하게 해석하지 않음

같은 봉에서 손절·익절 가격을 모두 통과한 경우에는 사전에 정한 보수적 규칙을 적용한다.

---

# 4. 시스템 구조

초기에는 여러 서버나 복잡한 멀티에이전트를 만들지 않고 **하나의 Python 프로젝트와 재현 가능한 Pipeline**으로 구현한다.

## A. Data & Audit

* KOSPI 100 과거 구성 종목 관리
* 장기간 일봉 OHLCV 수집
* 확보 가능한 최근 수년 분봉 OHLCV 수집
* Corporate Action 처리
* 누락·중복·이상치 검사
* 거래일 및 Timestamp 정렬
* 일봉·분봉 정합성 검사
* Point-in-Time 검사
* 백테스트용 Dataset 생성

분봉은 가능하면 원본 1분봉으로 저장하고 필요 시 상위 주기로 변환한다.

데이터 검증이 끝나기 전에는 모델을 개발하지 않는다.

## B. Technical Cross-Sectional Ranker

매 거래일 KOSPI 100 전체를 동일 기준으로 평가하여 상대적인 매수 우선순위를 결정한다.

주로 장기간 일봉을 사용한다.

후보 변수:

* Trend
* Momentum
* Relative Strength
* 거래량·거래대금 변화
* Volatility
* Drawdown
* Price Compression
* Breakout
* Gap
* Trend Persistence
* Universe 내 Percentile/Rank

출력:

* 종목별 Score
* Universe Rank
* 다음 거래일 매수 검토 후보군

## C. Entry Timing

B의 상위 후보 중 실제 진입 시점을 결정한다.

일봉 정보와 최근 수년의 분봉 정보를 함께 사용할 수 있다.

후보 정보:

* 단기 조정 종료
* 신고가·박스권 돌파
* 변동성 수축 후 확대
* 거래량 확인
* 시가 Gap
* 최근 고점·저점 구조
* Momentum 재가속
* Risk/Reward
* 개장 후 1/5/10/15분 가격 변화
* Opening Range
* 개장 직후 거래량·거래대금 변화
* 시초가 회복 또는 이탈
* VWAP 등 분봉에서 계산 가능한 기술적 변수

비교할 Entry Baseline 예:

* 다음 날 시가 즉시 매수
* 개장 5분 후 매수
* 개장 15분 후 매수
* 초기 조건 충족 시 매수
* Gap 또는 거래량 조건 불충족 시 매수 취소

분봉 모델은 일봉 Ranker보다 복잡성을 추가하므로 **실제 OOS 성과를 개선할 때만 채택**한다.

## D. Market Regime & Risk

KOSPI 100 가격 데이터와 Breadth만으로 시장 상태를 판단한다.

예:

* Risk-on
* Neutral
* Risk-off

활용 변수:

* 지수 추세
* 지수 변동성
* Drawdown
* 상승 종목 비율
* 이동평균선 위 종목 비율
* 신고가·신저가 비율
* 상대강도 분포

Risk-off에서는 신규매수 제한, 투자비중 축소 또는 현금비중 확대를 검토한다.

## E. Portfolio & Execution

* 종목당 비중
* 최대 보유 종목 수
* 현금 관리
* 손절·익절·기간 청산
* 필요 시 분봉 기반 장중 Exit
* 거래비용·세금·Slippage
* Gap
* 미체결 및 부분체결
* 거래정지
* 주문 상태
* 계좌 대조
* 오류 시 주문 중지
* 일별 및 필요 시 장중 운용 기록

---

# 5. AI의 역할

AI는 차트 이미지를 보고 직관적으로 매수·매도하지 않는다.

AI의 핵심 역할은 **사람이 쉽게 찾기 어려운 검증 가능한 변수와 관계를 설계하는 것**이다.

예:

* 장기 Trend + 단기 조정
* 중기 Momentum + 단기 Momentum 가속도
* Relative Strength + 거래량 변화
* 변동성 수축 → 가격 압축 → Breakout
* 상승일/하락일 거래량 비대칭
* Drawdown 회복 속도
* 여러 시간축 Trend 정렬
* Gap 이후 회복 패턴
* 일봉 Signal + 다음날 개장 직후 분봉 패턴
* 개장 직후 거래량 확대 + 가격 돌파
* 시장 Regime과 종목 Signal의 상호작용
* 여러 조건의 발생 순서

AI가 제안한 변수는 반드시 다음을 갖는다.

* 정확한 계산식
* 입력 데이터
* 데이터 주기
* Lookback
* 계산 가능 시점
* 예상 방향
* 논리
* 실패 가능 조건
* 기존 변수와의 중복
* Leakage 위험
* 검증 방법
* 채택/폐기 기준

**코드로 계산할 수 없는 AI의 직관은 실제 매매에 사용하지 않는다.**

---

# 6. 모델 개발 순서

처음부터 CNN/LSTM/Transformer를 사용하지 않는다.

다음 순서로 비교한다.

1. 규칙 기반 Baseline
2. 선형 모델
3. 제한된 Tree 모델
4. XGBoost / LightGBM
5. Cross-sectional Ranking Model
6. 필요할 경우 일봉 Ranker + 분봉 Entry Model 결합
7. 필요할 경우 모델 결합
8. 딥러닝

복잡한 모델은 단순 모델보다 **거래비용 포함 Out-of-Sample 성과가 안정적으로 개선될 때만 채택**한다.

초기 Ranking Target 후보:

* 향후 N일 수익률
* 시장 대비 초과수익률
* 변동성 조정 수익률
* 향후 수익률의 Universe 내 Rank

진입 Timing Label 후보:

* 일정 기간 내 목표수익/손절 Barrier 도달 순서
* Forward Return
* Breakout 지속 여부
* 상대수익률
* 시가 즉시 진입 대비 분봉 Entry의 개선 정도

특정 보유기간이나 손익비를 처음부터 정답으로 고정하지 않는다.

---

# 7. 백테스트 및 통계 검증

반드시 다음을 검사한다.

* Look-ahead Bias
* Survivorship Bias
* Data Leakage
* KOSPI 100 구성 이력 오류
* 상장폐지 누락
* Corporate Action 오류
* 수정주가 오류
* 일봉·분봉 정합성 오류
* 장중 선후 관계 오류
* 거래정지·미체결
* 수수료·세금 누락
* Slippage
* 유동성 문제
* Overfitting
* Selection Bias

표준화, Feature Selection, 임계값 결정, 모델 학습은 해당 Train 구간 안에서만 수행한다.

Random Train/Test Split은 사용하지 않는다.

시간 순서에 따른 Validation과 Walk-Forward를 사용한다.

Label 기간이 겹치면 필요에 따라 Purge/Embargo를 적용한다.

최종 Out-of-Sample은 모델 개발 과정에서 반복 확인하지 않는다.

일봉과 분봉의 가용 기간이 다를 수 있음을 허용한다.

예:

* 장기 Ranker: 약 15년 일봉
* Entry Timing: 최근 약 5년 분봉

이 경우 장기 일봉 전략 성과와 분봉 Entry가 추가된 최근 기간의 성과를 분리해 평가한다.

---

# 8. 성과 평가

최소 다음을 평가한다.

* CAGR
* 누적수익률
* MDD
* Drawdown 기간
* Volatility
* Sharpe
* Sortino
* Calmar
* KOSPI 100 대비 Alpha
* 연도별 수익률
* 상승·횡보·하락장 성과
* 승률
* 평균 이익/손실
* Payoff Ratio
* Turnover
* 거래비용
* Slippage
* 평균 보유기간
* 현금 비중
* 특정 종목/기간 의존도
* Parameter Sensitivity
* Walk-Forward
* 최종 Out-of-Sample

분봉 Entry를 사용할 경우 **시가 즉시 진입 Baseline 대비 성과 개선 여부**도 반드시 평가한다.

ML 자체의 Accuracy, AUC, NDCG, Rank IC보다 **실제 비용 차감 Portfolio 성과를 최종 기준**으로 한다.

---

# 9. 과최적화 방지

모든 전략 변경과 실험을 기록한다.

최소 기록:

* Experiment ID
* 가설
* Feature
* Parameter
* 데이터 주기
* Train/Validation/Test 기간
* 거래비용 가정
* 결과
* 채택/폐기 이유

결과를 본 뒤 공식이나 임계값을 반복 수정해 최고 수익률을 만드는 방식을 피한다.

최종 Test 데이터를 반복 사용했다면 더 이상 진정한 Out-of-Sample으로 간주하지 않는다.

---

# 10. 모의투자 → 실거래

역사적 백테스트가 끝났다고 바로 실거래하지 않는다.

진행 순서:

> Backtest → Out-of-Sample → Walk-Forward → Cost/Slippage Stress Test → Paper Trading → 소액 실거래

## Paper Trading

기본 초기 가상자금은 **5,000,000원**으로 한다.

실제 계좌와 유사하게 다음을 반영한다.

* 현금
* 실제 가능한 정수 주식 수량
* 수수료
* 세금
* Slippage
* 미체결
* 부분체결
* 주문 실패
* 거래정지
* Gap
* API 오류

실거래에서는 전일 장 종료 후 Ranker가 후보를 선정하고, 장 시작 후 실시간 또는 분봉 데이터를 이용해 검증된 Entry 규칙을 실행할 수 있다.

백테스트 예상 주문과 실제 모의 체결 결과의 차이를 기록한다.

## 소액 실거래

다음을 통과한 경우에만 진행한다.

* Walk-Forward
* 최종 OOS
* 거래비용 검증
* 모의투자
* 주문 안정성
* 중복주문 방지
* 계좌 대조
* Kill Switch

---

# 11. 개발 방식

가능하면 직접 새로 구현하기보다 다음을 우선한다.

1. 검증된 Python 라이브러리
2. 공식 API/SDK
3. 유지보수되는 오픈소스
4. 필요한 부분만 직접 구현

초기에는 다음만 필요하다.

* GitHub 저장소 하나
* Python 환경 하나
* 설정 파일
* Parquet 또는 DuckDB
* 자동화 테스트
* 실험 기록
* 재현 가능한 Pipeline

모델 검증 전에는 서버 이중화, 복잡한 멀티에이전트, 실시간 Dashboard, 대규모 Cloud Architecture를 만들지 않는다.

단, **최근 수년 분봉 데이터 수집과 Entry Timing 검증은 초기 연구 범위에 포함한다.**

모의·실거래 단계에서 필요할 경우 증권사 API, PostgreSQL, Naver Cloud, 자동 리포트, 장애복구 등을 추가한다.

---

# 12. 의사결정 원칙

사용자가 세부사항을 모른다는 이유로 작업을 멈추지 않는다.

중요하지 않은 사항은 합리적인 기본값을 선택하고 가정으로 기록한다.

중대한 결정은 다음 형식으로 제시한다.

* 추천안
* 추천 이유
* 중요한 대안
* 결과 영향

항상 가장 단순하게 작동하는 방법을 먼저 선택한다.

---

# 13. 단계별 작업 방식

전체 시스템을 한 번에 만들지 않는다.

현재 지정된 단계만 수행한다.

각 단계 종료 시 다음만 정리한다.

* 완료 산출물
* 검증 결과
* 발견된 문제
* 남은 위험
* 다음 단계 필요 입력
* 다음 단계 추천 작업

사용자의 승인 없이 다음 단계 구현을 시작하지 않는다.

---

# 14. 성공 기준

최종적으로 다음 구조가 실제로 반복 실행 가능해야 한다.

> Point-in-Time OHLCV
> → Technical Features
> → Cross-sectional Ranking
> → 다음 거래일 후보 선정
> → 분봉 기반 Entry Timing
> → Market Regime
> → Portfolio & Risk
> → Backtest
> → Walk-Forward
> → 5,000,000원 Paper Trading
> → Small Live Trading

높은 CAGR 하나가 아니라 **통계적 검증, 재현성, 거래 현실성, 시스템 안정성**을 종합하여 실거래 여부를 결정한다.

분봉 모델은 필수가 아니라 **일봉 기반 Ranker 및 단순 시가 진입 전략보다 OOS 성과 또는 위험관리를 실질적으로 개선할 때만 실제 시스템에 채택한다.**