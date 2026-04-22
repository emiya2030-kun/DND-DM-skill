from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from tools.models import EncounterEntity


_FAMILIAR_FORMS: dict[str, dict[str, object]] = {
    "slaad_tadpole": {
        "name": "Slaad Tadpole",
        "size": "tiny",
        "ac": 12,
        "hp": 7,
        "speed": {"walk": 30, "burrow": 10},
        "ability_scores": {"str": 7, "dex": 15, "con": 10, "int": 3, "wis": 5, "cha": 3},
        "ability_mods": {"str": -2, "dex": 2, "con": 0, "int": -4, "wis": -3, "cha": -4},
        "skill_modifiers": {"stealth": 4},
        "resistances": ["acid", "cold", "fire", "lightning", "thunder"],
        "special_senses": {"darkvision": 60, "passive_perception": 7},
        "languages": ["slaad"],
        "traits_metadata": [
            {
                "trait_id": "magic_resistance",
                "name_en": "Magic Resistance",
                "name_zh": "魔法抗性",
                "summary": "Advantage on saves against spells and magical effects.",
            }
        ],
        "weapons": [
            {
                "weapon_id": "bite",
                "name": "Bite",
                "attack_bonus": 4,
                "damage": [{"formula": "1d6+2", "type": "piercing"}],
                "range": {"normal": 5, "long": 5},
                "kind": "melee",
            }
        ],
    },
    "pseudodragon": {
        "name": "Pseudodragon",
        "size": "tiny",
        "ac": 14,
        "hp": 10,
        "speed": {"walk": 15, "fly": 60},
        "ability_scores": {"str": 6, "dex": 15, "con": 13, "int": 10, "wis": 12, "cha": 10},
        "ability_mods": {"str": -2, "dex": 2, "con": 1, "int": 0, "wis": 1, "cha": 0},
        "skill_modifiers": {"perception": 5, "stealth": 4},
        "special_senses": {"blindsight": 10, "darkvision": 60, "passive_perception": 15},
        "languages": ["common", "draconic"],
        "traits_metadata": [
            {
                "trait_id": "magic_resistance",
                "name_en": "Magic Resistance",
                "name_zh": "魔法抗性",
                "summary": "Advantage on saves against spells and magical effects.",
            }
        ],
        "actions_metadata": [
            {
                "action_id": "multiattack",
                "name_en": "Multiattack",
                "name_zh": "多重攻击",
                "summary": "Makes two Bite attacks.",
                "multiattack_sequences": [
                    {
                        "sequence_id": "double_bite",
                        "mode": "melee",
                        "steps": [
                            {"type": "weapon", "weapon_id": "bite"},
                            {"type": "weapon", "weapon_id": "bite"},
                        ],
                    }
                ],
            },
            {
                "action_id": "sting",
                "name_en": "Sting",
                "name_zh": "蛰刺",
                "summary": "Con save DC 12; poison damage and may poison or knock target unconscious.",
            },
        ],
        "weapons": [
            {
                "weapon_id": "bite",
                "name": "Bite",
                "attack_bonus": 4,
                "damage": [{"formula": "1d4+2", "type": "piercing"}],
                "range": {"normal": 5, "long": 5},
                "kind": "melee",
            },
            {
                "weapon_id": "sting",
                "name": "Sting",
                "attack_bonus": 4,
                "damage": [{"formula": "2d4", "type": "poison"}],
                "range": {"normal": 5, "long": 5},
                "kind": "melee",
                "on_hit_metadata": {
                    "save": {"ability": "con", "dc": 12},
                    "extra_effect": "poisoned_or_unconscious",
                },
            },
        ],
    },
    "owl": {
        "name": "Owl",
        "size": "tiny",
        "ac": 11,
        "hp": 1,
        "speed": {"walk": 5, "fly": 60},
        "ability_scores": {"str": 3, "dex": 13, "con": 8, "int": 2, "wis": 12, "cha": 7},
        "ability_mods": {"str": -4, "dex": 1, "con": -1, "int": -4, "wis": 1, "cha": -2},
        "skill_modifiers": {"perception": 5, "stealth": 5},
        "special_senses": {"darkvision": 120, "passive_perception": 15},
        "languages": [],
        "traits_metadata": [
            {
                "trait_id": "flyby",
                "name_en": "Flyby",
                "name_zh": "飞掠",
                "summary": "Flying out of an enemy's reach does not provoke opportunity attacks.",
            }
        ],
        "weapons": [
            {
                "weapon_id": "talons",
                "name": "Talons",
                "attack_bonus": 3,
                "damage": [{"formula": "1", "type": "slashing"}],
                "range": {"normal": 5, "long": 5},
                "kind": "melee",
            }
        ],
    },
    "skeleton": {
        "name": "Skeleton",
        "size": "medium",
        "ac": 14,
        "hp": 13,
        "speed": {"walk": 30},
        "ability_scores": {"str": 10, "dex": 16, "con": 15, "int": 6, "wis": 8, "cha": 5},
        "ability_mods": {"str": 0, "dex": 3, "con": 2, "int": -2, "wis": -1, "cha": -3},
        "special_senses": {"darkvision": 60, "passive_perception": 9},
        "languages": ["common", "other"],
        "immunities": ["poison"],
        "vulnerabilities": ["bludgeoning"],
        "condition_immunities": ["exhaustion", "poisoned"],
        "weapons": [
            {
                "weapon_id": "shortsword",
                "name": "Shortsword",
                "attack_bonus": 5,
                "damage": [{"formula": "1d6+3", "type": "piercing"}],
                "range": {"normal": 5, "long": 5},
                "kind": "melee",
            },
            {
                "weapon_id": "shortbow",
                "name": "Shortbow",
                "attack_bonus": 5,
                "damage": [{"formula": "1d6+3", "type": "piercing"}],
                "range": {"normal": 80, "long": 320},
                "kind": "ranged",
            },
        ],
    },
    "zombie": {
        "name": "Zombie",
        "size": "medium",
        "ac": 8,
        "hp": 15,
        "speed": {"walk": 20},
        "ability_scores": {"str": 13, "dex": 6, "con": 16, "int": 3, "wis": 6, "cha": 5},
        "ability_mods": {"str": 1, "dex": -2, "con": 3, "int": -4, "wis": -2, "cha": -3},
        "special_senses": {"darkvision": 60, "passive_perception": 8},
        "languages": ["common", "other"],
        "immunities": ["poison"],
        "condition_immunities": ["exhaustion", "poisoned"],
        "traits_metadata": [
            {
                "trait_id": "undead_fortitude",
                "name_en": "Undead Fortitude",
                "name_zh": "不死坚韧",
                "summary": "When reduced to 0 HP by non-radiant, non-critical damage, make a Con save to drop to 1 HP instead.",
            }
        ],
        "weapons": [
            {
                "weapon_id": "slam",
                "name": "Slam",
                "attack_bonus": 3,
                "damage": [{"formula": "1d8+1", "type": "bludgeoning"}],
                "range": {"normal": 5, "long": 5},
                "kind": "melee",
            }
        ],
    },
    "sprite": {
        "name": "Sprite",
        "size": "tiny",
        "ac": 15,
        "hp": 10,
        "speed": {"walk": 10, "fly": 40},
        "ability_scores": {"str": 3, "dex": 18, "con": 10, "int": 14, "wis": 13, "cha": 11},
        "ability_mods": {"str": -4, "dex": 4, "con": 0, "int": 2, "wis": 1, "cha": 0},
        "skill_modifiers": {"perception": 3, "stealth": 8},
        "special_senses": {"passive_perception": 13},
        "languages": ["common", "elvish", "sylvan"],
        "actions_metadata": [
            {
                "action_id": "heart_sight",
                "name_en": "Heart Sight",
                "name_zh": "真心视界",
                "summary": "Cha save DC 10; learn a creature's emotional state and alignment.",
            },
            {
                "action_id": "invisibility",
                "name_en": "Invisibility",
                "name_zh": "隐形",
                "summary": "Casts Invisibility on itself.",
            },
        ],
        "weapons": [
            {
                "weapon_id": "needle_sword",
                "name": "Needle Sword",
                "attack_bonus": 6,
                "damage": [{"formula": "1d4+4", "type": "piercing"}],
                "range": {"normal": 5, "long": 5},
                "kind": "melee",
            },
            {
                "weapon_id": "enchanting_bow",
                "name": "Enchanting Bow",
                "attack_bonus": 6,
                "damage": [{"formula": "1", "type": "piercing"}],
                "range": {"normal": 40, "long": 160},
                "kind": "ranged",
                "on_hit_metadata": {"applies_condition": "charmed", "duration": "until_sprite_next_turn_start"},
            },
        ],
    },
    "quasit": {
        "name": "Quasit",
        "size": "tiny",
        "ac": 13,
        "hp": 25,
        "speed": {"walk": 40},
        "ability_scores": {"str": 5, "dex": 17, "con": 10, "int": 7, "wis": 10, "cha": 10},
        "ability_mods": {"str": -3, "dex": 3, "con": 0, "int": -2, "wis": 0, "cha": 0},
        "skill_modifiers": {"stealth": 5},
        "resistances": ["cold", "fire", "lightning"],
        "immunities": ["poison"],
        "condition_immunities": ["poisoned"],
        "special_senses": {"darkvision": 120, "passive_perception": 10},
        "languages": ["abyssal", "common"],
        "traits_metadata": [
            {
                "trait_id": "magic_resistance",
                "name_en": "Magic Resistance",
                "name_zh": "魔法抗性",
                "summary": "Advantage on saves against spells and magical effects.",
            }
        ],
        "actions_metadata": [
            {
                "action_id": "invisibility",
                "name_en": "Invisibility",
                "name_zh": "隐形",
                "summary": "Casts Invisibility on itself.",
            },
            {
                "action_id": "scare",
                "name_en": "Scare",
                "name_zh": "惊吓",
                "summary": "Wis save DC 10 or frightened; repeats at end of each turn.",
            },
            {
                "action_id": "shape_shift",
                "name_en": "Shape-Shift",
                "name_zh": "变形",
                "summary": "Transforms into a bat, centipede, or toad, or back to true form.",
            },
        ],
        "weapons": [
            {
                "weapon_id": "rend",
                "name": "Rend",
                "attack_bonus": 5,
                "damage": [{"formula": "1d4+3", "type": "slashing"}],
                "range": {"normal": 5, "long": 5},
                "kind": "melee",
                "on_hit_metadata": {"applies_condition": "poisoned", "duration": "until_quasit_next_turn_end"},
            }
        ],
    },
    "imp": {
        "name": "Imp",
        "size": "tiny",
        "ac": 13,
        "hp": 21,
        "speed": {"walk": 20, "fly": 40},
        "ability_scores": {"str": 6, "dex": 17, "con": 13, "int": 11, "wis": 12, "cha": 14},
        "ability_mods": {"str": -2, "dex": 3, "con": 1, "int": 0, "wis": 1, "cha": 2},
        "skill_modifiers": {"deception": 4, "insight": 3, "stealth": 5},
        "resistances": ["cold"],
        "immunities": ["fire", "poison"],
        "condition_immunities": ["poisoned"],
        "special_senses": {
            "darkvision": 120,
            "passive_perception": 11,
            "sees_magical_darkness": True,
        },
        "languages": ["common", "infernal"],
        "traits_metadata": [
            {
                "trait_id": "magic_resistance",
                "name_en": "Magic Resistance",
                "name_zh": "魔法抗性",
                "summary": "Advantage on saves against spells and magical effects.",
            }
        ],
        "actions_metadata": [
            {
                "action_id": "invisibility",
                "name_en": "Invisibility",
                "name_zh": "隐形术",
                "summary": "Casts Invisibility on itself.",
            },
            {
                "action_id": "shape_shift",
                "name_en": "Shape-Shift",
                "name_zh": "变形",
                "summary": "Transforms into a rat, raven, or spider, or back to true form.",
            },
        ],
        "weapons": [
            {
                "weapon_id": "sting",
                "name": "Sting",
                "attack_bonus": 5,
                "damage": [
                    {"formula": "1d6+3", "type": "piercing"},
                    {"formula": "2d6", "type": "poison"},
                ],
                "range": {"normal": 5, "long": 5},
                "kind": "melee",
            }
        ],
    },
    "sphinx_of_wonder": {
        "name": "Sphinx of Wonder",
        "size": "tiny",
        "ac": 13,
        "hp": 24,
        "speed": {"walk": 20, "fly": 40},
        "ability_scores": {"str": 6, "dex": 17, "con": 13, "int": 15, "wis": 12, "cha": 11},
        "ability_mods": {"str": -2, "dex": 3, "con": 1, "int": 2, "wis": 1, "cha": 0},
        "skill_modifiers": {"arcana": 4, "religion": 4, "stealth": 5},
        "resistances": ["necrotic", "psychic", "radiant"],
        "special_senses": {"darkvision": 60, "passive_perception": 11},
        "languages": ["celestial", "common"],
        "traits_metadata": [
            {
                "trait_id": "magic_resistance",
                "name_en": "Magic Resistance",
                "name_zh": "魔法抗性",
                "summary": "Advantage on saves against spells and magical effects.",
            }
        ],
        "reactions_metadata": [
            {
                "reaction_id": "burst_of_ingenuity",
                "name_en": "Burst of Ingenuity",
                "name_zh": "灵光乍现",
                "summary": "2/day; add +2 to a nearby creature's ability check or saving throw.",
            }
        ],
        "weapons": [
            {
                "weapon_id": "rend",
                "name": "Rend",
                "attack_bonus": 5,
                "damage": [
                    {"formula": "1d4+3", "type": "slashing"},
                    {"formula": "2d6", "type": "radiant"},
                ],
                "range": {"normal": 5, "long": 5},
                "kind": "melee",
            }
        ],
    },
}


