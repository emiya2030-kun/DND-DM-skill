from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.core.config import ENTITY_DEFINITIONS_PATH


class EntityDefinitionRepository:
    """读取静态实体模板知识库。"""

    def __init__(self, path: Path | None = None):
        self.path = Path(path or ENTITY_DEFINITIONS_PATH)

    def load_all(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        definitions = data.get("entity_definitions")
        if not isinstance(definitions, dict):
            return {}
        return {str(key): value for key, value in definitions.items() if isinstance(value, dict)}

    def get(self, template_id: str) -> dict[str, Any] | None:
        return self.load_all().get(template_id)
