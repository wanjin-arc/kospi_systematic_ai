# Phase 1 Data Quality Report

> **Superseded status notice (2026-08-18):** This report records the earlier two-file partial-input audit. The later v24 production package passed the independent Phase-1 gate. The authoritative completion evidence is `data/quality/v24/phase1_v24_independent_audit.json`; Phase 2 was subsequently completed without reopening final OOS.

**Report date:** 2026-08-16  
**Status:** **BLOCKED — partial actual data normalized; Phase 1 gate not passed**

## Conclusion

The supplied historical KOSPI 100 membership and index-price CSVs were read, audited, normalized, and passed the checks applicable to their fields. The Phase 1 build was then executed and correctly refused to create processed development/final-OOS datasets.

Phase 1 is not complete because individual-stock OHLCV, corporate actions, and suspension intervals are absent. Stable security identity and upstream source metadata are also unresolved. No strategy, model, feature, or backtest was run.

## Supplied source profile

| Source | Coverage | Rows | Key result |
|---|---:|---:|---|
| Daily membership snapshots | 2010-01-04–2025-12-31 | 417,273 | 4,173 complete weekday snapshots; 174 tickers; no duplicate date/ticker or missing field |
| Index OHLCV | 2010-01-04–2025-12-30 | 3,939 | 3,939 unique exchange dates; no invalid OHLC, non-positive price, or negative activity |

The membership file is an exact weekday grid, while the index contains exchange sessions. All 3,939 index dates have a membership snapshot. The 234 membership-only weekdays are non-session dates and are excluded by the derived exchange calendar rather than deleted from the immutable source.

## Membership validation

| Check | Result |
|---|---:|
| Daily rows | 417,273 |
| Unique dates | 4,173 |
| Unique six-digit tickers | 174 |
| Unique names | 214 |
| Compressed membership/name intervals | 232 |
| Interval reconstruction mismatched dates | 0 |
| Duplicate rows or date/ticker keys | 0 |
| Dates with 100 members | 4,146 weekdays |
| Dates with 99 members | 27 weekdays / 26 exchange sessions |
| Constituent-set change dates | 44 |
| Consecutive-snapshot name-change events | 48 |

The 26 exchange-session exceptions are 2011-03-30, 2011-06-07, 2013-06-11–13, 2014-11-19, and 2017-05-11–06-08 excluding the 2017-06-06 holiday. They were not filled or forward/backward substituted. The frozen exactly-100 rule therefore raises 26 `UNIVERSE_SIZE_MISMATCH` errors pending upstream evidence.

## Index validation

| Check | Result |
|---|---:|
| Unique / duplicate dates | 3,939 / 0 |
| High below low | 0 |
| Open or close outside low–high | 0 |
| Non-positive OHLC | 0 |
| Negative volume / traded value | 0 / 0 |
| Reported change mismatches, tolerance 0.011 | 0 |
| Reported percent-change mismatches, tolerance 0.011 | 0 |
| Source concatenation blocks | 8 two-year blocks |
| Corrupt boundary markers | 6 `일자` suffixes on the unused market-cap field; detected and removed |

The source was globally non-monotonic because descending two-year exports were concatenated. Normalized dates are ascending. `거래량(천주)` was multiplied by 1,000 and `거래대금(백만원)` by 1,000,000. Raw source files remain unchanged and are identified by SHA-256.

## Automated validation result

| Severity | Count | Findings |
|---|---:|---|
| Blocker | 3 | Missing `ohlcv_raw.csv`, `corporate_actions.csv`, `suspensions.csv` |
| Error | 26 | 99 active members where the frozen rule expects 100 |
| Warning | 2 | Official session times and early-close flags absent on 3,939 derived calendar rows |

The source profile additionally records two provenance blockers that are not yet machine-enforced: upstream source/query/licence metadata are missing, and `symbol_id` is provisionally based on the six-digit display code because ISIN/code-change/listing/delisting evidence was not supplied.

## Tests and reproducibility

- Python source compilation: passed.
- Automated tests: 7 passed.
- Actual daily-membership-to-interval round trip: 0 mismatched dates.
- Pipeline build gate: passed by refusing output with 3 blockers and 26 errors.
- Development/final-OOS processed files: none; existing output directories remain empty because the gate failed.
- Strategy performance metrics: not computed.

Machine-readable evidence is in `data/quality/source_profile.json` and `data/quality/phase1_report.json`.

## Required resolution

1. Supply raw daily OHLCV and traded value for every point-in-time constituent, including the 2010 warm-up period.
2. Supply split/reverse-split/stock-dividend and other required corporate-action events.
3. Supply trading-suspension intervals and listing/delisting/code-change/ISIN evidence.
4. Provide the upstream source screen/product, query parameters, retrieval time, and terms reference for both current CSVs.
5. Resolve the 26 99-member sessions from an authoritative constituent history. Do not invent a hundredth member.
6. Add official session hours and early-close flags before execution-ready approval.

## Gate decision

Phase 1 remains **blocked**. The normalized partial inputs are valid staging artifacts, not a complete point-in-time market dataset. Phase 2 must not start.
