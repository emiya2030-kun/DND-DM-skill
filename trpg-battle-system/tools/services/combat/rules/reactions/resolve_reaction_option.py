from __future__ import annotations

from typing import Any

from tools.models import Encounter
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.combat.attack.execute_attack import ExecuteAttack
from tools.services.combat.rules.reactions.close_reaction_window import CloseReactionWindow
from tools.services.combat.rules.reactions.definitions.counterspell import ResolveCounterspellReaction
from tools.services.combat.rules.reactions.definitions.deflect_attacks import ResolveDeflectAttacksReaction
from tools.services.combat.rules.reactions.definitions.indomitable import ResolveIndomitableReaction
from tools.services.combat.rules.reactions.definitions.interception import ResolveInterceptionReaction
from tools.services.combat.rules.reactions.definitions.opportunity_attack import ResolveOpportunityAttackReaction
from tools.services.combat.rules.reactions.definitions.protection import ResolveProtectionReaction
from tools.services.combat.rules.reactions.definitions.shield import ResolveShieldReaction
from tools.services.combat.rules.reactions.definitions.tactical_mind import ResolveTacticalMindReaction
from tools.services.combat.rules.reactions.definitions.uncanny_dodge import ResolveUncannyDodgeReaction
from tools.services.combat.rules.reactions.resume_host_action import ResumeHostAction
from tools.services.combat.rules.reactions.templates.cast_interrupt_contest import CastInterruptContest
from tools.services.combat.rules.reactions.templates.leave_reach_interrupt import LeaveReachInterrupt
from tools.services.combat.rules.reactions.templates.targeted_defense_rewrite import TargetedDefenseRewrite
from tools.services.spells.encounter_cast_spell import EncounterCastSpell
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent


