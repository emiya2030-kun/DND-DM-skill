import sys
from pathlib import Path

from tinydb import Query

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.core.db import get_encounters_state


def main() -> None:
    db = get_encounters_state()
    encounter_id = "enc_day1_test"

    db.remove(Query().encounter_id == encounter_id)

    record = {
        "encounter_id": encounter_id,
        "name": "Test Encounter",
        "round": 1,
        "turn_index": 0,
        "active_entity_id": None,
        "entities": [],
    }
    db.insert(record)

    loaded = db.get(Query().encounter_id == encounter_id)
    print(loaded)

    db.close()


if __name__ == "__main__":
    main()
