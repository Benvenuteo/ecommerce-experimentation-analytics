"""Produce a self-contained HTML portfolio report with defensible KPI definitions."""

from __future__ import annotations

import base64
import html
from io import BytesIO
from numbers import Real
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def _embedded_png(figure: Any) -> str:
    """Serialize a chart into a data URI so the report works offline."""
    memory = BytesIO()
    figure.savefig(memory, format="png", dpi=140, bbox_inches="tight")
    plt.close(figure)
    return f"data:image/png;base64,{base64.b64encode(memory.getvalue()).decode('ascii')}"


def _p_value(value: float | None) -> str:
    """Avoid displaying very small p-values as zero after rounding."""
    if value is None or pd.isna(value):
        return "n/a"
    if value < 0.0001:
        return "<0.0001"
    if value < 0.001:
        return f"{value:.2e}"
    return f"{value:.4f}"


def _fraction(value: float | None) -> str:
    """Format rates as percentages; missing denominators remain visible."""
    return "n/a" if value is None else f"{value:.2%}"


def _format_table_value(value: Any, column: str, *, digits: int) -> str:
    """Format table cells according to the semantic meaning of their column."""
    if value is None or pd.isna(value):
        return "n/a"

    if isinstance(value, bool) or type(value).__name__ == "bool_":
        return "Yes" if bool(value) else "No"

    if not isinstance(value, Real):
        return str(value)

    number = float(value)
    name = column.lower()

    if "p_value" in name or "p-value" in name:
        return _p_value(number)

    if name.endswith("_pp") or "difference_pp" in name or "lift" in name:
        return f"{number:+.{digits}f} pp"

    if "rate" in name or "share" in name:
        return f"{number:.2%}"

    count_columns = {
        "count",
        "customers",
        "visits",
        "conversions",
        "purchased_items",
        "buyers",
        "numerator",
        "denominator",
        "source_rows",
        "accepted_rows",
        "rows",
        "purchase_line_events",
    }
    normalized_name = name.replace(" ", "_").replace("-", "_")

    if (
            normalized_name in count_columns
            or normalized_name.endswith("_count")
            or normalized_name.endswith("_rows")
            or normalized_name.startswith(
        ("invalid_", "missing_", "with_", "view_then_", "cart_then_")
    )
            or normalized_name == "purchase_without_session"
    ):
        return f"{int(round(number)):,}"

    if name.endswith("_usd") or "spend" in name:
        money_digits = (
            4
            if (
                    "per_" in name
                    or "per assigned customer" in name
                    or "per randomized customer" in name
            )
            else 2
        )
        return f"${number:,.{money_digits}f}"

    return f"{number:,.{digits}f}"


def _html_table(data: pd.DataFrame, *, digits: int = 4) -> str:
    """Render bounded-size numeric tables with column-aware number formatting."""
    frame = data.copy()

    for column in frame.columns:
        frame[column] = frame[column].map(
            lambda value, name=column: _format_table_value(
                value,
                name,
                digits=digits,
            )
        )

    return frame.to_html(
        index=False,
        escape=True,
        classes="table",
        border=0,
    )


def _format_interval(
    values: Any,
    *,
    suffix: str,
    currency: bool = False,
) -> str:
    """Format a two-sided confidence interval stored as a two-item sequence."""
    if not isinstance(values, (list, tuple)) or len(values) != 2:
        return "n/a"

    lower, upper = values

    if lower is None or upper is None or pd.isna(lower) or pd.isna(upper):
        return "n/a"

    if currency:

        def format_currency(amount: float) -> str:
            sign = "-$" if amount < 0 else "$"
            return f"{sign}{abs(amount):,.4f}"

        return (
            f"[{format_currency(float(lower))}, "
            f"{format_currency(float(upper))}] {suffix}"
        )

    return f"[{float(lower):+.4f}, {float(upper):+.4f}] {suffix}"


