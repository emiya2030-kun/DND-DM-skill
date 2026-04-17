from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.core.config import ARMOR_DEFINITIONS_PATH


class ArmorDefinitionRepository:
    """读取静态护甲与盾牌模板知识库。"""

    def __init__(self, path: Path | None = None):
        self.path = Path(path or ARMOR_DEFINITIONS_PATH)

    def load_all(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        definitions = data.get("armor_definitions")
        if not isinstance(definitions, dict):
            return {}
        return {str(key): value for key, value in definitions.items() if isinstance(value, dict)}

    def get(self, armor_id: str) -> dict[str, Any] | None:
        return self.load_all().get(armor_id)
