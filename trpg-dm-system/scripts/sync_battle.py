from __future__ import annotations

import argparse
import json

from _common import print_json
from agars_dm_backend.service import NarrativeDmService


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync battle state into the narrative DM backend.")
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--encounter-id", required=True)
    parser.add_argument("--encounter-state-json", required=True)
    parser.add_argument("--new-events-json", required=True)
    args = parser.parse_args()

    service = NarrativeDmService(base_dir=args.base_dir)
    payload = service.sync_battle(
        session_id=args.session_id,
        encounter_id=args.encounter_id,
        encounter_state=json.loads(args.encounter_state_json),
        new_events=json.loads(args.new_events_json),
    )
    print_json(payload)


if __name__ == "__main__":
    main()
