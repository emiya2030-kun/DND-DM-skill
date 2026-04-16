#!/usr/bin/env python3
"""启动一个本地 battlemap 页面服务，并从共享 encounter 仓储轮询最新状态。"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.render_battlemap_preview import build_preview_encounter
from tools.models import Encounter
from tools.repositories import EncounterRepository
from tools.services import GetEncounterState, RenderBattlemapPage, RollInitiativeAndStartEncounter
from tools.services.encounter.manage_encounter_entities import EncounterService

PREVIEW_ENCOUNTER_ID = "enc_preview_demo"


def build_preview_map_setup() -> dict[str, object]:
    encounter = build_preview_encounter()
    return {
        "map_id": encounter.map.map_id,
        "name": encounter.map.name,
        "description": encounter.map.description,
        "width": encounter.map.width,
        "height": encounter.map.height,
        "grid_size_feet": encounter.map.grid_size_feet,
        "terrain": list(encounter.map.terrain),
        "auras": list(encounter.map.auras),
        "zones": list(encounter.map.zones),
        "remains": list(encounter.map.remains),
        "battlemap_details": list(encounter.encounter_notes),
    }


def build_preview_entity_setups() -> list[dict[str, object]]:
    return [
        {
            "entity_instance_id": "ent_ally_wizard_001",
            "template_ref": {"source_type": "pc", "template_id": "pc_miren"},
            "runtime_overrides": {
                "name": "米伦",
                "position": {"x": 5, "y": 5},
                "hp": {"current": 22, "max": 27, "temp": 0},
                "ac": 14,
                "source_ref": {"class_name": "wizard"},
            },
        },
        {
            "entity_instance_id": "ent_ally_ranger_001",
            "template_ref": {"source_type": "pc", "template_id": "pc_sabur"},
            "runtime_overrides": {
                "name": "萨布尔",
                "position": {"x": 10, "y": 8},
                "hp": {"current": 29, "max": 34, "temp": 0},
                "ac": 16,
                "source_ref": {"class_name": "ranger"},
            },
        },
        {
            "entity_instance_id": "ent_enemy_brute_001",
            "template_ref": {"source_type": "monster", "template_id": "monster_sabur"},
            "runtime_overrides": {
                "name": "钢铁蛮兵",
                "position": {"x": 17, "y": 14},
                "hp": {"current": 40, "max": 40, "temp": 0},
                "ac": 15,
                "source_ref": {"monster_type": "brute"},
            },
        },
    ]


def ensure_preview_encounter(repository: EncounterRepository) -> object:
    encounter = repository.get(PREVIEW_ENCOUNTER_ID)
    if encounter is not None:
        return encounter
    preview = build_preview_encounter()
    repository.save(
        Encounter(
            encounter_id=PREVIEW_ENCOUNTER_ID,
            name="月祷礼拜堂攻防战",
            status="active",
            round=1,
            current_entity_id=None,
            turn_order=[],
            entities={},
            map=preview.map,
        )
    )
    encounter_service = EncounterService(repository)
    encounter_service.initialize_encounter(
        PREVIEW_ENCOUNTER_ID,
        map_setup=build_preview_map_setup(),
        entity_setups=build_preview_entity_setups(),
    )
    RollInitiativeAndStartEncounter(repository).execute(PREVIEW_ENCOUNTER_ID)
    return repository.get(PREVIEW_ENCOUNTER_ID)


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


def post_runtime_command(
    runtime_base_url: str,
    *,
    command: str,
    args: dict[str, object],
) -> dict[str, object]:
    payload = json.dumps({"command": command, "args": args}, ensure_ascii=False).encode("utf-8")
    request = Request(
        runtime_base_url.rstrip("/") + "/runtime/command",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        body = error.read().decode("utf-8")
        if body:
            try:
                return json.loads(body)
            except json.JSONDecodeError as decode_error:
                raise RuntimeError(f"runtime command request failed: {error.code}") from decode_error
        raise RuntimeError(f"runtime command request failed: {error.code}") from error
    except URLError as error:
        raise RuntimeError(f"runtime command request failed: {error}") from error


def fetch_runtime_encounter_state(
    runtime_base_url: str,
    encounter_id: str,
) -> dict[str, object]:
    query = urlencode({"encounter_id": encounter_id})
    request = Request(
        runtime_base_url.rstrip("/") + f"/runtime/encounter-state?{query}",
        method="GET",
    )
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            payload["_status"] = int(getattr(response, "status", 200))
            return payload
    except HTTPError as error:
        body = error.read().decode("utf-8")
        if body:
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = {"ok": False, "message": body}
        else:
            payload = {"ok": False, "message": f"runtime returned HTTP {error.code}"}
        payload["_status"] = int(error.code)
        return payload
    except URLError as error:
        raise RuntimeError(f"runtime encounter-state request failed: {error}") from error


def bootstrap_runtime_encounter(
    runtime_base_url: str,
    encounter_id: str,
    theme: str | None,
) -> None:
    args: dict[str, object] = {"encounter_id": encounter_id}
    if theme is not None and theme.strip():
        args["theme"] = theme
    result = post_runtime_command(
        runtime_base_url,
        command="start_random_encounter",
        args=args,
    )
    if not bool(result.get("ok")):
        raise RuntimeError(f"failed to bootstrap runtime encounter: {result}")


def render_localhost_battlemap_page(
    *,
    encounter_id: str,
    page_title: str,
    dev_reload_path: str | None = None,
    encounter: Encounter | None = None,
) -> str:
    template_encounter = encounter if encounter is not None else build_preview_encounter()
    html = RenderBattlemapPage().execute(template_encounter)
    polling_script = (
        "<script>"
        "(function(){"
        f"document.title={json.dumps(page_title, ensure_ascii=False)};"
        f"var encounterId={json.dumps(encounter_id, ensure_ascii=False)};"
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
        "fetchLatestEncounterState();"
        "setInterval(fetchLatestEncounterState, window.__BATTLEMAP_RUNTIME__.pollIntervalMs);"
        "})();"
        "</script>"
    )
    if dev_reload_path:
        polling_script += build_dev_reload_script(dev_reload_path)
    return html.replace("</body>", polling_script + "</body>")


class BattlemapLocalhostHandler(BaseHTTPRequestHandler):
    repository: EncounterRepository | None = None
    runtime_base_url: str | None = None
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
        encounter_id = PREVIEW_ENCOUNTER_ID
        encounter = build_preview_encounter()
        if self.repository is not None and self.runtime_base_url is None:
            encounter = ensure_preview_encounter(self.repository)
            encounter_id = encounter.encounter_id
        html = render_localhost_battlemap_page(
            encounter_id=encounter_id,
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
        params = parse_qs(query_string)
        encounter_id = params.get("encounter_id", [PREVIEW_ENCOUNTER_ID])[0]
        status_code = 200
        if self.runtime_base_url is not None:
            try:
                state = fetch_runtime_encounter_state(self.runtime_base_url, encounter_id)
                if isinstance(state, dict):
                    proxied_status = state.pop("_status", 200)
                    if isinstance(proxied_status, int):
                        status_code = proxied_status
            except Exception as error:
                self.send_error(502, f"Runtime backend unavailable: {error}")
                return
        else:
            if self.repository is None:
                self.send_error(500, "Repository not configured")
                return
            state = GetEncounterState(self.repository).execute(encounter_id)
        payload = json.dumps(state, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local battlemap preview server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--runtime-base-url", default="http://127.0.0.1:8771")
    parser.add_argument("--theme", default=None)
    parser.add_argument("--dev-reload-path", default=None)
    args = parser.parse_args()

    runtime_base_url = (args.runtime_base_url or "").strip() or None
    repository: EncounterRepository | None = None
    if runtime_base_url is not None:
        bootstrap_runtime_encounter(
            runtime_base_url=runtime_base_url,
            encounter_id=PREVIEW_ENCOUNTER_ID,
            theme=args.theme,
        )
    else:
        repository = EncounterRepository()
        repository.save(build_preview_encounter())

    BattlemapLocalhostHandler.repository = repository
    BattlemapLocalhostHandler.runtime_base_url = runtime_base_url
    BattlemapLocalhostHandler.page_title = "Battlemap Localhost"
    BattlemapLocalhostHandler.dev_reload_path = args.dev_reload_path

    server = ThreadingHTTPServer((args.host, args.port), BattlemapLocalhostHandler)
    try:
        print(f"http://{args.host}:{args.port}")
        server.serve_forever()
    finally:
        if repository is not None:
            repository.close()
        server.server_close()


if __name__ == "__main__":
    main()
