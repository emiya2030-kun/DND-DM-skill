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


def get_monk_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    runtime = get_class_runtime(entity_or_class_features, "monk")
    if not runtime:
        return {}
    return ensure_monk_runtime(entity_or_class_features)


def ensure_monk_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    monk = ensure_class_runtime(entity_or_class_features, "monk")
    level = int(monk.get("level", 0) or 0)

    explicit_martial_arts_die = monk.get("martial_arts_die")
    monk["martial_arts_die"] = (
        _resolve_monk_martial_arts_die(level)
        if level > 0
        else explicit_martial_arts_die if isinstance(explicit_martial_arts_die, str) and explicit_martial_arts_die.strip() else "1d6"
    )
    explicit_unarmored_movement = monk.get("unarmored_movement_bonus_feet")
    monk["unarmored_movement_bonus_feet"] = (
        _resolve_monk_unarmored_movement_bonus(level)
        if level > 0
        else explicit_unarmored_movement if isinstance(explicit_unarmored_movement, int) else 0
    )

    focus_points = monk.setdefault("focus_points", {})
    focus_points["max"] = _resolve_monk_focus_points_max(level) if level > 0 else int(focus_points.get("max", 0) or 0)
    remaining = focus_points.get("remaining")
    focus_points["remaining"] = remaining if isinstance(remaining, int) else focus_points["max"]

    martial_arts = monk.setdefault("martial_arts", {})
    explicit_martial_arts_enabled = martial_arts.get("enabled")
    martial_arts["enabled"] = explicit_martial_arts_enabled if isinstance(explicit_martial_arts_enabled, bool) else level >= 1
    if not isinstance(martial_arts.get("grapple_dc_ability"), str):
        martial_arts["grapple_dc_ability"] = "dex"

    uncanny_metabolism = monk.setdefault("uncanny_metabolism", {})
    explicit_uncanny_metabolism_available = uncanny_metabolism.get("available")
    uncanny_metabolism["available"] = (
        explicit_uncanny_metabolism_available
        if isinstance(explicit_uncanny_metabolism_available, bool)
        else level >= 2
    )

    deflect_attacks = monk.setdefault("deflect_attacks", {})
    explicit_deflect_attacks_enabled = deflect_attacks.get("enabled")
    deflect_attacks["enabled"] = bool(explicit_deflect_attacks_enabled) or level >= 3

    slow_fall = monk.setdefault("slow_fall", {})
    explicit_slow_fall_enabled = slow_fall.get("enabled")
    slow_fall["enabled"] = bool(explicit_slow_fall_enabled) or level >= 4

    stunning_strike = monk.setdefault("stunning_strike", {})
    explicit_stunning_strike_enabled = stunning_strike.get("enabled")
    stunning_strike["enabled"] = bool(explicit_stunning_strike_enabled) or level >= 5
    if not isinstance(stunning_strike.get("max_per_turn"), int):
        stunning_strike["max_per_turn"] = 1
    stunning_strike.setdefault("uses_this_turn", 0)

    empowered_strikes = monk.setdefault("empowered_strikes", {})
    explicit_empowered_strikes_enabled = empowered_strikes.get("enabled")
    empowered_strikes["enabled"] = bool(explicit_empowered_strikes_enabled) or level >= 6

    evasion = monk.setdefault("evasion", {})
    explicit_evasion_enabled = evasion.get("enabled")
    evasion["enabled"] = bool(explicit_evasion_enabled) or level >= 7

    heightened_focus = monk.setdefault("heightened_focus", {})
    explicit_heightened_focus_enabled = heightened_focus.get("enabled")
    heightened_focus["enabled"] = bool(explicit_heightened_focus_enabled) or level >= 10

    deflect_energy = monk.setdefault("deflect_energy", {})
    explicit_deflect_energy_enabled = deflect_energy.get("enabled")
    deflect_energy["enabled"] = bool(explicit_deflect_energy_enabled) or level >= 13

    return monk


def get_barbarian_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    return get_class_runtime(entity_or_class_features, "barbarian")


def ensure_barbarian_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    return ensure_class_runtime(entity_or_class_features, "barbarian")


def get_paladin_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    runtime = get_class_runtime(entity_or_class_features, "paladin")
    if not runtime:
        return {}
    return ensure_paladin_runtime(entity_or_class_features)


