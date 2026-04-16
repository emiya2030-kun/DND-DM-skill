from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from tools.models import EncounterEntity


def build_turn_effect_instance(
    *,
    spell_definition: dict[str, Any],
    effect_template_id: str,
    caster: EncounterEntity,
    save_dc: int | None = None,
) -> dict[str, Any]:
    effect_templates = spell_definition.get("effect_templates")
    if not isinstance(effect_templates, dict):
        raise ValueError("spell_definition.effect_templates must be a dict")

    template = effect_templates.get(effect_template_id)
    if not isinstance(template, dict):
        raise ValueError(f"effect template '{effect_template_id}' not found")

    instance = deepcopy(template)
    instance["effect_id"] = f"effect_{uuid4().hex[:12]}"
    instance["source_entity_id"] = caster.entity_id
    instance["source_name"] = caster.name
    instance["source_type"] = "spell"
    instance["source_ref"] = str(spell_definition.get("id") or spell_definition.get("spell_id") or effect_template_id)

    save_config = instance.get("save")
    if isinstance(save_config, dict):
        dc_mode = save_config.get("dc_mode")
        if dc_mode not in {None, "caster_spell_dc"}:
            raise ValueError("effect_template.save.dc_mode must be 'caster_spell_dc' when provided")
        if save_dc is None:
            raise ValueError("save_dc is required when effect template defines a save")
        save_config["dc"] = save_dc
        save_config.pop("dc_mode", None)
    return instance
