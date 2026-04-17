from __future__ import annotations

from typing import Any


def get_class_runtime(entity_or_class_features: Any, class_id: str) -> dict[str, Any]:
    class_features = _read_class_features(entity_or_class_features)
    bucket = class_features.get(class_id)
    if isinstance(bucket, dict):
        return bucket
    return {}


def ensure_class_runtime(entity_or_class_features: Any, class_id: str) -> dict[str, Any]:
    class_features = _ensure_class_features(entity_or_class_features)
    bucket = class_features.get(class_id)
    if isinstance(bucket, dict):
        return bucket
    class_features[class_id] = {}
    return class_features[class_id]


def get_fighter_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    return get_class_runtime(entity_or_class_features, "fighter")


def ensure_fighter_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    return ensure_class_runtime(entity_or_class_features, "fighter")


def _read_class_features(entity_or_class_features: Any) -> dict[str, Any]:
    if isinstance(entity_or_class_features, dict):
        class_features = entity_or_class_features.get("class_features")
        if isinstance(class_features, dict):
            return class_features
        return {}

    class_features = getattr(entity_or_class_features, "class_features", None)
    if isinstance(class_features, dict):
        return class_features
    return {}


def _ensure_class_features(entity_or_class_features: Any) -> dict[str, Any]:
    if isinstance(entity_or_class_features, dict):
        class_features = entity_or_class_features.get("class_features")
        if isinstance(class_features, dict):
            return class_features
        entity_or_class_features["class_features"] = {}
        return entity_or_class_features["class_features"]

    class_features = getattr(entity_or_class_features, "class_features", None)
    if isinstance(class_features, dict):
        return class_features

    setattr(entity_or_class_features, "class_features", {})
    return entity_or_class_features.class_features
