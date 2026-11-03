"""Generate clearly labelled synthetic CSVs for offline smoke tests and demonstrations."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd


def create_demo_data(output: Path, *, seed: int = 20261027) -> tuple[Path, Path]:
    """Create deterministic miniature analogues of REES46 and Hillstrom schemas.

    These records are fabricated; they are never a replacement for real-data results.
    """
    output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    events = []
    start = pd.Timestamp("2020-01-01", tz="UTC")
    for session_id in range(1_500):
        user_id = 1 + (session_id % 800)
        offset_minutes = int(rng.integers(0, 45)) * 1440 + int(rng.integers(0, 1440))
        begin = start + timedelta(minutes=offset_minutes)
        product_id = int(rng.integers(1, 150))
        brand = "generic-a" if product_id % 2 else "generic-b"
        category = "electronics.audio" if product_id % 3 else "electronics.smartphone"
        price = float(rng.integers(15, 500))
        stages = ["view"]
        if rng.random() < 0.48:
            stages.append("cart")
            if rng.random() < 0.35:
                stages.append("purchase")
        for step, event_type in enumerate(stages):
            events.append({
                "event_time": (begin + timedelta(minutes=step * 2)).isoformat(),
                "event_type": event_type, "product_id": product_id,
                "category_id": "1234567890123456789", "category_code": category,
                "brand": brand, "price": price, "user_id": str(user_id),
                "user_session": f"demo-session-{session_id}",
            })
    electronics = output / "electronics-events.csv"
    pd.DataFrame(events).to_csv(electronics, index=False)

    size = 12_000
    assignments = np.tile(["No E-Mail", "Mens E-Mail", "Womens E-Mail"], size // 3)
    rng.shuffle(assignments)
    previous_spend = rng.gamma(1.5, 120, size)
    conversion_probs = np.where(assignments == "No E-Mail", 0.018,
                                np.where(assignments == "Mens E-Mail", 0.025, 0.022))
    conversions = rng.binomial(1, conversion_probs)
    visits = np.maximum(conversions, rng.binomial(1, 0.15, size))
    spend = conversions * rng.gamma(3, 50, size)
    hillstrom = output / "hillstrom.csv"
    pd.DataFrame({
        "recency": rng.integers(1, 13, size=size),
        "history_segment": np.where(previous_spend >= 200, "high", "low"),
        "history": np.round(previous_spend, 2),
        "mens": rng.binomial(1, 0.5, size=size),
        "womens": rng.binomial(1, 0.5, size=size),
        "zip_code": rng.choice(["Urban", "Surburban", "Rural"], size=size),
        "newbie": rng.binomial(1, 0.25, size=size),
        "channel": rng.choice(["Web", "Phone", "Multichannel"], size=size),
        "segment": assignments,
        "visit": visits,
        "conversion": conversions,
        "spend": np.round(spend, 2),
    }).to_csv(hillstrom, index=False)
    (output / "DEMO_DATA_WARNING.txt").write_text(
        "SYNTHETIC DATA - NOT REES46 OR HILLSTROM OBSERVATIONS.\n"
        "All dashboard metrics generated from these CSVs are demonstration-only.\n",
        encoding="utf-8",
    )
    return electronics, hillstrom
