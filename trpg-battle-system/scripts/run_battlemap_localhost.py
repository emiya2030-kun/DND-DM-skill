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
from runtime.commands import COMMAND_HANDLERS
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


def fetch_runtime_health(runtime_base_url: str) -> dict[str, object]:
    request = Request(
        runtime_base_url.rstrip("/") + "/runtime/health",
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
        raise RuntimeError(f"runtime health request failed: {error}") from error


def assert_runtime_command_compatibility(
    runtime_base_url: str,
    *,
    required_commands: list[str] | None = None,
) -> dict[str, object]:
    payload = fetch_runtime_health(runtime_base_url)
    status = payload.get("status")
    if status != "ok":
        raise RuntimeError(f"runtime health check failed: {payload}")
    available_commands = payload.get("commands")
    if not isinstance(available_commands, list):
        raise RuntimeError("runtime health payload missing commands list")
    required = required_commands or sorted(COMMAND_HANDLERS.keys())
    available = {str(command) for command in available_commands}
    missing_commands = [command for command in required if command not in available]
    if missing_commands:
        raise RuntimeError(
            "runtime missing required commands: " + ", ".join(missing_commands)
        )
    return payload


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
    initial_state: dict[str, object] | None = None,
) -> str:
    if initial_state is not None:
        battlemap_details = initial_state.get("battlemap_details")
        if not isinstance(battlemap_details, dict):
            battlemap_details = {}
        battlemap_view = initial_state.get("battlemap_view")
        if not isinstance(battlemap_view, dict):
            battlemap_view = {}
        encounter_name = str(initial_state.get("encounter_name") or encounter_id)
        round_value = initial_state.get("round")
        round_number = round_value if isinstance(round_value, int) else 1
        map_name = str(battlemap_details.get("name") or "战斗地图")
        map_description = str(battlemap_details.get("description") or "等待战场数据同步。")
        dimensions = str(battlemap_details.get("dimensions") or "未知")
        grid_size = str(battlemap_details.get("grid_size") or "每格 5 尺")
        battlemap_html = str(battlemap_view.get("html") or "<section>等待战场数据同步。</section>")
        html = (
            "<!DOCTYPE html>"
            '<html lang="zh-CN">'
            "<head>"
            '<meta charset="utf-8" />'
            '<meta name="viewport" content="width=device-width, initial-scale=1" />'
            f"<title>{encounter_name} 战斗地图预览</title>"
            "<style>"
            ":root{color-scheme:dark;--bg:#071019;--bg-2:#0d1724;--panel:rgba(12,20,31,.78);--line:rgba(169,191,224,.14);--text:#edf3ff;--muted:#97a9c3;--gold:#d8b36a;}"
            "*{box-sizing:border-box;}"
            "body{margin:0;min-height:100vh;background:"
            "radial-gradient(circle at top left,rgba(53,94,162,.24),transparent 22%),"
            "radial-gradient(circle at top right,rgba(216,179,106,.08),transparent 18%),"
            "linear-gradient(180deg,#09111a 0,#060c13 100%);"
            "color:var(--text);font-family:'Avenir Next','Segoe UI',sans-serif;}"
            ".battlemap-app{position:relative;overflow:hidden;}"
            ".battlemap-app::before{content:'';position:fixed;inset:0;pointer-events:none;opacity:.18;"
            "background-image:radial-gradient(rgba(255,255,255,.16) .8px,transparent .8px);background-size:24px 24px;mix-blend-mode:soft-light;}"
            ".battlemap-preview{max-width:1680px;margin:0 auto;padding:24px 24px 40px;}"
            ".app-shell{display:grid;gap:22px;}"
            ".encounter-hero{position:relative;padding:20px 22px 22px;border-radius:26px;overflow:hidden;"
            "background:linear-gradient(180deg,rgba(12,20,31,.92),rgba(9,16,25,.84));"
            "border:1px solid var(--line);box-shadow:0 32px 80px rgba(1,4,9,.48),inset 0 1px 0 rgba(255,255,255,.04);}"
            ".encounter-hero::after{content:'';position:absolute;inset:auto -8% -30% auto;width:320px;height:320px;"
            "background:radial-gradient(circle,rgba(83,129,214,.22),transparent 64%);pointer-events:none;}"
            ".hero-topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-bottom:18px;}"
            ".topbar-chip{display:inline-flex;align-items:center;min-height:34px;padding:0 14px;border-radius:999px;"
            "background:rgba(255,255,255,.04);border:1px solid rgba(169,191,224,.16);color:#dce8fb;font-size:12px;letter-spacing:.12em;text-transform:uppercase;}"
            ".topbar-chip--accent{background:rgba(216,179,106,.12);border-color:rgba(216,179,106,.24);color:#f2d8a6;}"
            ".hero-grid{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(320px,.7fr);gap:18px;align-items:end;}"
            ".hero-copy h1{margin:0 0 12px;font-size:clamp(40px,5vw,72px);line-height:.95;letter-spacing:-.05em;}"
            ".hero-copy p{margin:0;max-width:58ch;color:var(--muted);font-size:16px;line-height:1.7;}"
            ".hero-facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;}"
            ".fact{padding:14px 16px;border-radius:18px;background:rgba(255,255,255,.035);border:1px solid rgba(169,191,224,.12);backdrop-filter:blur(12px);}"
            ".fact-label{display:block;margin-bottom:6px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);}"
            ".fact-value{font-size:22px;font-weight:700;letter-spacing:-.03em;}"
            "@media (max-width: 1080px){.hero-grid{grid-template-columns:1fr;}.hero-facts{grid-template-columns:repeat(3,minmax(0,1fr));}}"
            "@media (max-width: 760px){.battlemap-preview{padding:16px 16px 28px;}.encounter-hero{padding:18px;}.hero-facts{grid-template-columns:1fr;}.hero-copy h1{font-size:40px;}}"
            "</style>"
            "</head>"
            "<body>"
            '<main class="battlemap-preview battlemap-app">'
            '<div class="app-shell">'
            '<section class="encounter-hero hero" data-role="encounter-hero">'
            '<div class="hero-topbar">'
            '<span class="topbar-chip">战斗地图预览</span>'
            f'<span class="topbar-chip" data-role="map-name-chip">{map_name}</span>'
            f'<span class="topbar-chip topbar-chip--accent" data-role="round-chip">第 {round_number} 轮</span>'
            "</div>"
            '<div class="hero-grid">'
            '<div class="hero-copy hero-card">'
            f'<h1 data-role="encounter-title">{encounter_name}</h1>'
            f'<p data-role="map-description">{map_description}</p>'
            "</div>"
            '<div class="hero-facts facts">'
            f'<div class="fact"><span class="fact-label">地图尺寸</span><span class="fact-value" data-role="dimensions-value">{dimensions.replace(" x ", " × ").replace(" tiles", "")}</span></div>'
            f'<div class="fact"><span class="fact-label">比例尺</span><span class="fact-value" data-role="grid-size-value">{grid_size.replace("Each tile represents ", "每格 ").replace(" feet", " 尺")}</span></div>'
            f'<div class="fact"><span class="fact-label">当前轮次</span><span class="fact-value" data-role="round-value">第 {round_number} 轮</span></div>'
            "</div></div>"
            "</section>"
            f'<div data-role="battlemap-view-root">{battlemap_html}</div>'
            "</div>"
            "</main>"
            "<script>"
            f"window.__BATTLEMAP_STATE__ = {json.dumps(initial_state, ensure_ascii=False)};"
            "window.__LAST_TOOL_RESULT__ = null;"
            "window.getEncounterState = function(){return window.__BATTLEMAP_STATE__;};"
            "window.getLastToolResult = function(){return window.__LAST_TOOL_RESULT__;};"
            "window.applyEncounterState = function(nextState){"
            "if(!nextState||typeof nextState !== 'object'){throw new Error('encounter state must be an object');}"
            "window.__BATTLEMAP_STATE__ = nextState;"
            "if(typeof nextState.encounter_name === 'string'){document.title = nextState.encounter_name + ' 战斗地图预览';"
            "var titleNode=document.querySelector('[data-role=\"encounter-title\"]');if(titleNode){titleNode.textContent=nextState.encounter_name;}}"
            "if(typeof nextState.round === 'number'){"
            "var roundChip=document.querySelector('[data-role=\"round-chip\"]');if(roundChip){roundChip.textContent='第 ' + nextState.round + ' 轮';}"
            "var roundValue=document.querySelector('[data-role=\"round-value\"]');if(roundValue){roundValue.textContent='第 ' + nextState.round + ' 轮';}}"
            "if(nextState.battlemap_details){"
            "var details=nextState.battlemap_details;"
            "var mapNameChip=document.querySelector('[data-role=\"map-name-chip\"]');if(mapNameChip&&typeof details.name==='string'){mapNameChip.textContent=details.name;}"
            "var mapDescription=document.querySelector('[data-role=\"map-description\"]');if(mapDescription&&typeof details.description==='string'){mapDescription.textContent=details.description;}"
            "var dimensions=document.querySelector('[data-role=\"dimensions-value\"]');if(dimensions&&typeof details.dimensions==='string'){dimensions.textContent=details.dimensions.replace(' x ', ' × ').replace(' tiles', '');}"
            "var gridSize=document.querySelector('[data-role=\"grid-size-value\"]');if(gridSize&&typeof details.grid_size==='string'){gridSize.textContent=details.grid_size.replace('Each tile represents ', '每格 ').replace(' feet', ' 尺');}}"
            "if(nextState.battlemap_view&&typeof nextState.battlemap_view.html==='string'){"
            "var root=document.querySelector('[data-role=\"battlemap-view-root\"]');if(root){root.innerHTML=nextState.battlemap_view.html;}}"
            "document.dispatchEvent(new CustomEvent('battlemap:state-applied',{detail:{encounterState:nextState}}));"
            "return nextState;"
            "};"
            "window.applyToolResult = function(toolResult){"
            "if(!toolResult||typeof toolResult !== 'object'){throw new Error('tool result must be an object');}"
            "window.__LAST_TOOL_RESULT__ = toolResult;"
            "if(!toolResult.encounter_state||typeof toolResult.encounter_state !== 'object'){"
            "throw new Error('tool result does not contain encounter_state');}"
            "var appliedState=window.applyEncounterState(toolResult.encounter_state);"
            "document.dispatchEvent(new CustomEvent('battlemap:tool-result-applied',{detail:{toolResult:toolResult,encounterState:appliedState}}));"
            "return appliedState;"
            "};"
            "window.__BATTLEMAP_RUNTIME__ = {"
            "channel:'battlemap-runtime',"
            "applyEncounterState:function(nextState){return window.applyEncounterState(nextState);},"
            "applyToolResult:function(toolResult){return window.applyToolResult(toolResult);},"
            "getEncounterState:function(){return window.getEncounterState();}"
            "};"
            "window.addEventListener('message',function(event){"
            "var data=event&&event.data;"
            "if(!data||typeof data!=='object'||data.channel!=='battlemap-runtime'){return;}"
            "if(data.action==='apply_encounter_state'){"
            "var appliedState=window.applyEncounterState(data.payload);"
            "document.dispatchEvent(new CustomEvent('battlemap:runtime-message-applied',{detail:{action:data.action,encounterState:appliedState}}));"
            "return;"
            "}"
            "if(data.action==='apply_tool_result'){"
            "var appliedToolState=window.applyToolResult(data.payload);"
            "document.dispatchEvent(new CustomEvent('battlemap:runtime-message-applied',{detail:{action:data.action,encounterState:appliedToolState}}));"
            "}"
            "});"
            "document.dispatchEvent(new CustomEvent('battlemap:runtime-ready',{detail:{channel:'battlemap-runtime'}}));"
            "</script>"
            "</body>"
            "</html>"
        )
    else:
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
    encounter_id: str = PREVIEW_ENCOUNTER_ID

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
        encounter_id = self.encounter_id
        encounter = build_preview_encounter()
        initial_state: dict[str, object] | None = None
        if self.runtime_base_url is not None:
            try:
                state = fetch_runtime_encounter_state(self.runtime_base_url, encounter_id)
            except Exception as error:
                self.send_error(502, f"Runtime backend unavailable: {error}")
                return
            proxied_status = state.pop("_status", 200) if isinstance(state, dict) else 200
            if proxied_status != 200:
                self.send_error(int(proxied_status), "Failed to load encounter state")
                return
            initial_state = state
        if self.repository is not None and self.runtime_base_url is None:
            encounter = ensure_preview_encounter(self.repository)
            encounter_id = encounter.encounter_id
        html = render_localhost_battlemap_page(
            encounter_id=encounter_id,
            encounter=encounter,
            initial_state=initial_state,
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
        encounter_id = params.get("encounter_id", [self.encounter_id])[0]
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
    parser.add_argument("--encounter-id", default=PREVIEW_ENCOUNTER_ID)
    parser.add_argument("--theme", default=None)
    parser.add_argument("--dev-reload-path", default=None)
    args = parser.parse_args()

    runtime_base_url = (args.runtime_base_url or "").strip() or None
    encounter_id = (args.encounter_id or PREVIEW_ENCOUNTER_ID).strip() or PREVIEW_ENCOUNTER_ID
    repository: EncounterRepository | None = None
    if runtime_base_url is not None:
        assert_runtime_command_compatibility(runtime_base_url)
        if encounter_id == PREVIEW_ENCOUNTER_ID:
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
    BattlemapLocalhostHandler.encounter_id = encounter_id

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
