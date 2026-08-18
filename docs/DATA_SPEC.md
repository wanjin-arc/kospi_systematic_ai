# Data Specification — Phase 1

> **v24 implementation note:** The original logical specification below is retained for design history. Production v24 passed its independent audit and is partitioned under `data/processed/v24/development/` and `data/sealed/final_oos_v24/`. The latter remains inaccessible to ordinary development work.

**Version:** phase1-v1  
**Research window:** 2011-01-01 through 2025-12-31  
**Development-visible window:** through 2023-12-31  
**Sealed final OOS:** 2024-01-01 through 2025-12-31

## 1. Point-in-Time Principle

For a query made as of trading date `t`, the dataset may return only:

- KOSPI 100 memberships effective on `t`;
- raw prices dated no later than `t`;
- corporate actions effective no later than `t`;
- symbol/code information effective no later than `t`;
- KOSPI 100 index observations dated no later than `t`.

`valid_from` is inclusive and `valid_to` is exclusive. A current constituent list may never be extended backward. A missing active-member bar is an error unless a separately sourced suspension interval explains it; even then it remains a warning and is never filled with an invented price.

## 2. Source and Lineage Requirements

Every source file has an entry in `data/manifests/source_manifest.csv` with source organisation, product/screen, URL, retrieval timestamp, coverage, row count, SHA-256, and licence/terms reference. Every normalized row also retains `source_file` and `source_sha256`.

Authoritative source priority:

1. KRX official historical extract or contracted historical data product.
2. KRX Data Marketplace export with a reference date and reproducible query parameters.
3. A third-party wrapper only as an acquisition aid or independent cross-check; it cannot be the sole lineage record.

## 3. Logical Tables

### `symbol_master`

| Column | Type | Rule |
|---|---|---|
| `symbol_id` | string | Stable internal identity across display-code changes |
| `symbol` | string | Six-digit KRX display code effective for the interval |
| `isin` | string | ISIN when available; never used as a factor |
| `company_name` | string | Point-in-time display name; never used as a factor |
| `valid_from`, `valid_to` | date | Code/name version interval; end is exclusive |
| `listing_date`, `delisting_date` | date | Audit/execution fields only |
| `source_file`, `source_sha256` | string | Immutable lineage |

Unique key: `(symbol_id, valid_from)`. Intervals for a `symbol_id` may not overlap.

### `universe_membership`

| Column | Type | Rule |
|---|---|---|
| `index_name`, `index_code` | string | Must resolve to KOSPI 100 in the source snapshot |
| `symbol_id`, `symbol`, `company_name` | string | Constituent identity for that effective interval |
| `valid_from`, `valid_to` | date | Membership interval; end is exclusive |
| `announcement_at` | timestamp with offset | Announcement time when source supplies it |
| `effective_date` | date | Actual effective membership date |
| `retrieved_at_kst` | timestamp with offset | Acquisition audit time |
| lineage columns | string | Source file and SHA-256 |

Every confirmed trading session must return exactly 100 distinct active `symbol_id` values. The pipeline does not assume the nearest available snapshot is correct for an earlier date.

The user-supplied snapshot currently yields 99 members on 26 confirmed exchange sessions. This is retained as a validation error rather than filled. The exactly-100 invariant remains frozen until the upstream constituent history proves the missing entries or the user approves a documented rule for legitimate temporary vacancies.

### `trading_calendar`

Columns: `trade_date`, `is_trading_day`, official open/close time in KST, early-close flag, and lineage. Exchange sessions—not weekdays—define lookbacks and forward horizons.

For the current partial bundle, session dates are derived from the supplied index observations. This is sufficient for date alignment auditing, but blank official hours and early-close flags remain warnings and block execution-ready status.

### `ohlcv_raw`

