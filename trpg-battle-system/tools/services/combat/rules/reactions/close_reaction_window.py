from __future__ import annotations

from typing import Any

from tools.models import Encounter


class CloseReactionWindow:
    """Close or keep the pending reaction window based on remaining options."""

    def __init__(self, encounter_repository) -> None:
        self.encounter_repository = encounter_repository

    def execute(self, *, encounter: Encounter) -> dict[str, Any]:
        pending = encounter.pending_reaction_window
        if not isinstance(pending, dict):
            return {"window_status": "no_window", "pending_reaction_window": None}

        if self._has_pending_options(pending):
            pending["status"] = "waiting_reaction"
            encounter.pending_reaction_window = pending
            self.encounter_repository.save(encounter)
            return {"window_status": "waiting_reaction", "pending_reaction_window": pending}

        encounter.pending_reaction_window = None
        self.encounter_repository.save(encounter)
        return {"window_status": "closed", "pending_reaction_window": None}

    def _has_pending_options(self, pending: dict[str, Any]) -> bool:
        groups = pending.get("choice_groups", [])
        for group in groups:
            if group.get("status") != "pending":
                continue
            for option in group.get("options", []):
                if option.get("status") == "pending":
                    return True
        return False
