"""Command-line orchestration for reproducible full-data and demo study runs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from ecommerce_analytics.common import save_json, sha256_file
from ecommerce_analytics.demo import create_demo_data
from ecommerce_analytics.experiment import analyze_experiment
from ecommerce_analytics.funnel import analyze_funnel
from ecommerce_analytics.report import write_report


def main() -> None:
    """Parse commands, prevent overwrites, and run each reproducible analysis stage."""
    parser = argparse.ArgumentParser(description="E-commerce analytics and randomized A/B/C analysis")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run both independent studies on actual downloaded CSVs")
    run.add_argument("--events", type=Path, required=True, help="REES46 .csv or .csv.gz")
    run.add_argument("--experiment", type=Path, required=True, help="Hillstrom .csv")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--bootstrap", type=int, default=1000)
    demo = commands.add_parser("demo", help="Run only on fabricated deterministic data")
    demo.add_argument("--output", type=Path, default=Path("outputs/demo"))
    demo.add_argument("--bootstrap", type=int, default=500)
    arguments = parser.parse_args()
    target: Path = arguments.output
    if target.exists() and any(target.iterdir()):
        parser.error(f"Output directory must not exist or must be empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    demo_mode = arguments.command == "demo"
    if demo_mode:
        events, experiment = create_demo_data(target / "synthetic_raw")
    else:
        events, experiment = arguments.events, arguments.experiment
    funnel = analyze_funnel(events, target / "funnel", synthetic=demo_mode)
    trial = analyze_experiment(
        experiment, target / "experiment", bootstrap_iterations=arguments.bootstrap,
        synthetic=demo_mode,
    )
    report = write_report(target, funnel, trial, demo=demo_mode)
    save_json(target / "run_manifest.json", {
        "execution_time_utc": datetime.now(timezone.utc).isoformat(),
        "data_mode": "synthetic_demo" if demo_mode else "user_supplied_observational_and_experiment",
        "events_file": str(events.resolve()),
        "events_sha256": sha256_file(events),
        "experiment_file": str(experiment.resolve()),
        "experiment_sha256": sha256_file(experiment),
        "output_report": str(report.resolve()),
        "notes": ["All reports, source metrics and analytics tables are local to this run."],
    })
    print(f"Completed {'synthetic demo' if demo_mode else 'real-data study'}: {report.resolve()}")


if __name__ == "__main__":
    main()
