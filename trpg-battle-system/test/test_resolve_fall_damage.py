"""ResolveFallDamage 服务测试。"""

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services.combat.damage.resolve_fall_damage import ResolveFallDamage
from tools.services.events.append_event import AppendEvent
from tools.services.combat.shared.update_hp import UpdateHp


def _build_monk() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_monk_001",
        name="Monk",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=16,
        speed={"walk": 30, "remaining": 30},
        initiative=14,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        turn_effects=[],
        class_features={"monk": {"level": 4}},
    )


def _build_encounter() -> Encounter:
    monk = _build_monk()
    return Encounter(
        encounter_id="enc_fall_test",
        name="Fall Test Encounter",
        status="active",
        round=1,
        current_entity_id=monk.entity_id,
        turn_order=[monk.entity_id],
        entities={monk.entity_id: monk},
        map=EncounterMap(
            map_id="map_fall_test",
            name="Fall Test Map",
            description="A deep pit.",
            width=8,
            height=8,
        ),
    )


def test_resolve_fall_damage_applies_raw_fall_damage_without_slow_fall() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        encounter_repo.save(_build_encounter())

        service = ResolveFallDamage(
            encounter_repository=encounter_repo,
            update_hp=UpdateHp(encounter_repo, AppendEvent(event_repo)),
        )
        result = service.execute(
            encounter_id="enc_fall_test",
            actor_id="ent_monk_001",
            damage=12,
            use_slow_fall=False,
        )

        updated = encounter_repo.get("enc_fall_test")
        assert updated is not None
        assert updated.entities["ent_monk_001"].hp["current"] == 8
        assert result["fall_resolution"]["final_damage"] == 12
        assert result["fall_resolution"]["reduction"] == 0

        encounter_repo.close()
        event_repo.close()


def test_resolve_fall_damage_reduces_damage_by_five_times_monk_level_and_spends_reaction() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        encounter_repo.save(_build_encounter())

        service = ResolveFallDamage(
            encounter_repository=encounter_repo,
            update_hp=UpdateHp(encounter_repo, AppendEvent(event_repo)),
        )
        result = service.execute(
            encounter_id="enc_fall_test",
            actor_id="ent_monk_001",
            damage=18,
            use_slow_fall=True,
        )

        updated = encounter_repo.get("enc_fall_test")
        assert updated is not None
        monk = updated.entities["ent_monk_001"]
        assert monk.action_economy["reaction_used"] is True
        assert monk.hp["current"] == 20
        assert result["fall_resolution"]["reduction"] == 20
        assert result["fall_resolution"]["final_damage"] == 0

        encounter_repo.close()
        event_repo.close()