def ensure_paladin_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    paladin = ensure_class_runtime(entity_or_class_features, "paladin")
    level = int(paladin.get("level", 0) or 0)
    default_aura_radius_feet = 30 if level >= 18 else 10

    lay_on_hands = paladin.setdefault("lay_on_hands", {})
    lay_on_hands["pool_max"] = level * 5 if level > 0 else int(lay_on_hands.get("pool_max", 0) or 0)
    pool_remaining = lay_on_hands.get("pool_remaining")
    lay_on_hands["pool_remaining"] = pool_remaining if isinstance(pool_remaining, int) else lay_on_hands["pool_max"]

    divine_smite = paladin.setdefault("divine_smite", {})
    explicit_divine_smite_enabled = divine_smite.get("enabled")
    divine_smite["enabled"] = explicit_divine_smite_enabled if isinstance(explicit_divine_smite_enabled, bool) else level >= 2

    aura_of_protection = paladin.setdefault("aura_of_protection", {})
    explicit_aura_enabled = aura_of_protection.get("enabled")
    aura_of_protection["enabled"] = explicit_aura_enabled if isinstance(explicit_aura_enabled, bool) else level >= 6
    radius_feet = aura_of_protection.get("radius_feet")
    aura_of_protection["radius_feet"] = radius_feet if isinstance(radius_feet, int) else default_aura_radius_feet

    channel_divinity = paladin.setdefault("channel_divinity", {})
    explicit_channel_divinity_enabled = channel_divinity.get("enabled")
    channel_divinity["enabled"] = (
        explicit_channel_divinity_enabled if isinstance(explicit_channel_divinity_enabled, bool) else level >= 3
    )
    channel_divinity["max_uses"] = 3 if level >= 11 else 2 if level >= 3 else 0
    remaining_uses = channel_divinity.get("remaining_uses")
    channel_divinity["remaining_uses"] = (
        remaining_uses if isinstance(remaining_uses, int) else channel_divinity["max_uses"]
    )

    aura_of_courage = paladin.setdefault("aura_of_courage", {})
    explicit_aura_of_courage_enabled = aura_of_courage.get("enabled")
    aura_of_courage["enabled"] = (
        explicit_aura_of_courage_enabled if isinstance(explicit_aura_of_courage_enabled, bool) else level >= 10
    )
    aura_of_courage_radius = aura_of_courage.get("radius_feet")
    aura_of_courage["radius_feet"] = (
        aura_of_courage_radius if isinstance(aura_of_courage_radius, int) else default_aura_radius_feet
    )

    faithful_steed = paladin.setdefault("faithful_steed", {})
    explicit_faithful_steed_enabled = faithful_steed.get("enabled")
    faithful_steed["enabled"] = (
        explicit_faithful_steed_enabled if isinstance(explicit_faithful_steed_enabled, bool) else level >= 5
    )
    free_cast_available = faithful_steed.get("free_cast_available")
    faithful_steed["free_cast_available"] = (
        free_cast_available if isinstance(free_cast_available, bool) else level >= 5
    )

    radiant_strikes = paladin.setdefault("radiant_strikes", {})
    explicit_radiant_strikes_enabled = radiant_strikes.get("enabled")
    radiant_strikes["enabled"] = (
        explicit_radiant_strikes_enabled if isinstance(explicit_radiant_strikes_enabled, bool) else level >= 11
    )

    return paladin


def get_ranger_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    runtime = get_class_runtime(entity_or_class_features, "ranger")
    if not runtime:
        return {}
    return ensure_ranger_runtime(entity_or_class_features)


