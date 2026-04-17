from __future__ import annotations

from importlib import import_module

__all__ = [
    "AbilityCheckRequest",
    "AbilityCheckResult",
    "ExecuteAbilityCheck",
    "ResolveAbilityCheck",
]

_LAZY_EXPORTS = {
    "AbilityCheckRequest": ("tools.services.checks.ability_check_request", "AbilityCheckRequest"),
    "AbilityCheckResult": ("tools.services.checks.ability_check_result", "AbilityCheckResult"),
    "ExecuteAbilityCheck": ("tools.services.checks.execute_ability_check", "ExecuteAbilityCheck"),
    "ResolveAbilityCheck": ("tools.services.checks.resolve_ability_check", "ResolveAbilityCheck"),
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