def build_find_familiar_entity(
    *,
    caster: EncounterEntity,
    summon_position: dict[str, int],
    familiar_form: str,
    creature_type: str,
    source_spell_instance_id: str,
) -> EncounterEntity:
    normalized_form = str(familiar_form or "").strip().lower()
    normalized_creature_type = str(creature_type or "").strip().lower()
    if normalized_form not in _FAMILIAR_FORMS:
        raise ValueError("invalid_find_familiar_form")

    template = _FAMILIAR_FORMS[normalized_form]
    speed_template = dict(template["speed"])
    walk_speed = int(speed_template["walk"])
    speed = {"walk": walk_speed, "remaining": walk_speed}
    for key, value in speed_template.items():
        if key == "walk":
            continue
        speed[key] = int(value)

    hp_max = int(template["hp"])

    source_ref = {
        "summoner_entity_id": caster.entity_id,
        "source_spell_id": "find_familiar",
        "source_spell_instance_id": source_spell_instance_id,
        "summon_template": "find_familiar",
        "familiar_form_id": normalized_form,
        "creature_type": normalized_creature_type or None,
        "special_senses": deepcopy(template.get("special_senses", {})),
        "languages": list(template.get("languages", [])),
        "traits_metadata": deepcopy(template.get("traits_metadata", [])),
        "actions_metadata": deepcopy(template.get("actions_metadata", [])),
        "reactions_metadata": deepcopy(template.get("reactions_metadata", [])),
        "condition_immunities": list(template.get("condition_immunities", [])),
    }

    return EncounterEntity(
        entity_id=f"ent_familiar_{uuid4().hex[:12]}",
        name=str(template["name"]),
        side=caster.side,
        category="summon",
        controller=caster.controller,
        position=dict(summon_position),
        hp={"current": hp_max, "max": hp_max, "temp": 0},
        ac=int(template["ac"]),
        speed=speed,
        initiative=caster.initiative,
        size=str(template["size"]),
        proficiency_bonus=int(caster.proficiency_bonus or 0),
        ability_scores=deepcopy(template.get("ability_scores", {})),
        ability_mods=deepcopy(template.get("ability_mods", {})),
        skill_modifiers=deepcopy(template.get("skill_modifiers", {})),
        weapons=deepcopy(template.get("weapons", [])),
        resistances=list(template.get("resistances", [])),
        immunities=list(template.get("immunities", [])),
        vulnerabilities=list(template.get("vulnerabilities", [])),
        source_ref=source_ref,
        combat_flags={
            "dismiss_on_zero_hp": True,
            "dismiss_on_summoner_death": True,
            "familiar": True,
            "independent_initiative_expected": True,
        },
    )