def ensure_ranger_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    ranger = ensure_class_runtime(entity_or_class_features, "ranger")
    level = int(ranger.get("level", 0) or 0)
    wisdom_modifier = _extract_ability_modifier(entity_or_class_features, "wis")
    minimum_wisdom_uses = max(1, wisdom_modifier)

    ranger["weapon_mastery_count"] = 2
    ranger["extra_attack_count"] = 2 if level >= 5 else 1

    favored_enemy = ranger.setdefault("favored_enemy", {})
    explicit_favored_enemy_enabled = favored_enemy.get("enabled")
    favored_enemy["enabled"] = explicit_favored_enemy_enabled if isinstance(explicit_favored_enemy_enabled, bool) else level >= 1
    free_cast_uses_max = favored_enemy.get("free_cast_uses_max")
    favored_enemy["free_cast_uses_max"] = free_cast_uses_max if isinstance(free_cast_uses_max, int) else (2 if level >= 1 else 0)
    favored_enemy.setdefault("spell_id", "hunters_mark")
    remaining_free_cast_uses = favored_enemy.get("free_cast_uses_remaining")
    favored_enemy["free_cast_uses_remaining"] = (
        remaining_free_cast_uses if isinstance(remaining_free_cast_uses, int) else favored_enemy["free_cast_uses_max"]
    )

    expertise = ranger.setdefault("expertise", {})
    skills = expertise.get("skills")
    expertise["skills"] = list(skills) if isinstance(skills, list) else []

    deft_explorer = ranger.setdefault("deft_explorer", {})
    deft_explorer["enabled"] = level >= 2
    languages = deft_explorer.get("languages")
    deft_explorer["languages"] = list(languages) if isinstance(languages, list) else []

    fighting_style = ranger.setdefault("fighting_style", {})
    fighting_style["enabled"] = level >= 2

    roving = ranger.setdefault("roving", {})
    roving["enabled"] = level >= 6
    roving["speed_bonus_feet"] = 10 if level >= 6 else 0

    tireless = ranger.setdefault("tireless", {})
    tireless["enabled"] = level >= 10
    temp_hp_uses_max = tireless.get("temp_hp_uses_max")
    tireless["temp_hp_uses_max"] = (
        temp_hp_uses_max if isinstance(temp_hp_uses_max, int) else (minimum_wisdom_uses if level >= 10 else 0)
    )
    temp_hp_uses_remaining = tireless.get("temp_hp_uses_remaining")
    tireless["temp_hp_uses_remaining"] = (
        temp_hp_uses_remaining if isinstance(temp_hp_uses_remaining, int) else tireless["temp_hp_uses_max"]
    )

    relentless_hunter = ranger.setdefault("relentless_hunter", {})
    relentless_hunter["enabled"] = level >= 13

    natures_veil = ranger.setdefault("natures_veil", {})
    natures_veil["enabled"] = level >= 14
    uses_max = natures_veil.get("uses_max")
    natures_veil["uses_max"] = uses_max if isinstance(uses_max, int) else (minimum_wisdom_uses if level >= 14 else 0)
    uses_remaining = natures_veil.get("uses_remaining")
    natures_veil["uses_remaining"] = uses_remaining if isinstance(uses_remaining, int) else natures_veil["uses_max"]

    precise_hunter = ranger.setdefault("precise_hunter", {})
    precise_hunter["enabled"] = level >= 17

    feral_senses = ranger.setdefault("feral_senses", {})
    feral_senses["enabled"] = level >= 18
    feral_senses["blindsight_feet"] = 30 if level >= 18 else 0

    foe_slayer = ranger.setdefault("foe_slayer", {})
    foe_slayer["enabled"] = level >= 20
    foe_slayer["hunters_mark_damage_die"] = "1d10" if level >= 20 else "1d6"

    return ranger


def get_sorcerer_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    runtime = get_class_runtime(entity_or_class_features, "sorcerer")
    if not runtime:
        return {}
    return ensure_sorcerer_runtime(entity_or_class_features)


def ensure_sorcerer_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    sorcerer = ensure_class_runtime(entity_or_class_features, "sorcerer")
    level = int(sorcerer.get("level", 0) or 0)

    sorcerer["cantrips_known"] = _resolve_sorcerer_cantrips_known(level)
    sorcerer["prepared_spells_count"] = _resolve_sorcerer_prepared_spells_count(level)

    sorcery_points = sorcerer.setdefault("sorcery_points", {})
    sorcery_points["max"] = level if level > 0 else int(sorcery_points.get("max", 0) or 0)
    current = sorcery_points.get("current")
    sorcery_points["current"] = current if isinstance(current, int) else sorcery_points["max"]

    innate_sorcery = sorcerer.setdefault("innate_sorcery", {})
    innate_sorcery["enabled"] = level >= 1
    innate_sorcery["uses_max"] = 2 if level >= 1 else 0
    uses_current = innate_sorcery.get("uses_current")
    innate_sorcery["uses_current"] = uses_current if isinstance(uses_current, int) else innate_sorcery["uses_max"]
    innate_sorcery["active"] = bool(innate_sorcery.get("active"))
    innate_sorcery.setdefault("expires_at_turn", None)

    font_of_magic = sorcerer.setdefault("font_of_magic", {})
    font_of_magic["enabled"] = level >= 2

    sorcerous_restoration = sorcerer.setdefault("sorcerous_restoration", {})
    sorcerous_restoration["enabled"] = level >= 5
    sorcerous_restoration["used_since_long_rest"] = bool(sorcerous_restoration.get("used_since_long_rest", False))

    sorcery_incarnate = sorcerer.setdefault("sorcery_incarnate", {})
    sorcery_incarnate["enabled"] = level >= 7

    created_spell_slots = sorcerer.setdefault("created_spell_slots", {})
    for slot_level in range(1, 6):
        key = str(slot_level)
        value = created_spell_slots.get(key)
        created_spell_slots[key] = value if isinstance(value, int) and value >= 0 else 0

    return sorcerer


