from __future__ import annotations

from typing import Any


def normalize_class_feature_options(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        normalized_key = key.strip().lower()
        normalized[normalized_key] = value
    return normalized
