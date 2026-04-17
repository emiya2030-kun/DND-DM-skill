from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.services.combat.rules.conditions import ConditionRuntime

_SIZE_ORDER = {
    "tiny": 0,
    "small": 1,
    "medium": 2,
    "large": 3,
    "huge": 4,
    "gargantuan": 5,
}


def resolve_grapple_save_dc(actor: EncounterEntity) -> dict[str, Any]:
    class_features = actor.class_features if isinstance(actor.class_features, dict) else {}
    monk = class_features.get("monk")
    martial_arts = monk.get("martial_arts") if isinstance(monk, dict) else None
    ability_used = "dex" if isinstance(martial_arts, dict) and martial_arts.get("grapple_dc_ability") == "dex" else "str"
    ability_mod = int(actor.ability_mods.get(ability_used, 0))
    proficiency_bonus = int(actor.proficiency_bonus or 0)
    return {
        "dc": 8 + ability_mod + proficiency_bonus,
        "ability_used": ability_used,
        "breakdown": {
            "base": 8,
            "ability_mod": ability_mod,
            "proficiency_bonus": proficiency_bonus,
        },
    }


def build_active_grapple_payload(
    *,
    actor: EncounterEntity,
    target: EncounterEntity,
    save_dc: dict[str, Any],
) -> dict[str, Any]:
    return {
        "target_entity_id": target.entity_id,
        "escape_dc": int(save_dc["dc"]),
        "dc_ability_used": str(save_dc["ability_used"]),
        "movement_speed_halved": True,
        "source_condition": f"grappled:{actor.entity_id}",
    }


def extract_grapple_source_id(entity: EncounterEntity) -> str | None:
    for condition in entity.conditions:
        if isinstance(condition, str) and condition.startswith("grappled:"):
            source_id = condition.split(":", 1)[1].strip()
            if source_id:
                return source_id
    return None


def get_active_grapple_payload(actor: EncounterEntity) -> dict[str, Any] | None:
    combat_flags = actor.combat_flags if isinstance(actor.combat_flags, dict) else {}
    active_grapple = combat_flags.get("active_grapple")
    if not isinstance(active_grapple, dict):
        return None
    return active_grapple


def get_active_grapple_target(encounter: Encounter, actor: EncounterEntity) -> EncounterEntity | None:
    active_grapple = get_active_grapple_payload(actor)
    if active_grapple is None:
        return None
    target_id = active_grapple.get("target_entity_id")
    if not isinstance(target_id, str) or not target_id:
        return None
    target = encounter.entities.get(target_id)
    if target is None:
        return None
    if f"grappled:{actor.entity_id}" not in target.conditions:
        return None
    return target


def has_active_grapple_target(encounter: Encounter, actor: EncounterEntity) -> bool:
    return get_active_grapple_target(encounter, actor) is not None


def grapple_size_is_legal(actor: EncounterEntity, target: EncounterEntity) -> bool:
    actor_size = _SIZE_ORDER.get(actor.size, 2)
    target_size = _SIZE_ORDER.get(target.size, 2)
    return target_size <= actor_size + 1


def resolve_dragged_target_position(
    *,
    start_position: dict[str, int],
    walked_path: list[dict[str, int]],
) -> dict[str, int] | None:
    if not walked_path:
        return None
    if len(walked_path) == 1:
        return {"x": start_position["x"], "y": start_position["y"]}
    previous_anchor = walked_path[-2]
    return {"x": int(previous_anchor["x"]), "y": int(previous_anchor["y"])}


def release_grapple_if_invalid(encounter: Encounter, grappler_id: str) -> bool:
    grappler = encounter.entities.get(grappler_id)
    if grappler is None:
        return False
    active_grapple = get_active_grapple_payload(grappler)
    if active_grapple is None:
        return False

    target_id = active_grapple.get("target_entity_id")
    if not isinstance(target_id, str) or not target_id:
        grappler.combat_flags.pop("active_grapple", None)
        return True

    target = encounter.entities.get(target_id)
    grappler_runtime = ConditionRuntime(grappler.conditions or [])
    should_release = (
        target is None
        or grappler_runtime.has("incapacitated")
        or f"grappled:{grappler_id}" not in getattr(target, "conditions", [])
    )
    if not should_release:
        return False

    if target is not None:
        target.conditions = [condition for condition in target.conditions if condition != f"grappled:{grappler_id}"]
    grappler.combat_flags.pop("active_grapple", None)
    return True
