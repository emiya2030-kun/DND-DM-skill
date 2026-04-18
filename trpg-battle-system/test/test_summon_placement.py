from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.services.spells.summons.placement import resolve_summon_target_point


def build_caster() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_caster_001",
        name="Caster",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        size="medium",
    )


def build_blocker() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_blocker_001",
        name="Blocker",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 3, "y": 2},
        hp={"current": 10, "max": 10, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        size="medium",
    )


def build_encounter(*entities: EncounterEntity) -> Encounter:
    entity_map = {entity.entity_id: entity for entity in entities}
    turn_order = [entity.entity_id for entity in entities]
    return Encounter(
        encounter_id="enc_summon_placement_test",
        name="Summon Placement Test",
        status="active",
        round=1,
        current_entity_id=entities[0].entity_id if entities else None,
        turn_order=turn_order,
        entities=entity_map,
        map=EncounterMap(
            map_id="map_summon_placement_test",
            name="Summon Placement Map",
            description="A compact arena.",
            width=10,
            height=10,
        ),
    )


def test_resolve_summon_target_point_defaults_to_adjacent_open_space() -> None:
    caster = build_caster()
    blocker = build_blocker()
    encounter = build_encounter(caster, blocker)

    result = resolve_summon_target_point(
        encounter=encounter,
        caster=caster,
        summon_size="large",
        range_feet=30,
        target_point=None,
        default_mode="adjacent_open_space",
        out_of_range_error_code="find_steed_target_point_out_of_range",
        missing_target_point_error_code="find_steed_requires_target_point",
    )

    assert result == {"x": 0, "y": 2, "anchor": "cell_center"}


def test_resolve_summon_target_point_rejects_point_out_of_range() -> None:
    caster = build_caster()
    encounter = build_encounter(caster)

    with pytest.raises(ValueError, match="find_steed_target_point_out_of_range"):
        resolve_summon_target_point(
            encounter=encounter,
            caster=caster,
            summon_size="large",
            range_feet=30,
            target_point={"x": 9, "y": 2, "anchor": "cell_center"},
            default_mode="adjacent_open_space",
            out_of_range_error_code="find_steed_target_point_out_of_range",
            missing_target_point_error_code="find_steed_requires_target_point",
        )
