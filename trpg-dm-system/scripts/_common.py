from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
