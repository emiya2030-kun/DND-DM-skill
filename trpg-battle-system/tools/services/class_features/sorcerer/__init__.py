from __future__ import annotations

from importlib import import_module

__all__ = [
    "UseInnateSorcery",
    "ConvertSpellSlotToSorceryPoints",
    "CreateSpellSlotFromSorceryPoints",
    "UseSorcerousRestoration",
]

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "UseInnateSorcery": ("tools.services.class_features.sorcerer.use_innate_sorcery", "UseInnateSorcery"),
    "ConvertSpellSlotToSorceryPoints": (
        "tools.services.class_features.sorcerer.convert_spell_slot_to_sorcery_points",
        "ConvertSpellSlotToSorceryPoints",
    ),
    "CreateSpellSlotFromSorceryPoints": (
        "tools.services.class_features.sorcerer.create_spell_slot_from_sorcery_points",
        "CreateSpellSlotFromSorceryPoints",
    ),
    "UseSorcerousRestoration": (
        "tools.services.class_features.sorcerer.use_sorcerous_restoration",
        "UseSorcerousRestoration",
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
