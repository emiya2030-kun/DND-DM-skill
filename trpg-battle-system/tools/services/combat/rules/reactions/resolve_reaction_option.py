from __future__ import annotations

from typing import Any

from tools.models import Encounter
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.combat.attack.execute_attack import ExecuteAttack
from tools.services.combat.rules.reactions.close_reaction_window import CloseReactionWindow
from tools.services.combat.rules.reactions.definitions.opportunity_attack import ResolveOpportunityAttackReaction
from tools.services.combat.rules.reactions.templates.leave_reach_interrupt import LeaveReachInterrupt
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
    ) -> None:
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.execute_attack = execute_attack
        self.close_reaction_window = close_reaction_window or CloseReactionWindow(encounter_repository)
        self.opportunity_attack_resolver = ResolveOpportunityAttackReaction(
            LeaveReachInterrupt(execute_attack),
        )

    def execute(
        self,
        *,
        encounter_id: str,
        window_id: str,
        group_id: str,
        option_id: str,
        final_total: int,
        dice_rolls: dict[str, Any],
        damage_rolls: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        pending_window = self._get_pending_window_or_raise(encounter, window_id)
        group = self._get_group_or_raise(pending_window, group_id)
        option = self._get_option_or_raise(group, option_id)
        if option.get("status") != "pending":
            raise ValueError("reaction_option_not_pending")

        request_id = str(option["request_id"])
        request = self._get_pending_request_or_raise(encounter, request_id)
        reaction_type = str(request.get("reaction_type") or option.get("reaction_type"))

        attack_result = self._resolve_by_type(
            reaction_type=reaction_type,
            encounter_id=encounter_id,
            request=request,
            final_total=final_total,
            dice_rolls=dice_rolls,
            damage_rolls=damage_rolls,
        )

        encounter = self._get_encounter_or_raise(encounter_id)
        pending_window = self._get_pending_window_or_raise(encounter, window_id)
        group = self._get_group_or_raise(pending_window, group_id)
        option = self._get_option_or_raise(group, option_id)
        request = self._get_pending_request_or_raise(encounter, request_id)

        request["status"] = "resolved"
        group["status"] = "resolved"
        option["status"] = "resolved"
        if group_id not in pending_window.get("resolved_group_ids", []):
            pending_window.setdefault("resolved_group_ids", []).append(group_id)

        self._decline_other_options(encounter, group, option_id)
        self._decline_other_groups_for_actor(encounter, pending_window, group_id, group.get("actor_entity_id"))

        window_result = self.close_reaction_window.execute(encounter=encounter)

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
            "window_id": window_id,
            "group_id": group_id,
            "option_id": option_id,
            "window_status": window_result["window_status"],
            "attack_result": attack_result,
            "event_id": event.event_id,
            "encounter_state": GetEncounterState(self.encounter_repository).execute(encounter_id),
        }

    def _resolve_by_type(
        self,
        *,
        reaction_type: str,
        encounter_id: str,
        request: dict[str, Any],
        final_total: int,
        dice_rolls: dict[str, Any],
        damage_rolls: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        if reaction_type == "opportunity_attack":
            return self.opportunity_attack_resolver.execute(
                encounter_id=encounter_id,
                request=request,
                final_total=final_total,
                dice_rolls=dice_rolls,
                damage_rolls=damage_rolls,
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