| Column | Type | Rule |
|---|---|---|
| `trade_date` | date | Official exchange session |
| `symbol_id`, `symbol` | string | Point-in-time identity/code |
| `open`, `high`, `low`, `close` | decimal | Raw tradable prices; positive while `market_status=TRADING` |
| `volume` | integer/decimal | Non-negative shares |
| `traded_value` | integer/decimal | Non-negative KRW value |
| `market_status` | enum-like string | `TRADING`, `HALTED`, or explicitly documented source state |
| lineage columns | string | Source file and SHA-256 |

Unique key: `(trade_date, symbol_id)`. Required invariant:

`low ≤ open ≤ high`, `low ≤ close ≤ high`, and `high ≥ low`.

### `corporate_actions`

Columns: symbol identity, action type, offset-aware announcement time, effective date, share-factor numerator/denominator, cash amount/currency, and lineage. Corporate actions are audit/adjustment events, not predictive features.

For split-like events, define the event share factor as:

`q = new shares / old shares`

The row-local cumulative factor is:

`F(i,t) = product of q for symbol i with effective_date ≤ t`

Point-in-time analysis fields are:

- `analysis_price(i,t) = raw_price(i,t) × F(i,t)`
- `analysis_volume(i,t) = raw_volume(i,t) / F(i,t)`

This creates a continuous original-share basis without allowing a future split to rewrite rows before its effective date. Cash dividends do not alter analysis prices.

### `index_ohlcv_raw`

KOSPI 100 index `trade_date`, code/name, OHLC, volume, traded value, and lineage. OHLC consistency tests are identical to stocks. The index is the primary benchmark and regime input; no index fundamental fields are admitted.

### `suspensions`

Symbol identity, inclusive suspension start/end dates, reason, and lineage. An open-ended suspension has an empty `suspended_to`.

## 4. Cleaning and Output Rules

The build runs only after every required file and column is present and no `BLOCKER` or `ERROR` remains. It then:

1. keeps raw values and lineage unchanged;
2. filters analysis OHLCV to active KOSPI 100 membership dates;
3. adds row-local split-adjusted analysis fields;
4. partitions development rows through 2023-12-31;
5. writes 2024–2025 rows only into the sealed final-OOS directory;
6. creates deterministic manifests containing SHA-256 hashes.

The current runtime can write deterministic gzip CSV. The Phase 1 gate additionally requires a Parquet or DuckDB conversion and its own schema/hash validation once that dependency is available.

## 5. Automated Checks

- required file and column presence;
- empty required tables;
- ISO dates and offset-aware timestamps;
- six-digit codes and stable symbol IDs;
- overlapping identity or membership intervals;
- duplicate bars or calendar dates;
- OHLC range violations and negative activity;
- exactly 100 constituents on each exchange session;
- missing bars for active members, with separate suspension classification;
- positive share-adjustment factors;
- development/final-OOS physical separation;
- no history query later than the requested as-of date;
- ordinary development API refusal for dates in final OOS.

## 6. Query Contract

After a successful build:

- `universe_on(t)` returns only memberships effective on `t`.
- `history_through(symbol_id, t)` returns only bars dated `≤ t`.
- requests dated 2024-01-01 or later through the ordinary development interface raise `FinalOOSAccessError`.

Synthetic unit tests demonstrate the contract but do not constitute actual KOSPI 100 data validation.

## 7. Supplied-export normalization

`kospi100_data.normalize_user_exports` is the reproducible adapter for the two supplied files. It:

- accepts the UTF-8 BOM daily membership snapshot and CP949 index export;
- requires a complete weekday membership grid before inferring intervals;
- reproduces every daily membership snapshot from the compressed intervals;
- detects and removes six concatenation-boundary `일자` markers attached to the unused market-cap field;
- validates and sorts all index dates and OHLC values;
- converts `거래량(천주)` to shares and `거래대금(백만원)` to KRW;
- records original filenames and SHA-256 hashes on every normalized row and in the source manifest.

The adapter does not establish upstream provenance, official index code, ISIN identity, announcement time, listing/delisting events, or corporate-action history. Those remain separate audit requirements.
