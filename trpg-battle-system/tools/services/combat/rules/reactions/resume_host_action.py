from __future__ import annotations

from typing import Any


class ResumeHostAction:
    """Placeholder for host action resume logic (Task 4 minimal stub)."""

    def execute(self, *, encounter_id: str, pending_window: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "status": "not_implemented",
            "encounter_id": encounter_id,
            "host_action_result": None,
            "pending_window": pending_window,
        }
