"""施法资格解析测试。"""

import sys
import tempfile
import unittest
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import EncounterEntity
from tools.repositories import SpellDefinitionRepository
from tools.services.spells.resolve_spellcasting_access import ResolveSpellcastingAccess


def build_bard() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_bard_001",
        name="Lyra",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 1, "y": 1},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        source_ref={"class_name": "bard"},
        class_features={
            "bard": {
                "level": 10,
                "prepared_spells": ["healing_word", "dissonant_whispers"],
                "words_of_creation": {
                    "always_prepared_spells": ["power_word_heal", "power_word_kill"],
                },
            }
        },
        spells=[
            {"spell_id": "healing_word", "name": "Healing Word", "level": 1, "casting_class": "bard"},
            {"spell_id": "dissonant_whispers", "name": "Dissonant Whispers", "level": 1, "casting_class": "bard"},
            {"spell_id": "power_word_heal", "name": "Power Word Heal", "level": 9, "casting_class": "bard"},
            {"spell_id": "fire_bolt", "name": "Fire Bolt", "level": 0, "casting_class": "bard"},
        ],
    )


class ResolveSpellcastingAccessTests(unittest.TestCase):
    def _build_service(self, definitions: dict[str, object]) -> ResolveSpellcastingAccess:
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        path = Path(tmp_dir.name) / "spell_definitions.json"
        path.write_text(json.dumps({"spell_definitions": definitions}), encoding="utf-8")
        return ResolveSpellcastingAccess(SpellDefinitionRepository(path))

    def test_execute_returns_not_prepared_for_missing_prepared_spell(self) -> None:
        actor = build_bard()
        service = self._build_service(
            {
                "heroism": {
                    "id": "heroism",
                    "name": "Heroism",
                    "level": 1,
                    "base": {"level": 1},
                }
            }
        )
        actor.spells.append({"spell_id": "heroism", "name": "Heroism", "level": 1, "casting_class": "bard"})

        result = service.execute(actor=actor, spell_id="heroism")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "spell_not_prepared")
        self.assertFalse(result["is_prepared"])
        self.assertFalse(result["is_always_prepared"])

    def test_execute_allows_nested_always_prepared_spell(self) -> None:
        actor = build_bard()
        service = self._build_service(
            {
                "power_word_heal": {
                    "id": "power_word_heal",
                    "name": "Power Word Heal",
                    "level": 9,
                    "base": {"level": 9},
                }
            }
        )

        result = service.execute(actor=actor, spell_id="power_word_heal")

        self.assertTrue(result["ok"])
        self.assertTrue(result["is_always_prepared"])
        self.assertFalse(result["used_legacy_prepared_fallback"])

    def test_execute_allows_cantrip_without_prepared_entry(self) -> None:
        actor = build_bard()
        service = self._build_service(
            {
                "fire_bolt": {
                    "id": "fire_bolt",
                    "name": "Fire Bolt",
                    "level": 0,
                    "base": {"level": 0},
                }
            }
        )

        result = service.execute(actor=actor, spell_id="fire_bolt")

        self.assertTrue(result["ok"])
        self.assertTrue(result["is_cantrip"])

    def test_execute_uses_legacy_fallback_when_prepared_spells_missing(self) -> None:
        actor = build_bard()
        actor.class_features["bard"].pop("prepared_spells", None)
        service = self._build_service(
            {
                "dissonant_whispers": {
                    "id": "dissonant_whispers",
                    "name": "Dissonant Whispers",
                    "level": 1,
                    "base": {"level": 1},
                }
            }
        )

        result = service.execute(actor=actor, spell_id="dissonant_whispers")

        self.assertTrue(result["ok"])
        self.assertTrue(result["used_legacy_prepared_fallback"])

    def test_execute_uses_model_normalized_prepared_spells_when_loading_legacy_entity(self) -> None:
        legacy_actor = build_bard().to_dict()
        legacy_actor["class_features"] = {}
        legacy_actor["source_ref"]["class_name"] = "bard"
        actor = EncounterEntity.from_dict(legacy_actor)
        service = self._build_service(
            {
                "dissonant_whispers": {
                    "id": "dissonant_whispers",
                    "name": "Dissonant Whispers",
                    "level": 1,
                    "base": {"level": 1},
                }
            }
        )

        result = service.execute(actor=actor, spell_id="dissonant_whispers")

        self.assertTrue(result["ok"])
        self.assertFalse(result["used_legacy_prepared_fallback"])
        self.assertTrue(result["is_prepared"])


if __name__ == "__main__":
    unittest.main()
