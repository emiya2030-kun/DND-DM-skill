from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity


_INCAPACITATED_CONDITIONS = {"incapacitated", "paralyzed", "petrified", "stunned", "unconscious"}


def evaluate_monster_action_availability(
    encounter: Encounter,
    actor: EncounterEntity,
    action_definition: dict[str, Any],
    *,
    target: EncounterEntity | None = None,
) -> dict[str, Any]:
    blocked_reasons: list[str] = []

    availability = action_definition.get("availability")
    if isinstance(availability, dict):
        blocked_reasons.extend(_resolve_availability_blocks(actor, availability))

    resource_cost = action_definition.get("resource_cost")
    if isinstance(resource_cost, dict):
        blocked_reasons.extend(_resolve_resource_cost_blocks(actor, resource_cost))

    targeting = action_definition.get("targeting")
    if isinstance(targeting, dict) and targeting.get("target_filters"):
        if not _has_valid_target(encounter, actor, targeting, target=target):
            blocked_reasons.append("no_valid_target")

    deduped: list[str] = []
    for reason in blocked_reasons:
        if reason not in deduped:
            deduped.append(reason)
    return {
        "available": not deduped,
        "blocked_reasons": deduped,
    }


def _resolve_availability_blocks(
    actor: EncounterEntity,
    availability: dict[str, Any],
) -> list[str]:
    blocked: list[str] = []
    combat_profile = actor.source_ref.get("combat_profile") if isinstance(actor.source_ref, dict) else {}
    if not isinstance(combat_profile, dict):
        combat_profile = {}
    current_form = str(combat_profile.get("current_form") or "").strip()
    forms_any_of = availability.get("forms_any_of")
    if isinstance(forms_any_of, list) and forms_any_of:
        allowed_forms = {str(item).strip() for item in forms_any_of if str(item).strip()}
        if current_form not in allowed_forms:
            blocked.append("wrong_form")

    action_economy = actor.action_economy if isinstance(actor.action_economy, dict) else {}
    if availability.get("requires_action_available") and bool(action_economy.get("action_used")):
        blocked.append("action_used")
    if availability.get("requires_bonus_action_available") and bool(action_economy.get("bonus_action_used")):
        blocked.append("bonus_action_used")
    if availability.get("requires_reaction_available") and bool(action_economy.get("reaction_used")):
        blocked.append("reaction_used")
    if availability.get("not_in_sunlight") and bool(actor.combat_flags.get("in_sunlight")):
        blocked.append("in_sunlight")
    if availability.get("not_in_running_water") and bool(actor.combat_flags.get("in_running_water")):
        blocked.append("in_running_water")
    return blocked


def _resolve_resource_cost_blocks(
    actor: EncounterEntity,
    resource_cost: dict[str, Any],
) -> list[str]:
    blocked: list[str] = []
    legendary_cost = int(resource_cost.get("legendary_actions", 0) or 0)
    if legendary_cost > 0:
        remaining = _resolve_resource_remaining(actor, "legendary_actions")
        if remaining is not None and remaining < legendary_cost:
            blocked.append("legendary_actions_depleted")
    return blocked


def _resolve_resource_remaining(
    actor: EncounterEntity,
    resource_key: str,
) -> int | None:
    runtime_resources = actor.resources if isinstance(actor.resources, dict) else {}
    runtime_entry = runtime_resources.get(resource_key)
    if isinstance(runtime_entry, dict) and "remaining" in runtime_entry:
        return int(runtime_entry.get("remaining", 0) or 0)

    source_ref = actor.source_ref if isinstance(actor.source_ref, dict) else {}
    combat_profile = source_ref.get("combat_profile")
    if not isinstance(combat_profile, dict):
        return None
    profile_resources = combat_profile.get("resources")
    if not isinstance(profile_resources, dict):
        return None
    profile_entry = profile_resources.get(resource_key)
    if isinstance(profile_entry, dict) and "remaining" in profile_entry:
        return int(profile_entry.get("remaining", 0) or 0)
    return None


def _has_valid_target(
    encounter: Encounter,
    actor: EncounterEntity,
    targeting: dict[str, Any],
    *,
    target: EncounterEntity | None = None,
) -> bool:
    filters = [str(item).strip() for item in targeting.get("target_filters", []) if str(item).strip()]
    if not filters:
        return True
    allow_any = bool(targeting.get("allow_any_of_filters"))
    range_feet = int(targeting.get("range_feet", 0) or 0)
    target_pool = [target] if target is not None else list(encounter.entities.values())
    for candidate in target_pool:
        if candidate.entity_id == actor.entity_id or candidate.side == actor.side:
            continue
        if int(candidate.hp.get("current", 0) or 0) <= 0 or bool(candidate.combat_flags.get("is_dead")):
            continue
        if range_feet > 0 and _distance_feet(actor, candidate) > range_feet:
            continue
        matched = [_target_matches_filter(actor, candidate, filter_name) for filter_name in filters]
        if (allow_any and any(matched)) or (not allow_any and all(matched)):
            return True
    return False


def _target_matches_filter(
    actor: EncounterEntity,
    target: EncounterEntity,
    filter_name: str,
) -> bool:
    if filter_name == "grappled_by_self":
        return f"grappled:{actor.entity_id}" in (target.conditions or [])
    if filter_name == "incapacitated":
        return any(condition in _INCAPACITATED_CONDITIONS for condition in (target.conditions or []))
    if filter_name == "restrained":
        return "restrained" in (target.conditions or [])
    if filter_name == "willing":
        return bool(target.combat_flags.get("willing_for_monster_action"))
    if filter_name == "humanoid":
        source_ref = target.source_ref if isinstance(target.source_ref, dict) else {}
        return str(source_ref.get("creature_type") or source_ref.get("entity_type") or "").strip() == "humanoid"
    return False


def _distance_feet(
    source: EncounterEntity,
    target: EncounterEntity,
) -> int:
    dx = abs(int(source.position.get("x", 0) or 0) - int(target.position.get("x", 0) or 0))
    dy = abs(int(source.position.get("y", 0) or 0) - int(target.position.get("y", 0) or 0))
    return max(dx, dy) * 5
