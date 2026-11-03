"""Intention-to-treat analysis of the original randomized Hillstrom experiment.

The experimental unit is a customer. The three arms remain separate. Primary
outcome is 2-week conversion, with two treatment-versus-control comparisons.
No post-treatment outcomes are used to determine treatment assignment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import chisquare
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import confint_proportions_2indep, proportions_ztest

from ecommerce_analytics.common import save_json

REQUIRED = {
    "recency", "history", "mens", "womens", "newbie", "zip_code", "channel",
    "segment", "visit", "conversion", "spend",
}
ARM_VALUES = {"mens e-mail": "Mens E-Mail", "womens e-mail": "Womens E-Mail", "no e-mail": "No E-Mail"}
TREATMENTS = ("Mens E-Mail", "Womens E-Mail")
CONTROL = "No E-Mail"
BALANCE_FEATURES = ("recency", "history", "mens", "womens", "newbie")


class InvalidExperimentData(ValueError):
    """Raised for invalid randomized experiment data contracts."""


def _bootstrap_mean_difference(
    treated: np.ndarray, control: np.ndarray, repetitions: int, seed: int
) -> tuple[float, float]:
    """Percentile bootstrap interval for difference of unconditional mean spend."""
    generator = np.random.default_rng(seed)
    differences = np.empty(repetitions, dtype=float)
    for index in range(repetitions):
        first = generator.choice(treated, size=len(treated), replace=True)
        second = generator.choice(control, size=len(control), replace=True)
        differences[index] = first.mean() - second.mean()
    lower, upper = np.quantile(differences, (0.025, 0.975))
    return float(lower), float(upper)


def _standardized_mean_difference(first: np.ndarray, second: np.ndarray) -> float | None:
    """Scale baseline mean differences by pooled within-arm standard deviation."""
    pooled_var = (np.var(first, ddof=1) + np.var(second, ddof=1)) / 2
    if pooled_var <= 0:
        return 0.0 if np.mean(first) == np.mean(second) else None
    return float((np.mean(first) - np.mean(second)) / np.sqrt(pooled_var))


def load_experiment(source: Path) -> pd.DataFrame:
    """Load Hillstrom CSV and enforce a consistent three-arm trial schema."""
    if not source.is_file():
        raise FileNotFoundError(f"Hillstrom file not found: {source}")
    frame = pd.read_csv(source, dtype={"segment": "string", "zip_code": "string", "channel": "string"})
    frame.columns = [column.strip().lower() for column in frame.columns]
    absent = sorted(REQUIRED - set(frame.columns))
    if absent:
        raise InvalidExperimentData(f"Missing Hillstrom columns: {', '.join(absent)}")
    if frame.empty:
        raise InvalidExperimentData("Hillstrom file contains no observations")
    normalized = frame["segment"].str.strip().str.lower().map(ARM_VALUES)
    if normalized.isna().any():
        raise InvalidExperimentData("Unexpected or missing campaign segment")
    frame["segment"] = normalized
    if set(frame["segment"]) != set(ARM_VALUES.values()):
        raise InvalidExperimentData("The dataset must include the two treatment arms and control")
    for name in ["conversion", "visit", "mens", "womens", "newbie", "recency", "history", "spend"]:
        frame[name] = pd.to_numeric(frame[name], errors="coerce")
        if not np.isfinite(frame[name].to_numpy(dtype=float)).all():
            raise InvalidExperimentData(f"Invalid or missing numeric values in {name}")
    for name in ["conversion", "visit", "mens", "womens", "newbie"]:
        if not frame[name].isin((0, 1)).all():
            raise InvalidExperimentData(f"Expected a binary 0/1 variable: {name}")
    if (frame[["recency", "history", "spend"]] < 0).any().any():
        raise InvalidExperimentData("Negative recency, pre-period history or outcome spend")
    if frame[["zip_code", "channel"]].isna().any().any():
        raise InvalidExperimentData("Missing baseline categories: zip_code or channel")
    if (frame.loc[frame["conversion"] == 0, "spend"] > 0).any():
        raise InvalidExperimentData("Positive post-treatment spend for conversion=0")
    return frame


def analyze_experiment(
    source: Path, output: Path, *, bootstrap_iterations: int = 1_000, seed: int = 20261027,
    synthetic: bool = False,
) -> dict[str, Any]:
    """Estimate randomized ITT uplift with two-comparison Holm adjustments."""
    if bootstrap_iterations < 100:
        raise ValueError("bootstrap_iterations must be at least 100")
    frame = load_experiment(source)
    output.mkdir(parents=True, exist_ok=True)
    counts = frame["segment"].value_counts()
    observed_counts = np.array([counts[CONTROL], *(counts[t] for t in TREATMENTS)])
    ratio_test = chisquare(observed_counts, f_exp=[len(frame) / 3] * 3)
    summaries: list[dict[str, Any]] = []
    for arm in (CONTROL, *TREATMENTS):
        subset = frame.loc[frame["segment"] == arm]
        summaries.append({
            "arm": arm,
            "customers": int(len(subset)),
            "visits": int(subset["visit"].sum()),
            "conversions": int(subset["conversion"].sum()),
            "visit_rate": float(subset["visit"].mean()),
            "conversion_rate": float(subset["conversion"].mean()),
            "mean_spend_per_randomized_customer_usd": float(subset["spend"].mean()),
            "total_spend_usd": float(subset["spend"].sum()),
        })
    control = frame.loc[frame["segment"] == CONTROL]
    comparisons: list[dict[str, Any]] = []
    raw_p_values: list[float] = []
    balance: list[dict[str, Any]] = []
    for index, treatment in enumerate(TREATMENTS):
        treated = frame.loc[frame["segment"] == treatment]
        event_counts = [int(treated["conversion"].sum()), int(control["conversion"].sum())]
        nobs = [len(treated), len(control)]
        # With zero total conversions (or universal conversion), the score variance is zero.
        if sum(event_counts) in (0, sum(nobs)):
            p_value = 1.0
        else:
            _, p_value = proportions_ztest(event_counts, nobs, alternative="two-sided")
        ci_low, ci_high = confint_proportions_2indep(
            event_counts[0], nobs[0], event_counts[1], nobs[1],
            compare="diff", method="newcomb", alpha=0.05,
        )
        treated_spend = treated["spend"].to_numpy(dtype=float)
        control_spend = control["spend"].to_numpy(dtype=float)
        spend_ci = _bootstrap_mean_difference(treated_spend, control_spend, bootstrap_iterations, seed + index)
        record = {
            "treatment": treatment,
            "control": CONTROL,
            "conversion_rate_difference_pp": 100 * (
                event_counts[0] / nobs[0] - event_counts[1] / nobs[1]
            ),
            "conversion_diff_ci_95_pp": [100 * float(ci_low), 100 * float(ci_high)],
            "conversion_p_value_raw": float(p_value),
            "incremental_spend_per_assigned_customer_usd": float(
                treated_spend.mean() - control_spend.mean()
            ),
            "incremental_spend_ci_95_usd": list(spend_ci),
            "estimated_incremental_revenue_for_treated_arm_usd": float(
                (treated_spend.mean() - control_spend.mean()) * len(treated)
            ),
        }
        comparisons.append(record)
        raw_p_values.append(float(p_value))
        for feature in BALANCE_FEATURES:
            smd = _standardized_mean_difference(
                treated[feature].to_numpy(dtype=float), control[feature].to_numpy(dtype=float)
            )
            balance.append({
                "treatment": treatment,
                "baseline_variable": feature,
                "standardized_mean_difference": smd,
                "above_abs_0_1_review_threshold": smd is not None and abs(smd) > 0.10,
            })
    rejected, adjusted, _, _ = multipletests(raw_p_values, alpha=0.05, method="holm")
    for record, adjusted_p, reject in zip(comparisons, adjusted, rejected, strict=True):
        record["conversion_p_value_holm"] = float(adjusted_p)
        record["conversion_significant_holm_0_05"] = bool(reject)
    pd.DataFrame(summaries).to_csv(output / "experiment_arms.csv", index=False)
    pd.DataFrame(comparisons).to_csv(output / "experiment_comparisons.csv", index=False)
    pd.DataFrame(balance).to_csv(output / "experiment_balance.csv", index=False)
    result = {
        "dataset": "Hillstrom MineThatData 2008 email experiment",
        "source_kind": "synthetic_demo" if synthetic else "user_supplied_unverified",
        "design": {
            "type": "randomized_3_arm_customer_level_itt",
            "primary_outcome": "conversion within two weeks",
            "primary_comparisons": [f"{t} vs {CONTROL}" for t in TREATMENTS],
            "multiple_testing": "Holm adjustment across two primary conversion hypotheses",
            "sample_ratio_mismatch_chi_square_p": float(ratio_test.pvalue),
            "sample_ratio_expected": "1:1:1",
            "customers": len(frame),
            "bootstrap_iterations": bootstrap_iterations,
            "seed": seed,
        },
        "arms": summaries,
        "comparisons": comparisons,
        "balance_review": balance,
        "notes": [
            "Spend outcome is unconditional revenue per randomized customer, including zeros.",
            "Bootstrap spend intervals are descriptive exploratory intervals, not adjusted for multiplicity.",
            "Conversion CIs are unadjusted 95% Newcombe intervals; inference uses Holm-adjusted p values.",
            "Historical covariate balance is diagnostic, not an assumption of observed confounding.",
            "Campaign costs, profit and product margins are not available; revenue is not profit.",
            "No customer identifier is exposed; dataset is treated as one row per randomized customer.",
        ],
    }
    save_json(output / "experiment_metrics.json", result)
    return result