class ResolveReactionOption:
    """Resolve a reaction option selected from a pending reaction window."""

    def __init__(
        self,
        encounter_repository: EncounterRepository,
        append_event: AppendEvent,
        execute_attack: ExecuteAttack,
        close_reaction_window: CloseReactionWindow | None = None,
        encounter_cast_spell: EncounterCastSpell | None = None,
        resume_host_action: ResumeHostAction | None = None,
    ) -> None:
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.execute_attack = execute_attack
        self.close_reaction_window = close_reaction_window or CloseReactionWindow(encounter_repository)
        self.opportunity_attack_resolver = ResolveOpportunityAttackReaction(
            LeaveReachInterrupt(execute_attack),
        )
        self.shield_resolver = ResolveShieldReaction(
            TargetedDefenseRewrite(encounter_repository),
        )
        self.counterspell_resolver = ResolveCounterspellReaction(
            CastInterruptContest(encounter_repository),
        )
        self.deflect_attacks_resolver = ResolveDeflectAttacksReaction(encounter_repository)
        self.uncanny_dodge_resolver = ResolveUncannyDodgeReaction(encounter_repository)
        self.interception_resolver = ResolveInterceptionReaction(encounter_repository)
        self.protection_resolver = ResolveProtectionReaction(encounter_repository)
        self.indomitable_resolver = ResolveIndomitableReaction(encounter_repository)
        self.tactical_mind_resolver = ResolveTacticalMindReaction(encounter_repository)
        encounter_cast_spell = encounter_cast_spell or EncounterCastSpell(encounter_repository, append_event)
        self.resume_host_action = resume_host_action or ResumeHostAction(
            encounter_repository=encounter_repository,
            append_event=append_event,
            execute_attack=execute_attack,
            encounter_cast_spell=encounter_cast_spell,
        )

    def execute(
        self,
        *,
        encounter_id: str,
        window_id: str,
        group_id: str,
        option_id: str,
        final_total: int | None,
        dice_rolls: dict[str, Any] | None,
        damage_rolls: list[dict[str, Any]] | None = None,
        option_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        pending_window = self._get_pending_window_or_raise(encounter, window_id)
        group = self._get_group_or_raise(pending_window, group_id)
        option = self._get_option_or_raise(group, option_id)
        return self._execute_with_mapping(
            encounter_id=encounter_id,
            mapping={
                "window_id": window_id,
                "group_id": group_id,
                "option_id": option_id,
                "pending_window": pending_window,
                "group": group,
                "option": option,
                "request_id": str(option["request_id"]),
                "persist_window": True,
            },
            final_total=final_total,
            dice_rolls=dice_rolls,
            damage_rolls=damage_rolls,
            option_payload=option_payload,
        )

    def _execute_with_mapping(
        self,
        *,
        encounter_id: str,
        mapping: dict[str, Any],
        final_total: int | None,
        dice_rolls: dict[str, Any] | None,
        damage_rolls: list[dict[str, Any]] | None,
        option_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        if mapping.get("persist_window", True):
            pending_window = self._get_pending_window_or_raise(encounter, mapping["window_id"])
            group = self._get_group_or_raise(pending_window, mapping["group_id"])
            option = self._get_option_or_raise(group, mapping["option_id"])
        else:
            pending_window = mapping["pending_window"]
            group = mapping["group"]
            option = mapping["option"]
        request_id = mapping["request_id"]
        if option.get("status") != "pending":
            raise ValueError("reaction_option_not_pending")

        request = self._get_pending_request_or_raise(encounter, request_id)
        reaction_type = str(request.get("reaction_type") or option.get("reaction_type"))

        resolution = self._resolve_by_type(
            reaction_type=reaction_type,
            encounter_id=encounter.encounter_id,
            request=request,
            final_total=final_total,
            dice_rolls=dice_rolls,
            damage_rolls=damage_rolls,
            option_payload=option_payload,
        )

        resolution_mode = resolution.get("resolution_mode")
        if not resolution_mode:
            raise ValueError("reaction_resolution_missing")
        reaction_result = resolution.get("reaction_result")

        encounter = self._get_encounter_or_raise(encounter_id)
        request = self._get_pending_request_or_raise(encounter, request_id)
        if mapping.get("persist_window", True):
            pending_window = self._get_pending_window_or_raise(encounter, mapping["window_id"])
            group = self._get_group_or_raise(pending_window, mapping["group_id"])
            option = self._get_option_or_raise(group, mapping["option_id"])

        request["status"] = "resolved"
        group["status"] = "resolved"
        option["status"] = "resolved"
        if mapping.get("persist_window", True):
            if mapping["group_id"] not in pending_window.get("resolved_group_ids", []):
                pending_window.setdefault("resolved_group_ids", []).append(mapping["group_id"])

        self._decline_other_options(encounter, group, mapping["option_id"])
        self._decline_other_groups_for_actor(
            encounter,
            pending_window,
            mapping["group_id"],
            group.get("actor_entity_id"),
        )

        if mapping.get("persist_window", True):
            window_result = self.close_reaction_window.execute(encounter=encounter)
        else:
            self.encounter_repository.save(encounter)
            window_result = {"window_status": "closed", "pending_reaction_window": None}

        host_action_result = None
        if resolution_mode == "rewrite_host_action" and window_result["window_status"] == "closed":
            host_action_result = self.resume_host_action.execute(
                encounter_id=encounter_id,
                pending_window=pending_window,
                reaction_result=reaction_result,
            )["host_action_result"]

        event = self.append_event.execute(
            encounter_id=encounter_id,
            round=encounter.round,
            event_type="reaction_request_resolved",
            actor_entity_id=request.get("actor_entity_id"),
            target_entity_id=request.get("target_entity_id"),
            payload={
                "request_id": request_id,
                "reaction_type": reaction_type,
                "weapon_id": request.get("payload", {}).get("weapon_id"),
            },
        )

        return {
            "encounter_id": encounter_id,
            "request_id": request_id,
            "reaction_type": reaction_type,
            "window_id": mapping["window_id"],
            "group_id": mapping["group_id"],
            "option_id": mapping["option_id"],
            "window_status": window_result["window_status"],
            "resolution_mode": resolution_mode,
            "reaction_result": reaction_result,
            "attack_result": reaction_result,
            "host_action_result": host_action_result,
            "event_id": event.event_id,
            "encounter_state": GetEncounterState(self.encounter_repository).execute(encounter_id),
        }

    def _execute_compat_request(
        self,
        *,
        encounter_id: str,
        request_id: str,
        final_total: int | None,
        dice_rolls: dict[str, Any] | None,
        damage_rolls: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        request = self._get_pending_request_or_raise(encounter, request_id)
        reaction_type = request.get("reaction_type")
        window_id = f"compat_window_{request_id}"
        group_id = f"compat_group_{request.get('actor_entity_id')}"
        option_id = f"compat_option_{request_id}"
        pending_window = {
            "window_id": window_id,
            "status": "waiting_reaction",
            "trigger_event_id": request.get("trigger_event_id"),
            "trigger_type": request.get("trigger_type"),
            "blocking": True,
            "host_action_type": None,
            "host_action_id": None,
            "host_action_snapshot": {},
            "choice_groups": [
                {
                    "group_id": group_id,
                    "actor_entity_id": request.get("actor_entity_id"),
                    "ask_player": bool(request.get("ask_player", True)),
                    "status": "pending",
                    "resource_pool": "reaction",
                    "group_priority": 100,
                    "trigger_sequence": 1,
                    "relationship_rank": 1,
                    "tie_break_key": request.get("actor_entity_id"),
                    "options": [
                        {
                            "option_id": option_id,
                            "reaction_type": reaction_type,
                            "template_type": request.get("template_type"),
                            "request_id": request_id,
                            "label": reaction_type,
                            "status": "pending",
                        }
                    ],
                }
            ],
            "resolved_group_ids": [],
        }
        group = pending_window["choice_groups"][0]
        option = group["options"][0]
        return self._execute_with_mapping(
            encounter_id=encounter_id,
            mapping={
                "window_id": window_id,
                "group_id": group_id,
                "option_id": option_id,
                "pending_window": pending_window,
                "group": group,
                "option": option,
                "request_id": request_id,
                "persist_window": False,
            },
            final_total=final_total,
            dice_rolls=dice_rolls,
            damage_rolls=damage_rolls,
            option_payload=None,
        )

    def _resolve_by_type(
        self,
        *,
        reaction_type: str,
        encounter_id: str,
        request: dict[str, Any],
        final_total: int | None,
        dice_rolls: dict[str, Any] | None,
        damage_rolls: list[dict[str, Any]] | None,
        option_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if reaction_type == "opportunity_attack":
            return self.opportunity_attack_resolver.execute(
                encounter_id=encounter_id,
                request=request,
                final_total=final_total,
                dice_rolls=dice_rolls,
                damage_rolls=damage_rolls,
            )
        if reaction_type == "shield":
            return self.shield_resolver.execute(
                encounter_id=encounter_id,
                request=request,
                final_total=final_total,
                dice_rolls=dice_rolls,
            )
        if reaction_type == "deflect_attacks":
            return self.deflect_attacks_resolver.execute(
                encounter_id=encounter_id,
                request=request,
                option_payload=option_payload,
            )
        if reaction_type == "uncanny_dodge":
            return self.uncanny_dodge_resolver.execute(
                encounter_id=encounter_id,
                request=request,
                option_payload=option_payload,
            )
        if reaction_type == "interception":
            return self.interception_resolver.execute(
                encounter_id=encounter_id,
                request=request,
                option_payload=option_payload,
            )
        if reaction_type == "protection":
            return self.protection_resolver.execute(
                encounter_id=encounter_id,
                request=request,
                option_payload=option_payload,
            )
        if reaction_type == "counterspell":
            return self.counterspell_resolver.execute(
                encounter_id=encounter_id,
                request=request,
                final_total=final_total,
                dice_rolls=dice_rolls,
            )
        if reaction_type == "indomitable":
            return self.indomitable_resolver.execute(
                encounter_id=encounter_id,
                request=request,
                final_total=final_total,
                dice_rolls=dice_rolls,
            )
        if reaction_type == "tactical_mind":
            return self.tactical_mind_resolver.execute(
                encounter_id=encounter_id,
                request=request,
                final_total=final_total,
                dice_rolls=dice_rolls,
            )
        raise ValueError("unsupported_reaction_type")

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_pending_window_or_raise(self, encounter: Encounter, window_id: str) -> dict[str, Any]:
        pending = encounter.pending_reaction_window
        if not isinstance(pending, dict):
            raise ValueError("reaction_window_not_found")
        if str(pending.get("window_id")) != window_id:
            raise ValueError("reaction_window_mismatch")
        return pending

    def _get_group_or_raise(self, pending_window: dict[str, Any], group_id: str) -> dict[str, Any]:
        for group in pending_window.get("choice_groups", []):
            if group.get("group_id") == group_id:
                return group
        raise ValueError("reaction_group_not_found")

    def _get_option_or_raise(self, group: dict[str, Any], option_id: str) -> dict[str, Any]:
        for option in group.get("options", []):
            if option.get("option_id") == option_id:
                return option
        raise ValueError("reaction_option_not_found")

    def _get_pending_request_or_raise(self, encounter: Encounter, request_id: str) -> dict[str, Any]:
        for request in encounter.reaction_requests:
            if request.get("request_id") == request_id:
                if request.get("status") != "pending":
                    raise ValueError("reaction_request_not_pending")
                return request
        raise ValueError(f"reaction_request '{request_id}' not found")

    def _decline_other_options(self, encounter: Encounter, group: dict[str, Any], option_id: str) -> None:
        for option in group.get("options", []):
            if option.get("option_id") == option_id:
                continue
            if option.get("status") != "pending":
                continue
            option["status"] = "declined"
            request_id = option.get("request_id")
            if request_id:
                self._decline_request(encounter, str(request_id))

    def _decline_other_groups_for_actor(
        self,
        encounter: Encounter,
        pending_window: dict[str, Any],
        group_id: str,
        actor_entity_id: str | None,
    ) -> None:
        if actor_entity_id is None:
            return
        for group in pending_window.get("choice_groups", []):
            if group.get("group_id") == group_id:
                continue
            if group.get("actor_entity_id") != actor_entity_id:
                continue
            if group.get("status") != "pending":
                continue
            group["status"] = "resolved"
            for option in group.get("options", []):
                if option.get("status") == "pending":
                    option["status"] = "declined"
                    request_id = option.get("request_id")
                    if request_id:
                        self._decline_request(encounter, str(request_id))

    def _decline_request(self, encounter: Encounter, request_id: str) -> None:
        for request in encounter.reaction_requests:
            if request.get("request_id") == request_id and request.get("status") == "pending":
                request["status"] = "declined"
                return
