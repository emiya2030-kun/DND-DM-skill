#!/usr/bin/env python3
"""启动一个本地 battlemap 页面服务，并从共享 encounter 仓储轮询最新状态。"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.render_battlemap_preview import build_preview_encounter
from tools.models import Encounter
from tools.repositories import EncounterRepository
from tools.services import GetEncounterState, RenderBattlemapPage

PREVIEW_ENCOUNTER_ID = "enc_preview_demo"


def ensure_preview_encounter(repository: EncounterRepository) -> object:
    encounter = repository.get(PREVIEW_ENCOUNTER_ID)
    if encounter is not None:
        return encounter
    encounter = build_preview_encounter()
    repository.save(encounter)
    return encounter


def build_dev_reload_script(dev_reload_path: str) -> str:
    return (
        "<script>"
        "(function(){"
        f"var reloadPath={json.dumps(dev_reload_path, ensure_ascii=False)};"
        "window.__BATTLEMAP_DEV__={reloadPath:reloadPath,reloadToken:null,pollIntervalMs:700};"
        "async function pollReloadToken(){"
        "var response=await fetch(reloadPath,{cache:'no-store'});"
        "if(!response.ok){return null;}"
        "var payload=await response.json();"
        "if(!window.__BATTLEMAP_DEV__.reloadToken){window.__BATTLEMAP_DEV__.reloadToken=payload.reload_token;return payload;}"
        "if(payload.reload_token!==window.__BATTLEMAP_DEV__.reloadToken){"
        "window.__BATTLEMAP_DEV__.reloadToken=payload.reload_token;"
        "window.location.reload();"
        "return payload;"
        "}"
        "return payload;"
        "}"
        "window.__BATTLEMAP_DEV__.pollReloadToken=pollReloadToken;"
        "setInterval(pollReloadToken, window.__BATTLEMAP_DEV__.pollIntervalMs);"
        "})();"
        "</script>"
    )


def render_localhost_battlemap_page(
    *,
    encounter: Encounter,
    page_title: str,
    dev_reload_path: str | None = None,
) -> str:
    html = RenderBattlemapPage().execute(encounter)
    polling_script = (
        "<script>"
        "(function(){"
        f"document.title={json.dumps(page_title, ensure_ascii=False)};"
        f"var encounterId={json.dumps(encounter.encounter_id, ensure_ascii=False)};"
        "var lastSerializedState=JSON.stringify(window.getEncounterState());"
        "async function fetchLatestEncounterState(){"
        "var response=await fetch('/api/encounter-state?encounter_id=' + encodeURIComponent(encounterId),{cache:'no-store'});"
        "if(!response.ok){throw new Error('failed to fetch encounter state');}"
        "var nextState=await response.json();"
        "var serialized=JSON.stringify(nextState);"
        "if(serialized===lastSerializedState){return null;}"
        "lastSerializedState=serialized;"
        "var appliedState=window.applyEncounterState(nextState);"
        "document.dispatchEvent(new CustomEvent('battlemap:polling-sync-applied',{detail:{encounterState:appliedState}}));"
        "return appliedState;"
        "}"
        "window.__BATTLEMAP_RUNTIME__.fetchLatestEncounterState=fetchLatestEncounterState;"
        "window.__BATTLEMAP_RUNTIME__.pollIntervalMs=1000;"
        "setInterval(fetchLatestEncounterState, window.__BATTLEMAP_RUNTIME__.pollIntervalMs);"
        "})();"
        "</script>"
    )
    if dev_reload_path:
        polling_script += build_dev_reload_script(dev_reload_path)
    return html.replace("</body>", polling_script + "</body>")


class BattlemapLocalhostHandler(BaseHTTPRequestHandler):
    repository: EncounterRepository | None = None
    page_title: str = "Battlemap Localhost"
    dev_reload_path: str | None = None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_page()
            return
        if parsed.path == "/api/encounter-state":
            self._serve_encounter_state(parsed.query)
            return
        self.send_error(404, "Not Found")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _serve_page(self) -> None:
        encounter = build_preview_encounter()
        if self.repository is not None:
            encounter = ensure_preview_encounter(self.repository)
        html = render_localhost_battlemap_page(
            encounter=encounter,
            page_title=self.page_title,
            dev_reload_path=self.dev_reload_path,
        )
        encoded = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _serve_encounter_state(self, query_string: str) -> None:
        if self.repository is None:
            self.send_error(500, "Repository not configured")
            return
        params = parse_qs(query_string)
        encounter_id = params.get("encounter_id", [PREVIEW_ENCOUNTER_ID])[0]
        state = GetEncounterState(self.repository).execute(encounter_id)
        payload = json.dumps(state, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local battlemap preview server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--dev-reload-path", default=None)
    args = parser.parse_args()

    repository = EncounterRepository()
    repository.save(build_preview_encounter())

    BattlemapLocalhostHandler.repository = repository
    BattlemapLocalhostHandler.page_title = "Battlemap Localhost"
    BattlemapLocalhostHandler.dev_reload_path = args.dev_reload_path

    server = ThreadingHTTPServer((args.host, args.port), BattlemapLocalhostHandler)
    try:
        print(f"http://{args.host}:{args.port}")
        server.serve_forever()
    finally:
        repository.close()
        server.server_close()


if __name__ == "__main__":
    main()
