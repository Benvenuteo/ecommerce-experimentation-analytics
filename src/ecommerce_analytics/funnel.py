"""Validate and analyze REES46 event logs using SQLite for bounded-memory ingestion.

All rates use explicitly documented denominators. Missing session IDs are not
invented. Purchase events may represent order line items rather than orders.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from ecommerce_analytics.common import save_json

COLUMNS = (
    "event_time", "event_type", "product_id", "category_id", "category_code",
    "brand", "price", "user_id", "user_session",
)
VALID_EVENTS = {"view", "cart", "remove_from_cart", "purchase"}


class InvalidEventData(ValueError):
    """Raised when a required REES46 column is absent."""


def _clean_text(values: pd.Series) -> pd.Series:
    """Normalize missing tokens while retaining identifiers as strings."""
    clean = values.astype("string").str.strip()
    return clean.mask(clean.eq("") | clean.str.lower().isin(["nan", "none", "null"]))


def _load_events(source: Path, database: sqlite3.Connection, chunk_size: int) -> dict[str, int]:
    """Stream source events, recording invalid rows without silently correcting them."""
    counters = {
        "source_rows": 0,
        "accepted_rows": 0,
        "invalid_time": 0,
        "invalid_type": 0,
        "invalid_price": 0,
        "missing_user_id": 0,
        "missing_session_id": 0,
        "missing_category_code": 0,
        "missing_brand": 0,
        "purchase_without_session": 0,
    }
    database.execute(
        """CREATE TABLE events (
          event_time TEXT NOT NULL, event_type TEXT NOT NULL, product_id TEXT,
          category_id TEXT, category_code TEXT, brand TEXT, price REAL,
          user_id TEXT NOT NULL, user_session TEXT
        )"""
    )
    # Keep identifiers as strings to avoid float conversion or loss of precision.
    reader = pd.read_csv(source, chunksize=chunk_size, dtype="string", on_bad_lines="error")
    saw_chunk = False
    for chunk in reader:
        saw_chunk = True
        absent = sorted(set(COLUMNS) - set(chunk.columns))
        if absent:
            raise InvalidEventData(f"Missing REES46 columns: {', '.join(absent)}")
        df = chunk.loc[:, list(COLUMNS)].copy()
        for key in ["event_type", "product_id", "category_id", "category_code", "brand", "user_id", "user_session"]:
            df[key] = _clean_text(df[key])
        df["event_type"] = df["event_type"].str.lower()
        timestamps = pd.to_datetime(df["event_time"], errors="coerce", utc=True)
        prices = pd.to_numeric(df["price"], errors="coerce")
        # A price of zero is allowed; missing price is tolerable for non-purchases.
        bad_time = timestamps.isna()
        bad_event = ~df["event_type"].isin(VALID_EVENTS)
        bad_price = (prices.notna() & (prices < 0)) | ((df["event_type"] == "purchase") & prices.isna())
        bad_user = df["user_id"].isna()
        valid = ~(bad_time | bad_event | bad_price | bad_user)
        counters["source_rows"] += len(df)
        counters["invalid_time"] += int(bad_time.sum())
        counters["invalid_type"] += int(bad_event.sum())
        counters["invalid_price"] += int(bad_price.sum())
        counters["missing_user_id"] += int(bad_user.sum())
        counters["missing_session_id"] += int(df["user_session"].isna().sum())
        counters["missing_category_code"] += int(df["category_code"].isna().sum())
        counters["missing_brand"] += int(df["brand"].isna().sum())
        counters["purchase_without_session"] += int(((df["event_type"] == "purchase") & df["user_session"].isna()).sum())
        accepted = df.loc[valid].copy()
        accepted["event_time"] = timestamps.loc[valid].dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        accepted["price"] = prices.loc[valid]
        accepted = accepted.astype(object).where(pd.notna(accepted), None)
        database.executemany(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)",
            accepted.itertuples(index=False, name=None),
        )
        counters["accepted_rows"] += len(accepted)
        database.commit()
    if not saw_chunk:
        with source.open("r", newline="", encoding="utf-8-sig") as handle:
            header = next(csv.reader(handle), [])
        absent = sorted(set(COLUMNS) - set(header))
        if absent:
            raise InvalidEventData(f"Missing REES46 columns: {', '.join(absent)}")
    database.execute("CREATE INDEX idx_events_user_session ON events(user_id,user_session)")
    database.execute("CREATE INDEX idx_events_type ON events(event_type)")
    database.execute("CREATE INDEX idx_events_time ON events(event_time)")
    return counters


def analyze_funnel(
    source: Path, output: Path, *, chunk_size: int = 50_000, synthetic: bool = False
) -> dict[str, Any]:
    """Compute reproducible event, session and revenue metrics from a CSV/CSV.gz."""
    if not source.is_file():
        raise FileNotFoundError(f"E-commerce file not found: {source}")
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    output.mkdir(parents=True, exist_ok=True)
    database_path = output / "events.sqlite"
    if database_path.exists():
        raise FileExistsError(f"Refusing to replace existing database: {database_path}")
    try:
        with sqlite3.connect(database_path) as db:
            counters = _load_events(source, db, chunk_size)
            db.execute(
                """CREATE VIEW sessions AS
                SELECT user_id, user_session,
                       MIN(event_time) AS first_event_at,
                       MIN(CASE WHEN event_type='view' THEN event_time END) AS first_view_at,
                       MIN(CASE WHEN event_type='cart' THEN event_time END) AS first_cart_at,
                       MIN(CASE WHEN event_type='purchase' THEN event_time END) AS first_purchase_at,
                       SUM(CASE WHEN event_type='purchase' THEN price ELSE 0 END) AS revenue,
                       SUM(CASE WHEN event_type='purchase' THEN 1 ELSE 0 END) AS purchased_items
                FROM events WHERE user_session IS NOT NULL
                GROUP BY user_id, user_session"""
            )
            # Missing-session purchase items remain in all-events revenue, but not session KPIs.
            if counters["accepted_rows"] == 0:
                raise InvalidEventData("No valid events after data contract validation")
            stats = db.execute(
                """SELECT COUNT(*), COUNT(DISTINCT user_id),
                  SUM(CASE WHEN event_type='purchase' THEN 1 ELSE 0 END),
                  COALESCE(SUM(CASE WHEN event_type='purchase' THEN price ELSE 0 END),0),
                  MIN(event_time), MAX(event_time) FROM events"""
            ).fetchone()
            session_row = db.execute(
                """SELECT COUNT(*),
                  SUM(CASE WHEN first_view_at IS NOT NULL THEN 1 ELSE 0 END),
                  SUM(CASE WHEN first_cart_at IS NOT NULL THEN 1 ELSE 0 END),
                  SUM(CASE WHEN first_purchase_at IS NOT NULL THEN 1 ELSE 0 END),
                  SUM(CASE WHEN first_view_at IS NOT NULL AND first_cart_at>=first_view_at THEN 1 ELSE 0 END),
                  SUM(CASE WHEN first_cart_at IS NOT NULL AND first_purchase_at>=first_cart_at THEN 1 ELSE 0 END),
                  SUM(CASE WHEN first_view_at IS NOT NULL AND first_cart_at>=first_view_at
                       AND first_purchase_at>=first_cart_at THEN 1 ELSE 0 END),
                  COALESCE(SUM(revenue),0),
                  SUM(CASE WHEN purchased_items>0 THEN purchased_items ELSE 0 END)
                  FROM sessions"""
            ).fetchone()
            sessions, viewed, carted, converted, view_cart, cart_purchase, full_funnel, session_revenue, items = [v or 0 for v in session_row]
            # Revenue by category is purchase item value. It is not platform margin.
            category = pd.read_sql_query(
                """SELECT COALESCE(category_code,'[unknown]') AS category,
                     COUNT(*) AS purchased_items, ROUND(SUM(price),2) AS revenue
                   FROM events WHERE event_type='purchase'
                   GROUP BY COALESCE(category_code,'[unknown]')
                   ORDER BY revenue DESC LIMIT 20""",
                db,
            )
            monthly = pd.read_sql_query(
                """SELECT substr(event_time,1,7) AS month,
                     COUNT(DISTINCT CASE WHEN event_type='purchase' THEN user_id END) AS buyers,
                     COUNT(CASE WHEN event_type='purchase' THEN 1 END) AS purchased_items,
                     ROUND(SUM(CASE WHEN event_type='purchase' THEN price ELSE 0 END),2) AS revenue
                   FROM events GROUP BY substr(event_time,1,7) ORDER BY month""",
                db,
            )
            # Composite key guards against same session token appearing under different customers.
            repeat = db.execute(
                """SELECT COUNT(*) FROM
                   (SELECT user_id FROM sessions GROUP BY user_id
                    HAVING SUM(CASE WHEN first_purchase_at IS NOT NULL THEN 1 ELSE 0 END)>=2)"""
            ).fetchone()[0]
            # QA audit: a purchase may be a line item; repeated session purchases are not distinct orders.
            qa_without_cart = db.execute(
                """SELECT COUNT(*) FROM sessions WHERE first_purchase_at IS NOT NULL
                    AND (first_cart_at IS NULL OR first_cart_at>first_purchase_at)"""
            ).fetchone()[0]
            duplicate_candidates = db.execute(
                """SELECT COALESCE(SUM(repetitions-1),0) FROM (
                    SELECT COUNT(*) AS repetitions FROM events
                    GROUP BY event_time, event_type, product_id, category_id,
                             category_code, brand, price, user_id, user_session
                    HAVING COUNT(*)>1)"""
            ).fetchone()[0]
            # A source may legitimately emit indistinguishable line events: audit, do not drop.
            counters["potential_exact_duplicate_rows"] = int(duplicate_candidates)
            category.to_csv(output / "category_sales.csv", index=False)
            monthly.to_csv(output / "monthly_sales.csv", index=False)
            def denominator(n: float, d: float) -> float | None:
                return float(n / d) if d else None
            result = {
                "dataset": "REES46 electronics events",
                "source_kind": "synthetic_demo" if synthetic else "user_supplied_unverified",
                "quality": counters,
                "events": {
                    "total": int(stats[0]), "unique_users": int(stats[1]),
                    "purchase_line_events": int(stats[2]),
                    "gross_item_value": round(float(stats[3]), 2),
                    "first_at_utc": stats[4], "last_at_utc": stats[5],
                },
                "sessions": {
                    "total_with_known_session_id": int(sessions),
                    "with_view": int(viewed), "with_cart": int(carted),
                    "with_purchase": int(converted),
                    "view_then_cart": int(view_cart),
                    "cart_then_purchase": int(cart_purchase),
                    "view_then_cart_then_purchase": int(full_funnel),
                    "purchase_session_conversion_rate": denominator(converted, sessions),
                    "view_to_cart_reach_rate": denominator(view_cart, viewed),
                    "cart_to_purchase_reach_rate": denominator(cart_purchase, carted),
                    "ordered_full_funnel_rate": denominator(full_funnel, viewed),
                    "gross_value_in_attributed_sessions": round(float(session_revenue), 2),
                    "average_purchase_item_value": denominator(session_revenue, items),
                    "repeat_buyers_2plus_purchasing_sessions": int(repeat),
                    "purchases_without_prior_cart_session_count": int(qa_without_cart),
                },
            }
            save_json(output / "funnel_metrics.json", result)
            return result
    except Exception:
        database_path.unlink(missing_ok=True)
        raise
