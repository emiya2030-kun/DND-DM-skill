from __future__ import annotations

import argparse

from _common import print_json
from agars_dm_backend.service import NarrativeDmService


def main() -> None:
    parser = argparse.ArgumentParser(description="Query campaign facts from ingested setting snippets.")
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--query", required=True)
    args = parser.parse_args()

    service = NarrativeDmService(base_dir=args.base_dir)
    payload = service.query_facts(
        campaign_id=args.campaign_id,
        query=args.query,
    )
    print_json(payload)


if __name__ == "__main__":
    main()
