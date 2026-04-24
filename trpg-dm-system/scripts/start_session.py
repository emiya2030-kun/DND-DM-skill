from __future__ import annotations

import argparse

from _common import print_json
from agars_dm_backend.service import NarrativeDmService


def main() -> None:
    parser = argparse.ArgumentParser(description="Start a narrative DM session.")
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--player-name", required=True)
    parser.add_argument("--current-scene", required=True)
    args = parser.parse_args()

    service = NarrativeDmService(base_dir=args.base_dir)
    payload = service.start_session(
        campaign_id=args.campaign_id,
        session_id=args.session_id,
        player_name=args.player_name,
        current_scene=args.current_scene,
    )
    print_json(payload)


if __name__ == "__main__":
    main()