def get_warlock_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    runtime = get_class_runtime(entity_or_class_features, "warlock")
    if not runtime:
        return {}
    return ensure_warlock_runtime(entity_or_class_features)


def ensure_warlock_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    warlock = ensure_class_runtime(entity_or_class_features, "warlock")
    level = int(warlock.get("level", 0) or 0)

    warlock["invocations_known"] = _resolve_warlock_invocations_known(level)
    warlock["cantrips_known"] = _resolve_warlock_cantrips_known(level)
    warlock["prepared_spells_count"] = _resolve_warlock_prepared_spells_count(level)

    invocations = warlock.setdefault("eldritch_invocations", {})
    selected = invocations.get("selected")
    invocations["selected"] = list(selected) if isinstance(selected, list) else []
    invocations["known"] = warlock["invocations_known"]
    selected_invocation_ids = {
        str(entry.get("invocation_id") or entry.get("id") or "").strip().lower()
        for entry in invocations["selected"]
        if isinstance(entry, dict)
    }

    pact_of_the_blade = warlock.setdefault("pact_of_the_blade", {})
    explicit_pact_enabled = pact_of_the_blade.get("enabled")
    pact_of_the_blade["enabled"] = (
        explicit_pact_enabled if isinstance(explicit_pact_enabled, bool) else "pact_of_the_blade" in selected_invocation_ids
    )
    bound_weapon_id = pact_of_the_blade.get("bound_weapon_id")
    pact_of_the_blade["bound_weapon_id"] = bound_weapon_id if isinstance(bound_weapon_id, str) else None
    bound_weapon_name = pact_of_the_blade.get("bound_weapon_name")
    pact_of_the_blade["bound_weapon_name"] = bound_weapon_name if isinstance(bound_weapon_name, str) else None
    damage_type_override = pact_of_the_blade.get("damage_type_override")
    pact_of_the_blade["damage_type_override"] = (
        damage_type_override if isinstance(damage_type_override, str) and damage_type_override.strip() else None
    )

    pact_of_the_chain = warlock.setdefault("pact_of_the_chain", {})
    explicit_chain_enabled = pact_of_the_chain.get("enabled")
    pact_of_the_chain["enabled"] = (
        explicit_chain_enabled if isinstance(explicit_chain_enabled, bool) else "pact_of_the_chain" in selected_invocation_ids
    )
    familiar_entity_id = pact_of_the_chain.get("familiar_entity_id")
    pact_of_the_chain["familiar_entity_id"] = familiar_entity_id if isinstance(familiar_entity_id, str) else None
    familiar_name = pact_of_the_chain.get("familiar_name")
    pact_of_the_chain["familiar_name"] = familiar_name if isinstance(familiar_name, str) else None
    familiar_form_id = pact_of_the_chain.get("familiar_form_id")
    pact_of_the_chain["familiar_form_id"] = familiar_form_id if isinstance(familiar_form_id, str) else None

    armor_of_shadows = warlock.setdefault("armor_of_shadows", {})
    explicit_armor_of_shadows_enabled = armor_of_shadows.get("enabled")
    armor_of_shadows["enabled"] = (
        explicit_armor_of_shadows_enabled
        if isinstance(explicit_armor_of_shadows_enabled, bool)
        else level >= 1 and "armor_of_shadows" in selected_invocation_ids
    )

    fiendish_vigor = warlock.setdefault("fiendish_vigor", {})
    explicit_fiendish_vigor_enabled = fiendish_vigor.get("enabled")
    fiendish_vigor["enabled"] = (
        explicit_fiendish_vigor_enabled
        if isinstance(explicit_fiendish_vigor_enabled, bool)
        else level >= 2 and "fiendish_vigor" in selected_invocation_ids
    )

    eldritch_mind = warlock.setdefault("eldritch_mind", {})
    explicit_eldritch_mind_enabled = eldritch_mind.get("enabled")
    eldritch_mind["enabled"] = (
        explicit_eldritch_mind_enabled
        if isinstance(explicit_eldritch_mind_enabled, bool)
        else level >= 2 and "eldritch_mind" in selected_invocation_ids
    )

    devils_sight = warlock.setdefault("devils_sight", {})
    explicit_devils_sight_enabled = devils_sight.get("enabled")
    devils_sight["enabled"] = (
        explicit_devils_sight_enabled
        if isinstance(explicit_devils_sight_enabled, bool)
        else level >= 2 and "devils_sight" in selected_invocation_ids
    )
    if not isinstance(devils_sight.get("range_feet"), int):
        devils_sight["range_feet"] = 120
    if not isinstance(devils_sight.get("sees_magical_darkness"), bool):
        devils_sight["sees_magical_darkness"] = True

    turn_counters = warlock.get("turn_counters")
    warlock["turn_counters"] = dict(turn_counters) if isinstance(turn_counters, dict) else {}
    attack_action_attacks_used = warlock["turn_counters"].get("attack_action_attacks_used")
    warlock["turn_counters"]["attack_action_attacks_used"] = (
        attack_action_attacks_used if isinstance(attack_action_attacks_used, int) and attack_action_attacks_used >= 0 else 0
    )

    lifedrinker = warlock.setdefault("lifedrinker", {})
    explicit_lifedrinker_enabled = lifedrinker.get("enabled")
    lifedrinker["enabled"] = (
        explicit_lifedrinker_enabled
        if isinstance(explicit_lifedrinker_enabled, bool)
        else level >= 9 and "lifedrinker" in selected_invocation_ids
    )
    used_this_turn = lifedrinker.get("used_this_turn")
    lifedrinker["used_this_turn"] = used_this_turn if isinstance(used_this_turn, bool) else False

    eldritch_smite = warlock.setdefault("eldritch_smite", {})
    explicit_eldritch_smite_enabled = eldritch_smite.get("enabled")
    eldritch_smite["enabled"] = (
        explicit_eldritch_smite_enabled
        if isinstance(explicit_eldritch_smite_enabled, bool)
        else level >= 5 and "eldritch_smite" in selected_invocation_ids
    )
    eldritch_smite_used_this_turn = eldritch_smite.get("used_this_turn")
    eldritch_smite["used_this_turn"] = (
        eldritch_smite_used_this_turn if isinstance(eldritch_smite_used_this_turn, bool) else False
    )

    gaze_of_two_minds = warlock.setdefault("gaze_of_two_minds", {})
    explicit_gaze_enabled = gaze_of_two_minds.get("enabled")
    gaze_of_two_minds["enabled"] = (
        explicit_gaze_enabled
        if isinstance(explicit_gaze_enabled, bool)
        else level >= 5 and "gaze_of_two_minds" in selected_invocation_ids
    )
    linked_entity_id = gaze_of_two_minds.get("linked_entity_id")
    gaze_of_two_minds["linked_entity_id"] = linked_entity_id if isinstance(linked_entity_id, str) else None
    linked_entity_name = gaze_of_two_minds.get("linked_entity_name")
    gaze_of_two_minds["linked_entity_name"] = linked_entity_name if isinstance(linked_entity_name, str) else None
    remaining_source_turn_ends = gaze_of_two_minds.get("remaining_source_turn_ends")
    gaze_of_two_minds["remaining_source_turn_ends"] = (
        remaining_source_turn_ends
        if isinstance(remaining_source_turn_ends, int) and remaining_source_turn_ends >= 0
        else 0
    )
    special_senses = gaze_of_two_minds.get("special_senses")
    gaze_of_two_minds["special_senses"] = dict(special_senses) if isinstance(special_senses, dict) else {}

    magical_cunning = warlock.setdefault("magical_cunning", {})
    explicit_magical_cunning_enabled = magical_cunning.get("enabled")
    magical_cunning["enabled"] = (
        explicit_magical_cunning_enabled if isinstance(explicit_magical_cunning_enabled, bool) else level >= 2
    )
    available = magical_cunning.get("available")
    magical_cunning["available"] = available if isinstance(available, bool) else level >= 2

    contact_patron = warlock.setdefault("contact_patron", {})
    explicit_contact_patron_enabled = contact_patron.get("enabled")
    contact_patron["enabled"] = (
        explicit_contact_patron_enabled if isinstance(explicit_contact_patron_enabled, bool) else level >= 9
    )
    free_cast_available = contact_patron.get("free_cast_available")
    contact_patron["free_cast_available"] = (
        free_cast_available if isinstance(free_cast_available, bool) else level >= 9
    )
    contact_patron["spell_id"] = "contact_other_plane"
    contact_patron["auto_succeeds_save"] = True

    mystic_arcanum = warlock.setdefault("mystic_arcanum", {})
    for spell_level, required_level in ((6, 11), (7, 13), (8, 15), (9, 17)):
        bucket = mystic_arcanum.setdefault(str(spell_level), {})
        bucket["enabled"] = level >= required_level
        bucket["max_uses"] = 1 if level >= required_level else 0
        remaining_uses = bucket.get("remaining_uses")
        bucket["remaining_uses"] = remaining_uses if isinstance(remaining_uses, int) else bucket["max_uses"]

    eldritch_master = warlock.setdefault("eldritch_master", {})
    explicit_eldritch_master_enabled = eldritch_master.get("enabled")
    eldritch_master["enabled"] = (
        explicit_eldritch_master_enabled if isinstance(explicit_eldritch_master_enabled, bool) else level >= 20
    )

    return warlock


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


