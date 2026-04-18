"""service 总入口。

保留历史顶层导出 API（`from tools.services import X`），
但改为按需加载，避免包初始化时拉起完整 service 依赖链。
"""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "AbilityCheckRequest",
    "AbilityCheckResult",
    "ExecuteAbilityCheck",
    "ResolveAbilityCheck",
    "AppendEvent",
    "EncounterCastSpell",
    "ExecuteSpell",
    "SpellRequest",
    "RetargetMarkedSpell",
    "ExecuteAttack",
    "ExecuteSaveSpell",
    "ExecuteConcentrationCheck",
    "GrantTemporaryHp",
    "UseLayOnHands",
    "UseMagicalCunning",
    "UseContactPatron",
    "UseMysticArcanum",
    "UsePactOfTheBlade",
    "UseNaturesVeil",
    "UseDisengage",
    "UseDodge",
    "UseHelpAttack",
    "UseHelpAbilityCheck",
    "UseGrapple",
    "EscapeGrapple",
    "UseTireless",
    "AttackRollRequest",
    "AttackRollResult",
    "ResolveDamageParts",
    "ResolveReactionRequest",
    "AdvanceTurn",
    "BeginMoveEncounterEntity",
    "ContinuePendingMovement",
    "ResolveForcedMovement",
    "EndTurn",
    "StartTurn",
    "RollInitiativeAndStartEncounter",
    "EncounterService",
    "GetEncounterState",
    "MoveEncounterEntity",
    "RequestConcentrationCheck",
    "ResolveSavingThrow",
    "ResolveConcentrationCheck",
    "ResolveConcentrationResult",
    "SavingThrowRequest",
    "SavingThrowResult",
    "UpdateConditions",
    "UpdateEncounterNotes",
    "UpdateHp",
    "BuildMapNotes",
    "RenderBattlemapPage",
    "RenderBattlemapView",
]

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "AbilityCheckRequest": ("tools.services.checks.ability_check_request", "AbilityCheckRequest"),
    "AbilityCheckResult": ("tools.services.checks.ability_check_result", "AbilityCheckResult"),
    "ExecuteAbilityCheck": ("tools.services.checks.execute_ability_check", "ExecuteAbilityCheck"),
    "ResolveAbilityCheck": ("tools.services.checks.resolve_ability_check", "ResolveAbilityCheck"),
    "AppendEvent": ("tools.services.events.append_event", "AppendEvent"),
    "EncounterCastSpell": ("tools.services.spells.encounter_cast_spell", "EncounterCastSpell"),
    "ExecuteSpell": ("tools.services.spells.execute_spell", "ExecuteSpell"),
    "SpellRequest": ("tools.services.spells.spell_request", "SpellRequest"),
    "RetargetMarkedSpell": ("tools.services.spells.retarget_marked_spell", "RetargetMarkedSpell"),
    "ExecuteAttack": ("tools.services.combat.attack.execute_attack", "ExecuteAttack"),
    "ExecuteSaveSpell": ("tools.services.combat.save_spell.execute_save_spell", "ExecuteSaveSpell"),
    "ExecuteConcentrationCheck": (
        "tools.services.combat.rules.concentration.execute_concentration_check",
        "ExecuteConcentrationCheck",
    ),
    "GrantTemporaryHp": ("tools.services.combat.shared.grant_temporary_hp", "GrantTemporaryHp"),
    "UseLayOnHands": ("tools.services.class_features.paladin.use_lay_on_hands", "UseLayOnHands"),
    "UseMagicalCunning": ("tools.services.class_features.warlock.use_magical_cunning", "UseMagicalCunning"),
    "UseContactPatron": ("tools.services.class_features.warlock.use_contact_patron", "UseContactPatron"),
    "UseMysticArcanum": ("tools.services.class_features.warlock.use_mystic_arcanum", "UseMysticArcanum"),
    "UsePactOfTheBlade": ("tools.services.class_features.warlock.use_pact_of_the_blade", "UsePactOfTheBlade"),
    "UseNaturesVeil": ("tools.services.class_features.ranger.use_natures_veil", "UseNaturesVeil"),
    "UseDisengage": ("tools.services.combat.actions.use_disengage", "UseDisengage"),
    "UseDodge": ("tools.services.combat.actions.use_dodge", "UseDodge"),
    "UseHelpAttack": ("tools.services.combat.actions.use_help_attack", "UseHelpAttack"),
    "UseHelpAbilityCheck": ("tools.services.combat.actions.use_help_ability_check", "UseHelpAbilityCheck"),
    "UseGrapple": ("tools.services.combat.grapple.use_grapple", "UseGrapple"),
    "EscapeGrapple": ("tools.services.combat.grapple.escape_grapple", "EscapeGrapple"),
    "UseTireless": ("tools.services.class_features.ranger.use_tireless", "UseTireless"),
    "AttackRollRequest": ("tools.services.combat.attack.attack_roll_request", "AttackRollRequest"),
    "AttackRollResult": ("tools.services.combat.attack.attack_roll_result", "AttackRollResult"),
    "ResolveDamageParts": ("tools.services.combat.damage", "ResolveDamageParts"),
    "ResolveReactionRequest": ("tools.services.combat.rules.resolve_reaction_request", "ResolveReactionRequest"),
    "AdvanceTurn": ("tools.services.encounter.turns", "AdvanceTurn"),
    "BeginMoveEncounterEntity": ("tools.services.encounter.begin_move_encounter_entity", "BeginMoveEncounterEntity"),
    "ContinuePendingMovement": ("tools.services.encounter.continue_pending_movement", "ContinuePendingMovement"),
    "ResolveForcedMovement": ("tools.services.encounter.resolve_forced_movement", "ResolveForcedMovement"),
    "EndTurn": ("tools.services.encounter.turns", "EndTurn"),
    "StartTurn": ("tools.services.encounter.turns", "StartTurn"),
    "RollInitiativeAndStartEncounter": (
        "tools.services.encounter.roll_initiative_and_start_encounter",
        "RollInitiativeAndStartEncounter",
    ),
    "EncounterService": ("tools.services.encounter.manage_encounter_entities", "EncounterService"),
    "GetEncounterState": ("tools.services.encounter.get_encounter_state", "GetEncounterState"),
    "MoveEncounterEntity": ("tools.services.encounter.move_encounter_entity", "MoveEncounterEntity"),
    "RequestConcentrationCheck": (
        "tools.services.combat.rules.concentration.request_concentration_check",
        "RequestConcentrationCheck",
    ),
    "ResolveSavingThrow": ("tools.services.combat.save_spell.resolve_saving_throw", "ResolveSavingThrow"),
    "ResolveConcentrationCheck": (
        "tools.services.combat.rules.concentration.resolve_concentration_check",
        "ResolveConcentrationCheck",
    ),
    "ResolveConcentrationResult": (
        "tools.services.combat.rules.concentration.resolve_concentration_result",
        "ResolveConcentrationResult",
    ),
    "SavingThrowRequest": ("tools.services.combat.save_spell.saving_throw_request", "SavingThrowRequest"),
    "SavingThrowResult": ("tools.services.combat.save_spell.saving_throw_result", "SavingThrowResult"),
    "UpdateConditions": ("tools.services.combat.shared.update_conditions", "UpdateConditions"),
    "UpdateEncounterNotes": ("tools.services.combat.shared.update_encounter_notes", "UpdateEncounterNotes"),
    "UpdateHp": ("tools.services.combat.shared.update_hp", "UpdateHp"),
    "BuildMapNotes": ("tools.services.map.build_map_notes", "BuildMapNotes"),
    "RenderBattlemapPage": ("tools.services.map.render_battlemap_page", "RenderBattlemapPage"),
    "RenderBattlemapView": ("tools.services.map.render_battlemap_view", "RenderBattlemapView"),
}


def __getattr__(name: str):
    export = _LAZY_EXPORTS.get(name)
    if export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_path, attr_name = export
    value = getattr(import_module(module_path), attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__))
