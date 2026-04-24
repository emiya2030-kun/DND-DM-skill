from __future__ import annotations

import argparse

from _common import print_json
from agars_dm_backend.service import NarrativeDmService


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest campaign setting files for the narrative DM backend.")
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--file", action="append", required=True, dest="files")
    args = parser.parse_args()

    service = NarrativeDmService(base_dir=args.base_dir)
    payload = service.ingest_setting(
        campaign_id=args.campaign_id,
        title=args.title,
        file_paths=args.files,
    )
    print_json(payload)


if __name__ == "__main__":
    main()
