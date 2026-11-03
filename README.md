# E-commerce Experimentation & Customer Analytics

[![CI](https://github.com/Benvenuteo/ecommerce-experimentation-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/Benvenuteo/ecommerce-experimentation-analytics/actions/workflows/ci.yml) ![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue) ![License](https://img.shields.io/badge/license-MIT-green)

**Portfolio study for Data Analyst roles: SQL · Python · Funnel Analytics · Experimentation · Business Metrics**

An end-to-end reproducible analysis of two **independent** data sources:

1. **REES46 electronics store** — historical `view`, `cart`, `purchase` events; session conversion, product categories, time series and quality checks.
2. **Kevin Hillstrom / MineThatData (2008)** — a genuine, randomized 3-arm marketing experiment; difference in 2-week conversion, Holm multiplicity adjustment, revenue differences with bootstrap uncertainty and balance checks.

The two sources are unrelated to each other and identities cannot be joined. Historical e-commerce event analytics are descriptive; only randomized experiment data supports a causal intent-to-treat comparison of the original campaigns. Currency for REES46 is deliberately labelled "source units" until confirmed in the data documentation. No claim to platform margin or campaign profit is made.

## Results (real data run)

Full report: [examples/real_report.html](examples/real_report.html) (download and open locally; GitHub does not render HTML).

**REES46 electronics store** (885,129 events, 490,633 identified sessions, 2020-09-24 to 2021-02-28; descriptive only)

| Metric | Value |
| --- | --- |
| Session purchase rate | 4.96% (24,348 / 490,633) |
| View → cart | 8.44% |
| Cart → purchase | 49.72% |
| Ordered full funnel | 4.20% |
| Top category by gross item value | `computers.components.videocards`: 2.60M of 5.13M source units (~51%) |

**Hillstrom randomized experiment** (64,000 customers, SRM p = 0.904, all baseline |SMD| < 0.01)

| Arm vs. no-email control | Conversion | Lift (pp) | 95% CI (pp) | Holm p | Δ spend / customer |
| --- | --- | --- | --- | --- | --- |
| Mens E-Mail | 1.25% vs 0.57% | +0.68 | [0.50, 0.86] | <0.0001 | $0.77 [0.51, 1.05] |
| Womens E-Mail | 0.88% vs 0.57% | +0.31 | [0.15, 0.47] | 1.6e-4 | $0.42 [0.16, 0.68] |

<p>
<img src="docs/img/funnel_reach.png" width="48%" alt="Session stage reach">
<img src="docs/img/monthly_value.png" width="48%" alt="Monthly gross purchase-item value">
<img src="docs/img/experiment_conversion.png" width="48%" alt="Conversion rate by arm">
<img src="docs/img/experiment_lift_ci.png" width="48%" alt="Lift confidence intervals">
</p>

Caveats: no costs or margins, so no ROI claim; Mens vs Womens not tested directly; 27% of events lack a category code (`[unknown]` is the 2nd-largest category by value, ~9.6%); 655 potential exact duplicate rows were kept (see methodology).

## Quick start — Windows PowerShell

Requires Python 3.10+, an internet connection for package installation, and enough disk space for the source events + SQLite database.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m ecommerce_analytics demo --output outputs/demo
```

Open `outputs/demo/index.html` in a browser. **This report is explicitly labelled SYNTHETIC DEMONSTRATION**, not a finding from REES46 or the original Hillstrom study.

### Run on original publicly available datasets

Download the two source files following [docs/data_sources.md](docs/data_sources.md). The official REES46 `.csv.gz` can be used without decompressing. Place files at the indicated paths, then:

```powershell
.\.venv\Scripts\python.exe -m ecommerce_analytics run `
  --events data/raw/electronics-events.csv.gz `
  --experiment data/raw/hillstrom.csv `
  --output outputs/real-001
```

Each run must use a fresh output directory. Missing or invalid source files stop execution with clear exceptions. Nothing quietly falls back to generated data in `run` mode.

### Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m ecommerce_analytics demo --output outputs/demo
pytest -q
ruff check src tests
```

## What the pipeline produces

```text
outputs/<run>/
  index.html                          standalone HTML report (charts embedded)
  run_manifest.json                   run mode, local input and report paths
  funnel/
    events.sqlite                     normalized input rows and session view
    funnel_metrics.json               quality and KPI definitions
    monthly_sales.csv                 calendar-month revenue & purchasers
    category_sales.csv                ranked product-category revenue
  experiment/
    experiment_metrics.json           primary comparisons, CIs and caveats
    experiment_arms.csv               three-arm summary
    experiment_comparisons.csv        ITT estimates, spend effect, corrected p
    experiment_balance.csv            baseline standardized differences
```

## Architecture

```mermaid
flowchart TD
    A[REES46 CSV / CSV.gz] --> B[Chunked validator]
    B --> C[SQLite events + sessions]
    C --> D[Descriptive KPI exports]
    E[Hillstrom CSV] --> F[Strict experiment validator]
    F --> G[SRM + randomized ITT + bootstrap]
    G --> H[Trial effect exports]
    D --> I[Self-contained HTML report]
    H --> I
```

## Scientific safeguards

- **Purchase events may be order items**; without order IDs we do not invent order count, AOV, refund-adjusted revenue, or margin.
- Session denominators exclude rows with unknown session IDs; unknown-session purchase value remains in event-level value.
- Session paths are reported separately from unordered event reach. Missing cart events are not treated as proven abandonment.
- Randomized comparisons retain the three original arms and use **two** predeclared conversion contrasts vs. control, with Holm adjustment.
- Spend differences are **per randomized customer** including zeros, rather than per buyer (post-treatment conditioning bias).
- No attempt to merge customers or make cross-dataset causal claims.
- Raw-source data is excluded from version control; source attribution and caveats are documented.

See [research protocol and KPI dictionary](docs/methodology.md) for formulas and limitations. See [sample SQLite analytical queries](sql/analytics.sql).

## Test and QA

```bash
pytest -q
ruff check src tests
```

GitHub Actions validates lint, unit/integration tests and a complete offline demo run. Demo generation is deterministic. A full real-data report requires the original source files; no real-data performance or business-effect claims are made before they are processed.
