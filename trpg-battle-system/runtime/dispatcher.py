from __future__ import annotations

from typing import Any, Callable

from runtime.context import BattleRuntimeContext

RuntimeHandler = Callable[[BattleRuntimeContext, dict[str, Any]], dict[str, Any]]


def execute_runtime_command(
    context: BattleRuntimeContext,
    *,
    command: str,
    args: dict[str, Any],
    handlers: dict[str, RuntimeHandler] | None = None,
) -> dict[str, Any]:
    available_handlers = handlers or {}
    handler = available_handlers.get(command)
    if handler is None:
        return {
            "ok": False,
            "command": command,
            "error_code": "unknown_command",
            "message": f"unknown runtime command '{command}'",
            "result": None,
            "encounter_state": None,
        }

    try:
        payload = handler(context, args)
    except ValueError as error:
        encounter_id = args.get("encounter_id")
        encounter_state = None
        if encounter_id:
            try:
                encounter_state = context.get_encounter_state(encounter_id)
            except ValueError:
                encounter_state = None
        error_code = getattr(error, "error_code", str(error))
        message = getattr(error, "message", str(error))
        return {
            "ok": False,
            "command": command,
            "error_code": error_code,
            "message": message,
            "rule_context": getattr(error, "rule_context", None),
            "result": None,
            "encounter_state": encounter_state,
        }

    if not isinstance(payload, dict):
        return {
            "ok": False,
            "command": command,
            "error_code": "invalid_handler_response",
            "message": "handler must return a dict payload",
            "result": None,
            "encounter_state": None,
        }

    return {
        "ok": True,
        "command": command,
        "result": payload.get("result"),
        "encounter_state": payload.get("encounter_state"),
    }
