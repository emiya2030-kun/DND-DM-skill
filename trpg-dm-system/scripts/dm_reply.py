from __future__ import annotations

import argparse

from _common import print_json
from agars_dm_backend.service import NarrativeDmService


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a DM reply prompt bundle from narrative state.")
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--player-message", required=True)
    args = parser.parse_args()

    service = NarrativeDmService(base_dir=args.base_dir)
    payload = service.build_dm_reply(
        session_id=args.session_id,
        player_message=args.player_message,
    )
    print_json(payload)


if __name__ == "__main__":
    main()
