"""Statistical and data-contract checks for the randomized Hillstrom module."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ecommerce_analytics.demo import create_demo_data
from ecommerce_analytics.experiment import (
    InvalidExperimentData,
    _bootstrap_mean_difference,
    analyze_experiment,
    load_experiment,
)


def test_three_arms_with_holm_adjustment(tmp_path: Path) -> None:
    """Use an offline seeded experiment to verify estimates and persistence."""
    _, experiment = create_demo_data(tmp_path / "raw")
    result = analyze_experiment(experiment, tmp_path / "experiment", bootstrap_iterations=100)
    assert result["design"]["customers"] == 12000
    assert len(result["arms"]) == 3
    assert len(result["comparisons"]) == 2
    assert all(0 <= arm["conversion_rate"] <= 1 for arm in result["arms"])
    assert all(
        compare["conversion_p_value_holm"] >= compare["conversion_p_value_raw"]
        for compare in result["comparisons"]
    )
    assert (tmp_path / "experiment" / "experiment_metrics.json").exists()


def test_reject_nonbinary_outcome(tmp_path: Path) -> None:
    """Malformed outcome values must not be silently counted as negatives."""
    _, experiment = create_demo_data(tmp_path / "raw")
    frame = pd.read_csv(experiment)
    frame.loc[0, "conversion"] = 2
    frame.to_csv(experiment, index=False)
    with pytest.raises(InvalidExperimentData, match="binary"):
        load_experiment(experiment)


def test_reject_missing_arm(tmp_path: Path) -> None:
    """Do not compare groups if experimental control has been removed."""
    _, experiment = create_demo_data(tmp_path / "raw")
    frame = pd.read_csv(experiment)
    frame = frame[frame["segment"] != "No E-Mail"]
    frame.to_csv(experiment, index=False)
    with pytest.raises(InvalidExperimentData, match="two treatment arms"):
        load_experiment(experiment)


def test_bootstrap_deterministic_for_seed() -> None:
    """A fixed seed must reproduce numeric spend intervals exactly."""
    t = np.array([0.0, 0.0, 100.0, 0.0])
    c = np.array([0.0, 0.0, 20.0, 0.0])
    first = _bootstrap_mean_difference(t, c, 100, 4)
    assert first == _bootstrap_mean_difference(t, c, 100, 4)
    assert first[0] <= first[1]


def test_all_zero_conversion_has_valid_p_value(tmp_path: Path) -> None:
    """All-zero outcomes provide no evidence and must not produce NaN p-values."""
    _, experiment = create_demo_data(tmp_path / "raw")
    frame = pd.read_csv(experiment)
    frame["conversion"] = 0
    frame["spend"] = 0
    frame.to_csv(experiment, index=False)
    result = analyze_experiment(experiment, tmp_path / "experiment", bootstrap_iterations=100)
    assert all(item["conversion_p_value_holm"] == 1.0 for item in result["comparisons"])
