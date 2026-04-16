from __future__ import annotations

from typing import Any

from tools.models import Encounter
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.combat.attack.execute_attack import ExecuteAttack
from tools.services.combat.rules.reactions.resolve_reaction_option import ResolveReactionOption
from tools.services.events.append_event import AppendEvent


class ResolveReactionRequest:
    """兼容旧入参的 reaction request 解析器。"""

    def __init__(
        self,
        encounter_repository: EncounterRepository,
        append_event: AppendEvent,
        execute_attack: ExecuteAttack,
    ):
        self.encounter_repository = encounter_repository
        self.resolve_option = ResolveReactionOption(encounter_repository, append_event, execute_attack)

    def execute(
        self,
        *,
        encounter_id: str,
        request_id: str,
        final_total: int,
        dice_rolls: dict[str, Any],
        damage_rolls: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        request = self._get_pending_request_or_raise(encounter, request_id)
        mapping = self._find_option_mapping(encounter, request_id)
        if mapping is None:
            raise ValueError("reaction_option_not_found")

        return self.resolve_option.execute(
            encounter_id=encounter_id,
            window_id=mapping["window_id"],
            group_id=mapping["group_id"],
            option_id=mapping["option_id"],
            final_total=final_total,
            dice_rolls=dice_rolls,
            damage_rolls=damage_rolls,
        )

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_pending_request_or_raise(self, encounter: Encounter, request_id: str) -> dict[str, Any]:
        for request in encounter.reaction_requests:
            if request.get("request_id") == request_id:
                if request.get("status") != "pending":
                    raise ValueError("reaction_request_not_pending")
                return request
        raise ValueError(f"reaction_request '{request_id}' not found")

    def _find_option_mapping(self, encounter: Encounter, request_id: str) -> dict[str, str] | None:
        pending = encounter.pending_reaction_window
        if not isinstance(pending, dict):
            return None
        for group in pending.get("choice_groups", []):
            for option in group.get("options", []):
                if option.get("request_id") == request_id:
                    return {
                        "window_id": str(pending.get("window_id")),
                        "group_id": str(group.get("group_id")),
                        "option_id": str(option.get("option_id")),
                    }
        return None
