from __future__ import annotations

import argparse

from _common import print_json
from agars_dm_backend.service import NarrativeDmService


def main() -> None:
    parser = argparse.ArgumentParser(description="Build cached narrative profiles from the campaign graph summary.")
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()

    service = NarrativeDmService(base_dir=args.base_dir)
    payload = service.build_profiles(campaign_id=args.campaign_id)
    print_json(payload)


if __name__ == "__main__":
    main()
