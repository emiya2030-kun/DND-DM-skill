from __future__ import annotations

from typing import Any

from tools.models.entity_class_schema import SPELL_PREPARATION_MODES, collect_always_prepared_spells, normalize_class_name
from tools.repositories.spell_definition_repository import SpellDefinitionRepository


class ResolveSpellcastingAccess:
    """统一解析实体当前是否可合法施放某道法术。"""

    def __init__(self, spell_definition_repository: SpellDefinitionRepository | None = None):
        self.spell_definition_repository = spell_definition_repository or SpellDefinitionRepository()

    def execute(self, *, actor: Any, spell_id: str) -> dict[str, Any]:
        known_spell = self._find_known_spell(actor=actor, spell_id=spell_id)
        if known_spell is None:
            return {
                "ok": False,
                "error_code": "spell_not_known",
                "message": f"施法者未掌握 {spell_id}",
                "spell_entry": None,
                "casting_class": None,
                "preparation_mode": None,
                "is_cantrip": False,
                "is_prepared": False,
                "is_always_prepared": False,
                "used_legacy_prepared_fallback": False,
            }

        spell_definition = self.spell_definition_repository.get(spell_id)
        base_level = self._resolve_base_level(spell_definition=spell_definition, known_spell=known_spell)
        is_cantrip = base_level == 0
        casting_class = self._resolve_spellcasting_class(actor=actor, known_spell=known_spell)
        preparation_mode = self._resolve_preparation_mode(actor=actor, casting_class=casting_class)
        class_bucket = self._resolve_class_bucket(actor=actor, casting_class=casting_class)
        prepared_spells = self._normalize_spell_list(
            class_bucket.get("prepared_spells") if isinstance(class_bucket, dict) else None
        )
        always_prepared_spells = set(collect_always_prepared_spells(class_bucket))

        is_prepared = spell_id in prepared_spells
        is_always_prepared = spell_id in always_prepared_spells
        requires_preparation = self._requires_preparation(preparation_mode)
        used_legacy_prepared_fallback = False

        if is_cantrip or not requires_preparation or is_always_prepared or is_prepared:
            return {
                "ok": True,
                "error_code": None,
                "message": None,
                "spell_entry": known_spell,
                "casting_class": casting_class,
                "preparation_mode": preparation_mode,
                "is_cantrip": is_cantrip,
                "is_prepared": is_prepared,
                "is_always_prepared": is_always_prepared,
                "used_legacy_prepared_fallback": used_legacy_prepared_fallback,
            }

        if prepared_spells:
            return {
                "ok": False,
                "error_code": "spell_not_prepared",
                "message": f"施法者当前未准备 {spell_id}",
                "spell_entry": known_spell,
                "casting_class": casting_class,
                "preparation_mode": preparation_mode,
                "is_cantrip": is_cantrip,
                "is_prepared": False,
                "is_always_prepared": False,
                "used_legacy_prepared_fallback": False,
            }

        used_legacy_prepared_fallback = requires_preparation
        return {
            "ok": True,
            "error_code": None,
            "message": None,
            "spell_entry": known_spell,
            "casting_class": casting_class,
            "preparation_mode": preparation_mode,
            "is_cantrip": is_cantrip,
            "is_prepared": False,
            "is_always_prepared": False,
            "used_legacy_prepared_fallback": used_legacy_prepared_fallback,
        }

    def _find_known_spell(self, *, actor: Any, spell_id: str) -> dict[str, Any] | None:
        spells = getattr(actor, "spells", None)
        if not isinstance(spells, list):
            return None
        for spell in spells:
            if isinstance(spell, dict) and spell.get("spell_id") == spell_id:
                return spell
        return None

    def _resolve_base_level(self, *, spell_definition: dict[str, Any] | None, known_spell: dict[str, Any]) -> int:
        if isinstance(spell_definition, dict):
            base = spell_definition.get("base")
            if isinstance(base, dict):
                level = base.get("level")
                if isinstance(level, int) and level >= 0:
                    return level
            level = spell_definition.get("level")
            if isinstance(level, int) and level >= 0:
                return level
        level = known_spell.get("level")
        if isinstance(level, int) and level >= 0:
            return level
        return 0

    def _resolve_spellcasting_class(self, *, actor: Any, known_spell: dict[str, Any]) -> str | None:
        for key in ("casting_class", "source_class"):
            candidate = known_spell.get(key)
            normalized = self._normalize_class_name(candidate)
            if normalized is not None:
                return normalized

        classes = known_spell.get("classes")
        if isinstance(classes, list) and len(classes) == 1:
            normalized = self._normalize_class_name(classes[0])
            if normalized is not None:
                return normalized

        class_features = getattr(actor, "class_features", None)
        if isinstance(class_features, dict):
            recognized = [key for key in class_features.keys() if key in SPELL_PREPARATION_MODES]
            if len(recognized) == 1:
                return recognized[0]

        source_ref = getattr(actor, "source_ref", None)
        if isinstance(source_ref, dict):
            normalized = self._normalize_class_name(source_ref.get("class_name"))
            if normalized is not None:
                return normalized

        normalized = self._normalize_class_name(getattr(actor, "initial_class_name", None))
        if normalized is not None:
            return normalized
        return None

    def _resolve_preparation_mode(self, *, actor: Any, casting_class: str | None) -> str | None:
        if casting_class is None:
            return None
        class_bucket = self._resolve_class_bucket(actor=actor, casting_class=casting_class)
        if isinstance(class_bucket, dict):
            explicit = class_bucket.get("spell_preparation_mode")
            if isinstance(explicit, str) and explicit.strip():
                return explicit.strip().lower()
        return SPELL_PREPARATION_MODES.get(casting_class)

    def _resolve_class_bucket(self, *, actor: Any, casting_class: str | None) -> dict[str, Any]:
        if casting_class is None:
            return {}
        class_features = getattr(actor, "class_features", None)
        if not isinstance(class_features, dict):
            return {}
        bucket = class_features.get(casting_class)
        return bucket if isinstance(bucket, dict) else {}

    def _normalize_spell_list(self, value: Any) -> set[str]:
        if not isinstance(value, list):
            return set()
        normalized: set[str] = set()
        for item in value:
            if isinstance(item, str) and item.strip():
                normalized.add(item.strip())
        return normalized

    def _requires_preparation(self, preparation_mode: str | None) -> bool:
        return preparation_mode not in (None, "", "none")

    def _normalize_class_name(self, value: Any) -> str | None:
        return normalize_class_name(value)
