"""Event-ingestion edge cases: sessions, order lines and missing data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ecommerce_analytics.demo import create_demo_data
from ecommerce_analytics.funnel import InvalidEventData, analyze_funnel


def test_demo_funnel_metrics(tmp_path: Path) -> None:
    """Aggregate session facts from observed events without double counting stages."""
    events, _ = create_demo_data(tmp_path / "raw")
    result = analyze_funnel(events, tmp_path / "result", chunk_size=100)
    assert result["sessions"]["total_with_known_session_id"] == 1500
    assert result["sessions"]["with_view"] == 1500
    assert result["sessions"]["with_purchase"] <= result["sessions"]["with_cart"]
    assert result["events"]["purchase_line_events"] >= result["sessions"]["with_purchase"]
    assert (tmp_path / "result" / "events.sqlite").exists()


def test_missing_session_keeps_item_revenue(tmp_path: Path) -> None:
    """A purchase with missing session belongs to revenue but not session conversion."""
    frame = pd.DataFrame([
        ["2020-01-01T00:00:00Z", "view", 1, 1, "audio", "x", 10, "u1", "s1"],
        ["2020-01-01T00:00:02Z", "purchase", 1, 1, "audio", "x", 10, "u1", None],
    ], columns=["event_time", "event_type", "product_id", "category_id",
                "category_code", "brand", "price", "user_id", "user_session"])
    source = tmp_path / "events.csv"
    frame.to_csv(source, index=False)
    result = analyze_funnel(source, tmp_path / "metrics")
    assert result["events"]["gross_item_value"] == 10
    assert result["sessions"]["with_purchase"] == 0
    assert result["quality"]["purchase_without_session"] == 1


def test_missing_event_column_fails(tmp_path: Path) -> None:
    """Schema errors must stop the run instead of producing misleading zeros."""
    source = tmp_path / "events.csv"
    source.write_text("event_time,event_type,user_id\n2020-01-01,view,1\n", encoding="utf-8")
    with pytest.raises(InvalidEventData, match="Missing REES46 columns"):
        analyze_funnel(source, tmp_path / "result")
    assert not (tmp_path / "result" / "events.sqlite").exists()


def test_invalid_purchase_price_rejected(tmp_path: Path) -> None:
    """Invalid or negative prices must not corrupt purchase-value metrics."""
    data = {
        "event_time": ["2020-01-01T00:00:00Z", "2020-01-02T00:00:00Z"],
        "event_type": ["purchase", "purchase"],
        "product_id": [1, 2], "category_id": [1, 1],
        "category_code": ["a", "b"], "brand": ["a", "b"],
        "price": [10, -99], "user_id": ["1", "2"],
        "user_session": ["x", "y"],
    }
    source = tmp_path / "events.csv"
    pd.DataFrame(data).to_csv(source, index=False)
    result = analyze_funnel(source, tmp_path / "result")
    assert result["quality"]["invalid_price"] == 1
    assert result["events"]["gross_item_value"] == 10


def test_do_not_replace_previous_results(tmp_path: Path) -> None:
    """Existing SQLite outputs are immutable by default for reproducibility."""
    events, _ = create_demo_data(tmp_path / "raw")
    output = tmp_path / "result"
    analyze_funnel(events, output)
    with pytest.raises(FileExistsError):
        analyze_funnel(events, output)
