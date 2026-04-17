from __future__ import annotations

from typing import Any


def resolve_fighting_style_ids(entity_or_class_features: Any) -> set[str]:
    class_features = _extract_class_features(entity_or_class_features)
    style_ids: set[str] = set()
    for bucket in class_features.values():
        if not isinstance(bucket, dict):
            continue
        fighting_style = bucket.get("fighting_style")
        if not isinstance(fighting_style, dict):
            continue
        style_id = str(fighting_style.get("style_id") or "").strip().lower()
        if style_id:
            style_ids.add(style_id)
    return style_ids


def has_fighting_style(entity_or_class_features: Any, style_id: str) -> bool:
    normalized = str(style_id or "").strip().lower()
    if not normalized:
        return False
    return normalized in resolve_fighting_style_ids(entity_or_class_features)


def _extract_class_features(entity_or_class_features: Any) -> dict[str, Any]:
    if isinstance(entity_or_class_features, dict):
        class_features = entity_or_class_features.get("class_features")
        if isinstance(class_features, dict):
            return class_features
        return entity_or_class_features if all(isinstance(value, dict) for value in entity_or_class_features.values()) else {}

    class_features = getattr(entity_or_class_features, "class_features", None)
    if isinstance(class_features, dict):
        return class_features
    return {}
