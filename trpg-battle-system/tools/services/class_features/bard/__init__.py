from __future__ import annotations

from importlib import import_module

__all__ = [
    "UseBardicInspiration",
    "UseFontOfInspiration",
]

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "UseBardicInspiration": (
        "tools.services.class_features.bard.use_bardic_inspiration",
        "UseBardicInspiration",
    ),
    "UseFontOfInspiration": (
        "tools.services.class_features.bard.use_font_of_inspiration",
        "UseFontOfInspiration",
    ),
}


def __getattr__(name: str):
    export = _LAZY_EXPORTS.get(name)
    if export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_path, attr_name = export
    value = getattr(import_module(module_path), attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__))
