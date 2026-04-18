from __future__ import annotations

from typing import Any


class RuleValidationError(ValueError):
    def __init__(
        self,
        error_code: str,
        message: str | None = None,
        *,
        rule_context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(error_code)
        self.error_code = error_code
        self.message = message or error_code
        self.rule_context = dict(rule_context or {})

