from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent, UsePactOfTheBlade


def build_actor(*, level: int = 5) -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_warlock_001",
        name="Warlock",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 24, "max": 24, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        ability_mods={"str": 1, "dex": 2, "con": 2, "int": 0, "wis": 0, "cha": 4},
        proficiency_bonus=3,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        weapons=[
            {
                "weapon_id": "longsword",
                "name": "Longsword",
                "category": "martial",
                "kind": "melee",
                "damage": [{"formula": "1d8", "type": "slashing"}],
                "range": {"normal": 5, "long": 5},
                "properties": ["versatile"],
            }
        ],
        class_features={
            "warlock": {
                "level": level,
                "eldritch_invocations": {
                    "selected": [{"invocation_id": "pact_of_the_blade"}]
                },
            }
        },
    )


def build_encounter() -> Encounter:
    actor = build_actor()
    target = EncounterEntity(
        entity_id="ent_target_001",
        name="Bandit",
        side="enemy",
        category="npc",
        controller="gm",
        position={"x": 3, "y": 2},
        hp={"current": 12, "max": 12, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
    )
    return Encounter(
        encounter_id="enc_use_pact_of_the_blade_test",
        name="Use Pact of the Blade Test",
        status="active",
        round=1,
        current_entity_id=actor.entity_id,
        turn_order=[actor.entity_id, target.entity_id],
        entities={actor.entity_id: actor, target.entity_id: target},
        map=EncounterMap(
            map_id="map_use_pact_of_the_blade_test",
            name="Use Pact of the Blade Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


def test_execute_binds_existing_weapon_and_consumes_bonus_action() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        encounter_repo.save(build_encounter())

        result = UsePactOfTheBlade(
            encounter_repo,
            AppendEvent(event_repo),
        ).execute(
            encounter_id="enc_use_pact_of_the_blade_test",
            actor_id="ent_warlock_001",
            weapon_id="longsword",
            damage_type="radiant",
        )

        updated = encounter_repo.get("enc_use_pact_of_the_blade_test")
        assert updated is not None
        warlock = updated.entities["ent_warlock_001"].class_features["warlock"]
        pact = warlock["pact_of_the_blade"]
        assert pact["bound_weapon_id"] == "longsword"
        assert pact["damage_type_override"] == "radiant"
        assert updated.entities["ent_warlock_001"].action_economy["bonus_action_used"] is True
        assert result["class_feature_result"]["pact_of_the_blade"]["bound_weapon_id"] == "longsword"
        encounter_repo.close()
        event_repo.close()
