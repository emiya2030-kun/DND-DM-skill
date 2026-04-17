"""施法相关 service 顶层导出。

这里也改成按需加载，避免在只导入某个子模块时把完整施法链提前拉起，
从而触发 `SavingThrowResult -> encounter.turns -> spells -> ExecuteSpell`
这种包级循环引用。
"""

from __future__ import annotations

from importlib import import_module

__all__ = ["SpellRequest", "ExecuteSpell"]

_LAZY_EXPORTS = {
    "SpellRequest": ("tools.services.spells.spell_request", "SpellRequest"),
    "ExecuteSpell": ("tools.services.spells.execute_spell", "ExecuteSpell"),
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
