# Research protocol and metric definitions

## Research questions

- What fraction of recorded sessions reached each stage (view, add to cart, purchase)?
- How is observed purchase line value distributed by category and month?
- Did each randomly assigned Hillstrom email variant affect 2-week conversion?
- How much incremental 2-week revenue per randomized recipient is consistent with the observed experiment?

## Data sources

- REES46 events in the electronics store, Sep 2020–Feb 2021 (observed event window in the analysed file). Observational event log. One row represents a product event. This is **not** an orders table or a controlled experiment.
- Kevin Hillstrom, MineThatData 2008. Randomized 3-arm e-mail experiment with 64,000 customers. Each row represents one randomly assigned customer. Pre-treatment covariates: recency, history, past mens/womens purchases, new customer indicator, ZIP area category, and channel. Post-treatment outcomes: visit, conversion, spend over two weeks.

Do not join these independent populations. Do not extrapolate them to current customer behavior of any other business.

## KPI dictionary

| Metric | Definition | Limitation |
| --- | --- | --- |
| Event rows | Valid records with timestamp, event type, user ID, and nonnegative or permitted missing price | Not unique visitors |
| Identified session | Unique `(user_id, user_session)` where session ID is present | Excludes unknown sessions; no sessionization imputation |
| Purchase-session conversion | Sessions with ≥1 purchase event / all identified sessions | Session conversion, not user conversion |
| View/cart/purchase reach | Number of distinct identified sessions with respective stage | Stage counts are not nested |
| View→cart first-event reach | Sessions with first cart at/after first view / sessions with view | May understate a later repeated path |
| Cart→purchase first-event reach | Sessions with first purchase at/after first cart / sessions with cart | May understate a later repeated path |
| Strict first-event full funnel | First view ≤ first cart ≤ first purchase / sessions with view | Only earliest events; timestamps can tie |
| Gross purchase item value | Sum purchase event prices across valid source rows | Source units; no order ID; no profit / margin / net revenue |
| Purchase item value | Gross value in identified sessions / item purchase events in identified sessions | Not AOV; no order ID |
| Repeat purchasing user | Identified user with purchases across 2+ distinct identified sessions | Unknown sessions omitted; observation-window censoring |
| Trial conversion rate | Converted randomized customers / assigned customers | Two-week endpoint |
| ITT absolute lift | Treatment conversion rate − control conversion rate | Percentage points (pp) |
| ITT spend difference | Treatment mean spend − control mean spend, including zeros | USD / assigned customer; not profit |

## Data quality and exclusion policy

- Required columns checked before load.
- Invalid timestamps, event types, negative prices and missing user IDs excluded and counted; missing purchase prices excluded.
- Missing category / brand permitted; grouped in an explicit `[unknown]` category.
- Missing `user_session` events remain in overall value metrics but are not attributed to identified sessions.
- Exact duplicate rows are **not** dropped, since repeated purchase-item events may be legitimate. Investigate upstream instrumentation before deduplication.
- IDs are strings; 64-bit numeric parsing does not damage extremely large category IDs.
- Experiments reject missing, non-binary, non-finite and invalid treatment data rather than imputing it.

## Causal analysis specification

- Hypothesis 1: Mens e-mail versus no e-mail changes 2-week conversion.
- Hypothesis 2: Womens e-mail versus no e-mail changes 2-week conversion.
- Randomization unit: customer; primary metric: conversion (binary, 2-week).
- Two-sided difference-in-proportion z-tests; Holm family-wise error control across exactly two *primary* hypotheses at alpha=0.05.
- Risk-difference uncertainty: 95% Newcombe independent-proportion confidence intervals (unadjusted; do not use them to overrule Holm decisions).
- Revenue: differences in unconditional spend per assigned customer, including non-converters; percentile bootstrap with deterministic seed. Revenue analysis is secondary/exploratory; its interval is not multiplicity-adjusted.
- Sample ratio mismatch: chi-square 1:1:1 (source documentation says allocation 1/3 each). Investigate severe mismatch before treating estimates as trustworthy.
- Baseline balance: standardized mean differences of numeric pre-treatment covariates; |SMD|>0.1 flags a review, not automatic proof of biased randomization.
- Cost and margin not observed; no causal claims for ROI or profit. Two-week effects do not establish long-term retention.

## Reproducibility and limitations

- Deterministic seeded bootstraps and synthetic smoke tests.
- Per-run output path must be new/empty; SQL database is never silently overwritten.
- SQLite ingests REES46 CSV in chunks to bound Python memory footprint. SQLite indices and aggregation may consume substantial disk/CPU for very large datasets.
- Historical data cannot establish current customer behavior; the sources are illustrations of transferable analytical methods.
