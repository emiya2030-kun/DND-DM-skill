from __future__ import annotations

from collections.abc import Iterable

from .condition_parser import Condition, parse_condition


class ConditionRuntime:
    def __init__(self, conditions: Iterable[str] | None):
        raw_conditions = conditions or ()
        self._conditions: tuple[Condition, ...] = tuple(parse_condition(item) for item in raw_conditions)

    def has(self, name: str) -> bool:
        return any(condition.name == name for condition in self._conditions)

    def has_from_source(self, name: str, source: str) -> bool:
        return any(condition.name == name and condition.source == source for condition in self._conditions)

    def exhaustion_level(self) -> int:
        for condition in self._conditions:
            if condition.name == "exhaustion":
                return condition.level or 0
        return 0

    def get_d20_penalty(self) -> int:
        return self.exhaustion_level() * 2

    def get_speed_penalty_feet(self) -> int:
        return self.exhaustion_level() * 5

    def sources_for(self, name: str) -> tuple[str, ...]:
        seen: list[str] = []
        for condition in self._conditions:
            if condition.name == name and condition.source:
                if condition.source not in seen:
                    seen.append(condition.source)
        return tuple(seen)
