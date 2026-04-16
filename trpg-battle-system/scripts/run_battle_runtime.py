#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runtime.context import build_runtime_context
from runtime.http_server import ThreadingHTTPServer, build_runtime_handler_class


def main() -> None:
    parser = argparse.ArgumentParser(description="Run persistent battle runtime server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8771, type=int)
    args = parser.parse_args()

    context = build_runtime_context()
    handler_class = build_runtime_handler_class(runtime_context=context)
    server = ThreadingHTTPServer((args.host, args.port), handler_class)
    try:
        print(f"http://{args.host}:{args.port}")
        server.serve_forever()
    finally:
        context.close()
        server.server_close()


if __name__ == "__main__":
    main()
