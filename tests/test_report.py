"""End-to-end test for an offline self-contained HTML report."""

from __future__ import annotations

from pathlib import Path

from ecommerce_analytics.demo import create_demo_data
from ecommerce_analytics.experiment import analyze_experiment
from ecommerce_analytics.funnel import analyze_funnel
from ecommerce_analytics.report import write_report


def test_report_has_embedded_charts_and_demo_warning(tmp_path: Path) -> None:
    """Static report must display figures and unmistakably label fabricated data."""
    events, experiment = create_demo_data(tmp_path / "raw")
    funnel = analyze_funnel(events, tmp_path / "report" / "funnel")
    trial = analyze_experiment(experiment, tmp_path / "report" / "experiment", bootstrap_iterations=100)
    report = write_report(tmp_path / "report", funnel, trial, demo=True)
    contents = report.read_text(encoding="utf-8")
    assert "SYNTHETIC DEMONSTRATION" in contents
    assert "data:image/png;base64," in contents
    assert "Holm" in contents
    assert "REES46" in contents