def _extract_ability_modifier(entity_or_class_features: Any, ability: str) -> int:
    if isinstance(entity_or_class_features, dict):
        ability_mods = entity_or_class_features.get("ability_mods")
    else:
        ability_mods = getattr(entity_or_class_features, "ability_mods", None)
    if not isinstance(ability_mods, dict):
        return 0
    value = ability_mods.get(ability)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def _resolve_monk_martial_arts_die(level: int) -> str:
    if level >= 17:
        return "1d12"
    if level >= 11:
        return "1d10"
    if level >= 5:
        return "1d8"
    return "1d6"


def _resolve_monk_focus_points_max(level: int) -> int:
    return level if level >= 2 else 0


def _resolve_monk_unarmored_movement_bonus(level: int) -> int:
    if level >= 18:
        return 30
    if level >= 14:
        return 25
    if level >= 10:
        return 20
    if level >= 6:
        return 15
    if level >= 2:
        return 10
    return 0


def _resolve_warlock_invocations_known(level: int) -> int:
    if level >= 18:
        return 10
    if level >= 15:
        return 9
    if level >= 12:
        return 8
    if level >= 9:
        return 7
    if level >= 7:
        return 6
    if level >= 5:
        return 5
    if level >= 2:
        return 3
    return 1 if level >= 1 else 0


