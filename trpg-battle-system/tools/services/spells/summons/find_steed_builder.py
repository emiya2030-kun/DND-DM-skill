from __future__ import annotations

from uuid import uuid4

from tools.models import EncounterEntity


_STEED_DAMAGE_TYPES = {
    "celestial": "radiant",
    "fey": "psychic",
    "fiend": "necrotic",
}


def build_find_steed_entity(
    *,
    caster: EncounterEntity,
    cast_level: int,
    summon_position: dict[str, int],
    steed_type: str,
    appearance: str,
    source_spell_instance_id: str,
) -> EncounterEntity:
    normalized_steed_type = str(steed_type or "").strip().lower()
    if normalized_steed_type not in _STEED_DAMAGE_TYPES:
        raise ValueError("invalid_find_steed_type")
    if not isinstance(cast_level, int) or cast_level < 2:
        raise ValueError("find_steed_cast_level_invalid")

    speed = {"walk": 60, "remaining": 60}
    if cast_level >= 4:
        speed["fly"] = 60

    hp_max = 5 + cast_level * 10
    damage_type = _STEED_DAMAGE_TYPES[normalized_steed_type]
    appearance_label = appearance.strip() if isinstance(appearance, str) and appearance.strip() else "steed"

    return EncounterEntity(
        entity_id=f"ent_steed_{uuid4().hex[:12]}",
        name="Otherworldly Steed",
        side=caster.side,
        category="summon",
        controller=caster.controller,
        position=dict(summon_position),
        hp={"current": hp_max, "max": hp_max, "temp": 0},
        ac=10 + cast_level,
        speed=speed,
        initiative=caster.initiative,
        size="large",
        proficiency_bonus=int(caster.proficiency_bonus or 0),
        ability_scores={"str": 18, "dex": 12, "con": 14, "int": 6, "wis": 12, "cha": 8},
        ability_mods={"str": 4, "dex": 1, "con": 2, "int": -2, "wis": 1, "cha": -1},
        weapons=[
            {
                "id": "otherworldly_slam",
                "name": "Otherworldly Slam",
                "attack_type": "melee_weapon",
                "range": {"reach": 5},
                "damage": {"formula": f"1d8+{cast_level}", "damage_type": damage_type},
            }
        ],
        source_ref={
            "summoner_entity_id": caster.entity_id,
            "source_spell_id": "find_steed",
            "source_spell_instance_id": source_spell_instance_id,
            "summon_template": "otherworldly_steed",
            "steed_type": normalized_steed_type,
            "appearance": appearance_label,
        },
        combat_flags={
            "dismiss_on_zero_hp": True,
            "dismiss_on_summoner_death": True,
            "shares_initiative_with_summoner": True,
            "controlled_mount": True,
        },
    )
