from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository, SpellDefinitionRepository
from tools.services import AppendEvent, EncounterCastSpell


def build_caster(*, position: Optional[dict[str, int]] = None) -> EncounterEntity:
    position = position or {"x": 2, "y": 2}
    return EncounterEntity(
        entity_id="ent_enemy_mage_001",
        name="Enemy Mage",
        side="enemy",
        category="npc",
        controller="gm",
        position=position,
        hp={"current": 18, "max": 18, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        ability_mods={"int": 3},
        proficiency_bonus=2,
        resources={"spell_slots": {"3": {"max": 2, "remaining": 2}}},
    )


def build_counterspeller(
    *,
    with_counterspell: bool,
    position: Optional[dict[str, int]] = None,
) -> EncounterEntity:
    position = position or {"x": 4, "y": 2}
    spells = [{"spell_id": "counterspell", "name": "Counterspell", "level": 3}] if with_counterspell else []
    resources = {"spell_slots": {"3": {"max": 1, "remaining": 1}}} if with_counterspell else {}
    return EncounterEntity(
        entity_id="ent_ally_counter_001",
        name="Counter Mage",
        side="ally",
        category="pc",
        controller="player",
        position=position,
        hp={"current": 16, "max": 16, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        action_economy={"reaction_used": False},
        spells=spells,
        resources=resources,
    )


def build_encounter(
    *,
    with_counterspell: bool,
    caster_position: Optional[dict[str, int]] = None,
    counterspeller_position: Optional[dict[str, int]] = None,
) -> Encounter:
    caster = build_caster(position=caster_position)
    counterspeller = build_counterspeller(
        with_counterspell=with_counterspell,
        position=counterspeller_position,
    )
    return Encounter(
        encounter_id="enc_spell_reaction_test",
        name="Spell Reaction Test",
        status="active",
        round=1,
        current_entity_id=caster.entity_id,
        turn_order=[caster.entity_id, counterspeller.entity_id],
        entities={caster.entity_id: caster, counterspeller.entity_id: counterspeller},
        map=EncounterMap(
            map_id="map_spell_reaction_test",
            name="Spell Reaction Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


class SpellReactionWindowTests(unittest.TestCase):
    def test_cast_spell_does_not_open_window_when_counterspeller_too_far(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(
                build_encounter(
                    with_counterspell=True,
                    caster_position={"x": 1, "y": 1},
                    counterspeller_position={"x": 20, "y": 1},
                )
            )

            service = EncounterCastSpell(
                encounter_repo,
                AppendEvent(event_repo),
                SpellDefinitionRepository(),
            )

            result = service.execute(
                encounter_id="enc_spell_reaction_test",
                actor_id="ent_enemy_mage_001",
                spell_id="fireball",
                cast_level=3,
            )

            self.assertIn("spell_id", result)
            self.assertNotIn("status", result)
            encounter_repo.close()
            event_repo.close()

    def test_cast_spell_returns_normal_result_when_no_counterspeller(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter(with_counterspell=False))

            service = EncounterCastSpell(
                encounter_repo,
                AppendEvent(event_repo),
                SpellDefinitionRepository(),
            )

            result = service.execute(
                encounter_id="enc_spell_reaction_test",
                actor_id="ent_enemy_mage_001",
                spell_id="fireball",
                cast_level=3,
            )

            self.assertIn("spell_id", result)
            self.assertNotIn("status", result)
            encounter_repo.close()
            event_repo.close()

    def test_cast_spell_returns_waiting_reaction_when_enemy_can_counterspell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter(with_counterspell=True))

            service = EncounterCastSpell(
                encounter_repo,
                AppendEvent(event_repo),
                SpellDefinitionRepository(),
            )

            result = service.execute(
                encounter_id="enc_spell_reaction_test",
                actor_id="ent_enemy_mage_001",
                spell_id="fireball",
                cast_level=3,
            )

            self.assertEqual(result["status"], "waiting_reaction")
            self.assertEqual(result["pending_reaction_window"]["trigger_type"], "spell_declared")
            options = result["pending_reaction_window"]["choice_groups"][0]["options"]
            self.assertEqual(options[0]["reaction_type"], "counterspell")
            self.assertIn("encounter_state", result)
            encounter_repo.close()
            event_repo.close()
