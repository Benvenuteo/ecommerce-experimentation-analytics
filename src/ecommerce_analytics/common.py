"""Shared filesystem helpers and safe JSON conversion."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


def json_ready(value: Any) -> Any:
    """Recursively convert NumPy values and non-finite values to strict JSON."""
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, np.generic):
        return json_ready(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def save_json(destination: Path, payload: dict[str, Any]) -> None:
    """Write deterministic, UTF-8 and standards-compliant JSON output."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(json_ready(payload), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def sha256_file(source: Path, *, chunk_bytes: int = 1024 * 1024) -> str:
    """Fingerprint raw inputs in constant memory for reproducibility audits."""
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        while block := stream.read(chunk_bytes):
            digest.update(block)
    return digest.hexdigest()