def _resolve_warlock_cantrips_known(level: int) -> int:
    if level >= 10:
        return 4
    if level >= 4:
        return 3
    return 2 if level >= 1 else 0


def _resolve_warlock_prepared_spells_count(level: int) -> int:
    if level >= 19:
        return 15
    if level >= 17:
        return 14
    if level >= 16:
        return 13
    if level >= 15:
        return 13
    if level >= 14:
        return 12
    if level >= 13:
        return 12
    if level >= 11:
        return 11
    if level >= 10:
        return 10
    if level >= 9:
        return 10
    if level >= 8:
        return 9
    if level >= 7:
        return 8
    if level >= 6:
        return 7
    if level >= 5:
        return 6
    if level >= 4:
        return 5
    if level >= 3:
        return 4
    if level >= 2:
        return 3
    return 2 if level >= 1 else 0


def _resolve_sorcerer_cantrips_known(level: int) -> int:
    if level >= 10:
        return 6
    if level >= 4:
        return 5
    return 4 if level >= 1 else 0


def _resolve_sorcerer_prepared_spells_count(level: int) -> int:
    progression = {
        1: 2,
        2: 4,
        3: 6,
        4: 7,
        5: 9,
        6: 10,
        7: 11,
        8: 12,
        9: 14,
        10: 15,
        11: 16,
        12: 16,
        13: 17,
        14: 17,
        15: 18,
        16: 18,
        17: 19,
        18: 20,
        19: 21,
        20: 22,
    }
    return progression.get(level, 0)