def write_report(
    output: Path,
    funnel: dict[str, Any],
    experiment: dict[str, Any],
    *,
    demo: bool = False,
) -> Path:
    """
    Create an offline HTML report with explicit definitions,
    statistical uncertainty and analytical caveats.
    """
    output.mkdir(parents=True, exist_ok=True)

    session = funnel["sessions"]
    events = funnel["events"]
    quality = funnel["quality"]

    arms = pd.DataFrame(experiment["arms"])
    comparisons = pd.DataFrame(experiment["comparisons"])

    sales = pd.read_csv(output / "funnel" / "monthly_sales.csv")
    categories = pd.read_csv(output / "funnel" / "category_sales.csv")
    balancing = pd.read_csv(output / "experiment" / "experiment_balance.csv")

    # ------------------------------------------------------------------
    # 1. Session reach chart and explicitly denominated funnel rates.
    # ------------------------------------------------------------------
    stage_labels = [
        "All sessions",
        "Viewed",
        "Added to cart",
        "Purchased",
    ]

    stage_counts = [
        session["total_with_known_session_id"],
        session["with_view"],
        session["with_cart"],
        session["with_purchase"],
    ]

    fig, ax = plt.subplots(figsize=(8, 3.3))

    bars = ax.bar(stage_labels, stage_counts)

    ax.set_ylabel("Distinct user/session pairs")
    ax.set_title("Session stage reach (non-exclusive, not a strict funnel)")
    ax.tick_params(axis="x", rotation=10)

    ax.bar_label(
        bars,
        labels=[f"{value:,}" for value in stage_counts],
        padding=3,
        fontsize=8,
    )

    funnel_plot = _embedded_png(fig)

    funnel_rate_rows = [
        {
            "Metric": "Session purchase rate",
            "Numerator": session["with_purchase"],
            "Denominator": session["total_with_known_session_id"],
            "Rate": session["purchase_session_conversion_rate"],
            "Definition": (
                "Sessions with at least one purchase / "
                "sessions with a known session ID"
            ),
        },
        {
            "Metric": "View-to-cart reach rate",
            "Numerator": session["view_then_cart"],
            "Denominator": session["with_view"],
            "Rate": session["view_to_cart_reach_rate"],
            "Definition": (
                "Sessions with cart after view / "
                "sessions with at least one view"
            ),
        },
        {
            "Metric": "Cart-to-purchase reach rate",
            "Numerator": session["cart_then_purchase"],
            "Denominator": session["with_cart"],
            "Rate": session["cart_to_purchase_reach_rate"],
            "Definition": (
                "Sessions with purchase after cart / "
                "sessions with at least one cart"
            ),
        },
        {
            "Metric": "Ordered full-funnel rate",
            "Numerator": session["view_then_cart_then_purchase"],
            "Denominator": session["with_view"],
            "Rate": session["ordered_full_funnel_rate"],
            "Definition": (
                "Sessions with view, then cart, then purchase / "
                "sessions with at least one view"
            ),
        },
    ]

    funnel_rates = pd.DataFrame(funnel_rate_rows)

    # ------------------------------------------------------------------
    # 2. Monthly and category purchase-item value.
    # ------------------------------------------------------------------
    first_event = pd.to_datetime(
        events.get("first_at_utc"),
        utc=True,
        errors="coerce",
    )

    first_month_is_partial = bool(
        pd.notna(first_event)
        and first_event.day > 1
        and not sales.empty
    )

    fig, ax = plt.subplots(figsize=(8, 3.2))

    if not sales.empty:
        month_labels = sales["month"].astype(str).tolist()

        if first_month_is_partial:
            month_labels[0] = f"{month_labels[0]}*"

        x_positions = list(range(len(sales)))

        ax.plot(
            x_positions,
            sales["revenue"],
            marker="o",
        )

        ax.set_xticks(
            x_positions,
            labels=month_labels,
        )

        ax.tick_params(axis="x", rotation=25)

    ax.set_ylabel("Gross purchase-item value (source units)")
    ax.set_title("Historical monthly purchase-event values")

    sales_plot = _embedded_png(fig)

    category_display = categories.rename(
        columns={
            "revenue": "gross_purchase_item_value_source_units",
            "purchased_items": "purchased_items",
        }
    ).copy()

    category_columns = [
        column
        for column in (
            "category",
            "purchased_items",
            "gross_purchase_item_value_source_units",
        )
        if column in category_display.columns
    ]

    category_display = category_display[category_columns].head(12).rename(
        columns={
            "category": "Purchase category",
            "purchased_items": "Purchase line events",
            "gross_purchase_item_value_source_units": (
                "Gross purchase-item value (source units)"
            ),
        }
    )

    # ------------------------------------------------------------------
    # 3. Data-quality audit with rates relative to all source rows.
    # ------------------------------------------------------------------
    source_rows = int(quality.get("source_rows", 0))

    qa_rows = []

    for check, count in quality.items():
        qa_rows.append(
            {
                "quality_check": check,
                "count": count,
                "share_of_source_rows": (
                    count / source_rows if source_rows else None
                ),
            }
        )

    qa = pd.DataFrame(qa_rows).rename(
        columns={
            "quality_check": "Data-quality check",
            "count": "Rows",
            "share_of_source_rows": "Share of source rows",
        }
    )

    # ------------------------------------------------------------------
    # 4. Experiment conversion chart and comparison table.
    # ------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 3.3))

    if not arms.empty:
        bars = ax.bar(
            arms["arm"],
            arms["conversion_rate"] * 100,
        )

        ax.bar_label(
            bars,
            labels=[
                f"{value:.2f}%"
                for value in arms["conversion_rate"] * 100
            ],
            padding=3,
            fontsize=8,
        )

    ax.set_ylabel("Conversion rate (%)")
    ax.set_title(
        "Randomized experiment: 2-week conversion by assigned arm"
    )

    ab_plot = _embedded_png(fig)

    # Conversion lift with unadjusted Newcombe confidence intervals.
    fig, ax = plt.subplots(figsize=(8, 3.2))

    positions = list(range(len(comparisons)))

    effects = comparisons[
        "conversion_rate_difference_pp"
    ].astype(float).tolist()

    intervals = comparisons[
        "conversion_diff_ci_95_pp"
    ].tolist()

    if positions:
        left_errors = [
            max(0.0, effect - float(interval[0]))
            for effect, interval in zip(
                effects,
                intervals,
                strict=True,
            )
        ]

        right_errors = [
            max(0.0, float(interval[1]) - effect)
            for effect, interval in zip(
                effects,
                intervals,
                strict=True,
            )
        ]

        ax.errorbar(
            effects,
            positions,
            xerr=[left_errors, right_errors],
            fmt="o",
            capsize=4,
        )

        ax.set_yticks(
            positions,
            labels=comparisons["treatment"].tolist(),
        )

    ax.axvline(
        0,
        linewidth=1,
        linestyle="--",
    )

    ax.set_xlabel(
        "Absolute conversion-rate difference vs control (percentage points)"
    )

    ax.set_title("95% Newcombe intervals (unadjusted)")

    effects_plot = _embedded_png(fig)

    # Format confidence intervals before rendering the table.
    comparison_display = comparisons.copy()

    comparison_display["conversion_ci_95_pp"] = (
        comparison_display["conversion_diff_ci_95_pp"].map(
            lambda value: _format_interval(
                value,
                suffix="pp",
            )
        )
    )

    comparison_display["incremental_spend_ci_95_usd_display"] = (
        comparison_display["incremental_spend_ci_95_usd"].map(
            lambda value: _format_interval(
                value,
                suffix="USD",
                currency=True,
            )
        )
    )

    comparison_columns = [
        "treatment",
        "conversion_rate_difference_pp",
        "conversion_ci_95_pp",
        "conversion_p_value_raw",
        "conversion_p_value_holm",
        "incremental_spend_per_assigned_customer_usd",
        "incremental_spend_ci_95_usd_display",
        "estimated_incremental_revenue_for_treated_arm_usd",
        "conversion_significant_holm_0_05",
    ]

    comparison_columns = [
        column
        for column in comparison_columns
        if column in comparison_display.columns
    ]

    comparison_display = comparison_display[
        comparison_columns
    ].rename(
        columns={
            "treatment": "Treatment vs no-email control",
            "conversion_rate_difference_pp": "Conversion lift",
            "conversion_ci_95_pp": "Unadjusted 95% CI for lift",
            "conversion_p_value_raw": "Raw p-value",
            "conversion_p_value_holm": "Holm-adjusted p-value",
            "incremental_spend_per_assigned_customer_usd": (
                "Incremental spend per assigned customer"
            ),
            "incremental_spend_ci_95_usd_display": (
                "Bootstrap 95% CI for incremental spend"
            ),
            "estimated_incremental_revenue_for_treated_arm_usd": (
                "Estimated incremental spend in treatment arm"
            ),
            "conversion_significant_holm_0_05": (
                "Significant after Holm (0.05)"
            ),
        }
    )

    arms_display = arms.rename(
        columns={
            "arm": "Assigned campaign arm",
            "customers": "Customers",
            "visits": "Visits",
            "conversions": "Conversions",
            "visit_rate": "Visit rate",
            "conversion_rate": "Conversion rate",
            "mean_spend_per_randomized_customer_usd": (
                "Mean spend per randomized customer"
            ),
            "total_spend_usd": "Total spend",
        }
    )

    balancing_display = balancing.rename(
        columns={
            "treatment": "Treatment arm",
            "baseline_variable": "Baseline variable",
            "standardized_mean_difference": (
                "Standardized mean difference"
            ),
            "above_abs_0_1_review_threshold": (
                "Above absolute 0.1 review threshold"
            ),
        }
    )

    # ------------------------------------------------------------------
    # 5. Dynamic executive summary.
    # ------------------------------------------------------------------
    control_rows = arms.loc[
        arms["arm"] == "No E-Mail"
    ]

    control_conversion = (
        float(control_rows.iloc[0]["conversion_rate"])
        if not control_rows.empty
        else None
    )

    executive_lines = []

    if control_conversion is not None:
        for _, row in comparisons.iterrows():
            treatment_rows = arms.loc[
                arms["arm"] == row["treatment"]
            ]

            treatment_conversion = (
                float(treatment_rows.iloc[0]["conversion_rate"])
                if not treatment_rows.empty
                else None
            )

            ci_text = _format_interval(
                row["conversion_diff_ci_95_pp"],
                suffix="pp",
            )

            p_text = _p_value(
                float(row["conversion_p_value_holm"])
            )

            if treatment_conversion is None:
                conversion_text = "conversion rate unavailable"
            else:
                conversion_text = (
                    f"{treatment_conversion:.2%} vs "
                    f"{control_conversion:.2%} in the control group"
                )

            executive_lines.append(
                f"<li><strong>{html.escape(str(row['treatment']))}:</strong> "
                f"{conversion_text}; estimated conversion lift "
                f"{float(row['conversion_rate_difference_pp']):+.4f} pp "
                f"(unadjusted 95% CI {html.escape(ci_text)}; "
                f"Holm-adjusted p {html.escape(p_text)}).</li>"
            )

    if not comparisons.empty:
        strongest = comparisons.iloc[
            comparisons["conversion_rate_difference_pp"].abs().argmax()
        ]

        strongest_text = (
            f"The largest point estimate of conversion lift versus control was for "
            f"{html.escape(str(strongest['treatment']))} "
            f"({float(strongest['conversion_rate_difference_pp']):+.4f} pp). "
            "This is a comparison of point estimates; the report does not include a "
            "direct statistical test between the two treatment arms."
        )
    else:
        strongest_text = (
            "No treatment-versus-control comparison was available."
        )

    srm_p = experiment["design"][
        "sample_ratio_mismatch_chi_square_p"
    ]

    # ------------------------------------------------------------------
    # 6. Metric cards, caveats and narrative.
    # ------------------------------------------------------------------
    metrics = [
        (
            "Valid e-commerce events",
            f"{events['total']:,}",
        ),
        (
            "Sessions with known IDs",
            f"{session['total_with_known_session_id']:,}",
        ),
        (
            "Session purchase rate",
            _fraction(session["purchase_session_conversion_rate"]),
        ),
        (
            "Gross purchase-item value",
            f"{events['gross_item_value']:,.2f} source units",
        ),
        (
            "Experiment customers",
            f"{experiment['design']['customers']:,}",
        ),
        (
            "Randomization SRM p-value",
            _p_value(srm_p),
        ),
    ]

    cards = "\n".join(
        f'<section class="metric">'
        f'<div class="metric-value">{html.escape(value)}</div>'
        f'<div class="metric-label">{html.escape(name)}</div>'
        f'</section>'
        for name, value in metrics
    )

    disclaimer = (
        "REES46 event prices represent gross purchase-item value in source units, not "
        "verified net revenue, order-level average order value (AOV), gross margin or "
        "marketplace commission. Purchase events may represent order line items. "
        "Unknown session IDs are excluded from session KPIs but remain in overall "
        "purchase-item value. Session-stage counts show independent reach; the rates "
        "below use ordered first-stage timestamps. These are observational metrics, "
        "not causal effects."
    )

    analysis = (
        "The Hillstrom randomization supports intention-to-treat contrasts between "
        "each email campaign and the no-email control under the original experiment "
        "design. The primary endpoint is conversion within two weeks. Two-sided "
        "p-values for the two primary comparisons are adjusted using the Holm method. "
        "The displayed 95% Newcombe intervals are unadjusted; bootstrap intervals for "
        "incremental spend per assigned customer are exploratory. Campaign delivery "
        "costs and product margins are unavailable, so profit and ROI cannot be inferred."
    )

    first_at = html.escape(
        str(events.get("first_at_utc", "n/a"))
    )

    last_at = html.escape(
        str(events.get("last_at_utc", "n/a"))
    )

    monthly_note = (
        "The first observed month is partial (*). Monthly values also depend on event "
        "volume and item prices, not only on customer behaviour."
        if first_month_is_partial
        else (
            "Monthly values depend on event volume and item prices, "
            "not only on customer behaviour."
        )
    )

    banner = (
        '<div class="warning"><strong>SYNTHETIC DEMONSTRATION:</strong> '
        "All metrics and conclusions below come from generated sample data, "
        "NOT observed retailer or Hillstrom outcomes. "
        "Do not cite these numbers as empirical results.</div>"
        if demo
        else (
            '<div class="real"><strong>USER-SUPPLIED CSV RUN:</strong> '
            "The program validates schemas but cannot independently verify "
            "file origin. Confirm provenance before publishing results.</div>"
        )
    )

    # ------------------------------------------------------------------
    # 7. Assemble the self-contained HTML document.
    # ------------------------------------------------------------------
    html_content = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>E-commerce Experimentation &amp; Customer Analytics</title>
