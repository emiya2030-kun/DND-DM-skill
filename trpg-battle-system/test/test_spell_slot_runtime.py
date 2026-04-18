from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import EncounterEntity
from tools.services.class_features.shared.spell_slots import (
    add_created_spell_slot,
    clear_created_spell_slots,
    ensure_spell_slots_runtime,
)


def build_entity() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_spellcaster_001",
        name="Spellcaster",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 1, "y": 1},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
    )


def test_ensure_spell_slots_runtime_builds_multiclass_caster_slots() -> None:
    entity = build_entity()
    entity.class_features = {
        "ranger": {"level": 4},
        "sorcerer": {"level": 3},
    }

    result = ensure_spell_slots_runtime(entity)

    assert result["multiclass_caster_level"] == 5
    assert entity.resources["spell_slots"] == {
        "1": {"max": 4, "remaining": 4},
        "2": {"max": 3, "remaining": 3},
        "3": {"max": 2, "remaining": 2},
    }


def test_ensure_spell_slots_runtime_builds_third_caster_slots() -> None:
    entity = build_entity()
    entity.class_features = {
        "fighter": {"level": 3, "subclass_id": "eldritch_knight"},
        "rogue": {"level": 3, "subclass_id": "arcane_trickster"},
    }

    result = ensure_spell_slots_runtime(entity)

    assert result["multiclass_caster_level"] == 2
    assert entity.resources["spell_slots"] == {
        "1": {"max": 3, "remaining": 3},
    }


def test_ensure_spell_slots_runtime_preserves_existing_remaining_counts() -> None:
    entity = build_entity()
    entity.class_features = {
        "paladin": {"level": 5},
        "sorcerer": {"level": 3},
    }
    entity.resources = {
        "spell_slots": {
            "1": {"max": 99, "remaining": 1},
            "2": {"max": 99, "remaining": 0},
            "3": {"max": 99, "remaining": 2},
            "9": {"max": 1, "remaining": 1},
        }
    }

    result = ensure_spell_slots_runtime(entity)

    assert result["multiclass_caster_level"] == 6
    assert entity.resources["spell_slots"] == {
        "1": {"max": 4, "remaining": 1},
        "2": {"max": 3, "remaining": 0},
        "3": {"max": 3, "remaining": 2},
    }


def test_ensure_spell_slots_runtime_builds_warlock_pact_magic_slots() -> None:
    entity = build_entity()
    entity.class_features = {
        "warlock": {"level": 5},
    }

    result = ensure_spell_slots_runtime(entity)

    assert result["multiclass_caster_level"] == 0
    assert result["spell_slots"] == {}
    assert result["pact_magic_slots"] == {
        "slot_level": 3,
        "max": 2,
        "remaining": 2,
    }
    assert entity.resources["pact_magic_slots"] == {
        "slot_level": 3,
        "max": 2,
        "remaining": 2,
    }


def test_ensure_spell_slots_runtime_builds_shared_and_pact_slots_together() -> None:
    entity = build_entity()
    entity.class_features = {
        "paladin": {"level": 2},
        "warlock": {"level": 3},
    }
    entity.resources = {
        "spell_slots": {"1": {"max": 99, "remaining": 1}},
        "pact_magic_slots": {"slot_level": 99, "max": 99, "remaining": 1},
    }

    result = ensure_spell_slots_runtime(entity)

    assert result["multiclass_caster_level"] == 1
    assert entity.resources["spell_slots"] == {
        "1": {"max": 2, "remaining": 1},
    }
    assert entity.resources["pact_magic_slots"] == {
        "slot_level": 2,
        "max": 2,
        "remaining": 1,
    }


def test_add_created_spell_slot_increments_slot_pool_and_runtime_counter() -> None:
    entity = build_entity()
    entity.class_features = {"sorcerer": {"level": 5}}

    ensure_spell_slots_runtime(entity)
    result = add_created_spell_slot(entity, slot_level=3, amount=1)

    assert result["remaining_after"] == 3
    assert entity.resources["spell_slots"]["3"]["remaining"] == 3
    assert entity.class_features["sorcerer"]["created_spell_slots"]["3"] == 1


def test_clear_created_spell_slots_restores_original_remaining_values() -> None:
    entity = build_entity()
    entity.class_features = {"sorcerer": {"level": 5}}

    ensure_spell_slots_runtime(entity)
    add_created_spell_slot(entity, slot_level=1, amount=1)
    add_created_spell_slot(entity, slot_level=2, amount=1)

    cleared = clear_created_spell_slots(entity)

    assert cleared == {"1": 1, "2": 1}
    assert entity.resources["spell_slots"]["1"]["remaining"] == entity.resources["spell_slots"]["1"]["max"]
    assert entity.resources["spell_slots"]["2"]["remaining"] == entity.resources["spell_slots"]["2"]["max"]
    assert entity.class_features["sorcerer"]["created_spell_slots"]["1"] == 0
    assert entity.class_features["sorcerer"]["created_spell_slots"]["2"] == 0
