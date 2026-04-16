from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Condition:
    raw: str
    name: str
    source: str | None = None
    level: int | None = None


def _require_nonempty(value: str, context: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{context} must be non-empty")
    return stripped


def parse_condition(raw: str) -> Condition:
    if raw is None or not raw.strip():
        raise ValueError("condition string must not be empty")

    parts = raw.split(":", 1)
    name = _require_nonempty(parts[0], "condition name").lower()
    has_extra = len(parts) == 2
    extra = parts[1] if has_extra else None

    if name == "exhaustion":
        if not has_extra:
            raise ValueError("exhaustion must include a level")
        level_text = _require_nonempty(extra, "exhaustion level")
        if not level_text.isdecimal():
            raise ValueError(f"invalid exhaustion level: {raw!r}")
        level = int(level_text)
        if level < 1 or level > 6:
            raise ValueError("exhaustion level must be between 1 and 6")
        return Condition(raw=raw, name=name, level=level)

    source = None
    if has_extra:
        source = _require_nonempty(extra, "condition source")

    return Condition(raw=raw, name=name, source=source)
