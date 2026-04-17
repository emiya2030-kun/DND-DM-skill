from __future__ import annotations

from importlib import import_module

__all__ = [
    "EncounterRepository",
    "ArmorDefinitionRepository",
    "EntityDefinitionRepository",
    "EventRepository",
    "ClassFeatureDefinitionRepository",
    "ClassProficiencyDefinitionRepository",
    "SpellDefinitionRepository",
    "WeaponDefinitionRepository",
    "ZoneDefinitionRepository",
    "ReactionDefinitionRepository",
]

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "EncounterRepository": ("tools.repositories.encounter_repository", "EncounterRepository"),
    "ArmorDefinitionRepository": ("tools.repositories.armor_definition_repository", "ArmorDefinitionRepository"),
    "EntityDefinitionRepository": ("tools.repositories.entity_definition_repository", "EntityDefinitionRepository"),
    "EventRepository": ("tools.repositories.event_repository", "EventRepository"),
    "ClassFeatureDefinitionRepository": (
        "tools.repositories.class_feature_definition_repository",
        "ClassFeatureDefinitionRepository",
    ),
    "ClassProficiencyDefinitionRepository": (
        "tools.repositories.class_proficiency_definition_repository",
        "ClassProficiencyDefinitionRepository",
    ),
    "SpellDefinitionRepository": ("tools.repositories.spell_definition_repository", "SpellDefinitionRepository"),
    "WeaponDefinitionRepository": ("tools.repositories.weapon_definition_repository", "WeaponDefinitionRepository"),
    "ZoneDefinitionRepository": ("tools.repositories.zone_definition_repository", "ZoneDefinitionRepository"),
    "ReactionDefinitionRepository": (
        "tools.repositories.reaction_definition_repository",
        "ReactionDefinitionRepository",
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