<style>
:root{{--ink:#172439;--muted:#596779;--card:#ffffff;--bg:#f5f7fb;--accent:#1e547a;}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 system-ui,-apple-system,Segoe UI,Arial,sans-serif}}
header{{background:#122c42;color:white;padding:46px 7% 35px}}
header h1{{margin:0;max-width:1100px;font-size:clamp(26px,4vw,42px)}}
header p{{max-width:900px;color:#d5e2ec}}
main{{max-width:1130px;margin:auto;padding:26px}}
h2{{font-size:23px;margin:38px 0 12px}}
h3{{font-size:17px;margin:25px 0 8px}}
p{{max-width:1000px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(225px,1fr));gap:12px}}
.metric,.section{{background:var(--card);border:1px solid #e0e6ef;border-radius:10px;padding:18px}}
.metric-value{{font-size:26px;font-weight:750;color:#204d70}}
.metric-label{{color:var(--muted);font-size:13px}}
.warning{{background:#fff1da;border-left:5px solid #a97319;padding:16px 18px;margin:20px 0}}
.real{{background:#e9f2fa;border-left:5px solid var(--accent);padding:16px 18px;margin:20px 0}}
img{{width:100%;max-width:890px;height:auto;display:block;margin:12px auto}}
.table{{width:100%;border-collapse:collapse;font-size:13px;white-space:normal}}
.table th,.table td{{border-bottom:1px solid #e3e6ec;text-align:left;padding:7px 9px;vertical-align:top}}
.table th{{background:#eaf0f5}}
.scroll{{overflow-x:auto}}
.note{{color:var(--muted);font-size:13px}}
.summary-list{{padding-left:22px}}
.summary-list li{{margin:8px 0}}
footer{{padding:30px 0;color:var(--muted);border-top:1px solid #ddd;margin-top:40px}}
</style>
</head>
<body>
<header>
<h1>E-commerce Experimentation &amp; Customer Analytics</h1>
<p>Two independent studies: observed marketplace behaviour and a randomized email campaign experiment. Reproducible Python/SQL analysis, data-quality checks and business-focused inference.</p>
</header>
<main>
{banner}
<section class="grid">{cards}</section>

<h2>Executive summary</h2>
<section class="section">
<p><strong>Randomized Hillstrom experiment:</strong> the following estimates compare each campaign arm with the no-email control. They are intention-to-treat contrasts.</p>
<ul class="summary-list">{''.join(executive_lines)}</ul>
<p>{strongest_text}</p>
<p><strong>Randomization check:</strong> the sample-ratio-mismatch chi-square test returned p = {html.escape(_p_value(srm_p))}. This provides no evidence of an allocation-ratio mismatch; it does not prove that every aspect of the experiment was flawless.</p>
<p><strong>Commercial limitation:</strong> incremental spend is not profit or ROI. Campaign costs and product margins are not available.</p>
</section>

<h2>01 / Customer behaviour and purchase funnel</h2>
<section class="section">
<p>{html.escape(disclaimer)}</p>
<p class="note">Observed event window (UTC): {first_at} to {last_at}.</p>
<img alt="Session stage reach" src="{funnel_plot}">
<h3>Funnel rates and denominators</h3>
<div class="scroll">{_html_table(funnel_rates, digits=2)}</div>
<p class="note">The reach chart is non-exclusive: sessions can contain multiple event stages. The rate table separately defines the numerator and denominator for each ordered measure.</p>
<h3>Monthly purchase activity</h3>
<img alt="Monthly gross purchase-item values" src="{sales_plot}">
<p class="note">{html.escape(monthly_note)}</p>
<h3>Purchase categories by gross item value</h3>
<div class="scroll">{_html_table(category_display, digits=2)}</div>
<p class="note">The category value is gross purchase-item value in source units; it is not net revenue, margin or platform commission.</p>
<h3>REES46 data-quality audit</h3>
<div class="scroll">{_html_table(qa, digits=2)}</div>
<p class="note">Shares use all source rows as the denominator. Quality counters may overlap and should not be summed. Potential exact duplicates are audit candidates, not automatic deletion instructions.</p>
<p class="note">Detailed source tables: funnel/monthly_sales.csv, funnel/category_sales.csv, funnel/events.sqlite.</p>
</section>

<h2>02 / Randomized experiment (Hillstrom)</h2>
<section class="section">
<p>{html.escape(analysis)}</p>
<img alt="Experiment conversion rates by assigned arm" src="{ab_plot}">
<h3>Conversion lift and uncertainty</h3>
<img alt="Unadjusted Newcombe risk-difference intervals" src="{effects_plot}">
<h3>Arm-level outcomes</h3>
<div class="scroll">{_html_table(arms_display, digits=4)}</div>
<h3>Primary conversion comparisons and incremental spend</h3>
<div class="scroll">{_html_table(comparison_display, digits=4)}</div>
<h3>Baseline balance diagnostics</h3>
<div class="scroll">{_html_table(balancing_display, digits=3)}</div>
<p class="note">Conversion difference intervals are unadjusted 95% Newcombe intervals. Spend intervals are nonparametric bootstrap intervals and are exploratory. Detailed metrics: experiment/experiment_metrics.json.</p>
</section>

<h2>03 / Interpretation and guardrails</h2>
<section class="section">
<p><strong>Business decision rule:</strong> before rolling out a campaign, assess adjusted significance, effect size, uncertainty, incremental spend and the unknown delivery and merchandise costs. A positive point estimate alone is not sufficient evidence of commercial gain.</p>
<p><strong>Comparison scope:</strong> each treatment is compared with the no-email control. The report does not perform a direct statistical comparison between Mens E-Mail and Womens E-Mail.</p>
<p><strong>Separation of datasets:</strong> REES46 customer identities and Hillstrom customer identities are unrelated and are never joined. Observational event analytics cannot establish the causal effect of emails. Experimental estimates cannot be transferred automatically to another marketplace or era.</p>
<p><strong>Historical context:</strong> Hillstrom is a 2008 experiment. The REES46 event window is shown above. Neither dataset represents current customers of any other business.</p>
</section>

<footer>Portfolio study · Python, SQL/SQLite, pandas, SciPy, statsmodels, Matplotlib · Reproducible outputs</footer>
</main>
</body>
</html>"""

    target = output / "index.html"
    target.write_text(
        html_content,
        encoding="utf-8",
    )

    return target
