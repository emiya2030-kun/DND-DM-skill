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


def build_static_player_sheet() -> dict[str, object]:
    return {
        "summary": {
            "name": "奎里昂",
            "class_name": "战士",
            "subclass_name": "奥法骑士",
            "level": 4,
            "hp_current": 44,
            "hp_max": 44,
            "ac": 16,
            "spell_save_dc": 13,
            "spell_attack_bonus": 5,
            "portrait_url": None,
        },
        "abilities": [
            {"key": "str", "label": "力量", "score": 8, "save_bonus": 2},
            {"key": "dex", "label": "敏捷", "score": 18, "save_bonus": 4},
            {"key": "con", "label": "体魄", "score": 14, "save_bonus": 5},
            {"key": "int", "label": "智力", "score": 14, "save_bonus": 2},
            {"key": "wis", "label": "感知", "score": 10, "save_bonus": 0},
            {"key": "cha", "label": "魅力", "score": 10, "save_bonus": 0},
        ],
        "tabs": {
            "skills": [
                {"key": "athletics", "label": "运动", "modifier": -1},
                {"key": "acrobatics", "label": "特技", "modifier": 4},
                {"key": "sleight_of_hand", "label": "巧手", "modifier": 4},
                {"key": "stealth", "label": "隐匿", "modifier": 4},
                {"key": "arcana", "label": "奥秘", "modifier": 5},
                {"key": "history", "label": "历史", "modifier": 2},
                {"key": "investigation", "label": "调查", "modifier": 2},
                {"key": "nature", "label": "自然", "modifier": 2},
                {"key": "religion", "label": "宗教", "modifier": 2},
                {"key": "animal_handling", "label": "驯服动物", "modifier": 0},
                {"key": "insight", "label": "洞悉", "modifier": 0},
                {"key": "medicine", "label": "医疗", "modifier": 0},
                {"key": "perception", "label": "察觉", "modifier": 3},
                {"key": "survival", "label": "求生", "modifier": 0},
                {"key": "deception", "label": "欺瞒", "modifier": 0},
                {"key": "intimidation", "label": "威吓", "modifier": 0},
                {"key": "performance", "label": "表演", "modifier": 0},
                {"key": "persuasion", "label": "说服", "modifier": 3},
            ],
            "equipment": [
                {"name": "干将", "attack_bonus": 7, "damage": "1d6+4", "mastery": "侵扰"},
                {"name": "莫邪", "attack_bonus": 7, "damage": "1d6+4", "mastery": "讯切"},
            ],
            "extras": {
                "placeholder_title": "后续追加",
                "placeholder_body": "后续会加入特性、状态、资源与法术相关信息。",
            },
        },
    }


def render_player_sheet_shell(player_sheet: dict[str, object]) -> str:
    summary = player_sheet.get("summary", {}) if isinstance(player_sheet, dict) else {}
    health_line = (
        f"{summary.get('hp_current', '--')} / {summary.get('hp_max', '--')} HP · AC {summary.get('ac', '--')}"
    )
    return (
        '<section class="player-sheet-shell" data-role="player-sheet-shell">'
        '<div class="player-sheet-grid">'
        '<aside class="player-sheet-portrait" data-role="player-sheet-portrait">'
        '<div class="player-sheet-portrait-frame">'
        '<div class="player-sheet-portrait-mark"></div>'
        '<div class="player-sheet-portrait-label">主角头像</div>'
        "</div>"
        "</aside>"
        '<div class="player-sheet-main">'
        f'<div class="player-sheet-summary" data-role="player-sheet-summary">{health_line}</div>'
        '<div class="player-sheet-abilities" data-role="player-sheet-abilities"></div>'
        '<div class="player-sheet-tabs" data-role="player-sheet-tabs"></div>'
        '<div class="player-sheet-panel" data-role="player-sheet-panel"></div>'
        "</div>"
        "</div>"
        "</section>"
    )


def build_player_sheet_styles() -> str:
    return (
        ".player-sheet-shell{position:relative;padding:18px;border-radius:28px;"
        "background:linear-gradient(180deg,rgba(29,24,19,.96),rgba(11,12,14,.98));"
        "border:1px solid rgba(214,176,112,.22);"
        "box-shadow:0 24px 48px rgba(0,0,0,.35),inset 0 1px 0 rgba(255,237,203,.05);}"
        ".player-sheet-grid{display:grid;grid-template-columns:170px minmax(0,1fr);gap:16px;align-items:stretch;}"
        ".player-sheet-portrait-frame{min-height:320px;border-radius:20px;padding:14px;"
        "display:flex;align-items:center;justify-content:center;flex-direction:column;gap:14px;"
        "background:linear-gradient(180deg,rgba(85,56,28,.92),rgba(24,20,18,.96));"
        "border:1px solid rgba(225,188,122,.28);box-shadow:inset 0 0 0 1px rgba(255,246,222,.05),0 14px 28px rgba(0,0,0,.28);}"
        ".player-sheet-portrait-mark{width:74px;height:74px;border-radius:50%;"
        "background:radial-gradient(circle at 35% 30%,#f0d4a4 0,#9d6f3b 26%,#352518 62%,#1a1613 100%);}"
        ".player-sheet-portrait-label{color:#ead7b1;font-size:13px;letter-spacing:.18em;text-transform:uppercase;}"
        ".player-sheet-main{display:grid;gap:14px;}"
        ".player-sheet-summary{padding:16px 18px;border-radius:20px;"
        "background:linear-gradient(180deg,rgba(15,15,16,.72),rgba(8,8,10,.82));"
        "border:1px solid rgba(214,176,112,.2);}"
        ".player-sheet-name{font-size:36px;font-weight:900;letter-spacing:.01em;color:#f3e7cf;}"
        ".player-sheet-class{margin-top:4px;color:#bea57a;font-size:12px;letter-spacing:.2em;text-transform:uppercase;}"
        ".player-sheet-health{margin-top:10px;display:inline-flex;padding:8px 12px;border-radius:999px;"
        "background:rgba(112,34,29,.38);border:1px solid rgba(255,151,135,.18);color:#ffe0d7;font-weight:800;}"
        ".player-sheet-spell{margin-top:10px;color:#cbbca2;font-size:13px;}"
        ".player-sheet-abilities{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px;}"
        ".player-sheet-ability{padding:12px 8px;border-radius:16px;background:rgba(18,15,12,.94);"
        "border:1px solid rgba(214,176,112,.14);text-align:center;}"
        ".player-sheet-ability-label{display:block;font-size:11px;color:#90816a;letter-spacing:.12em;}"
        ".player-sheet-ability-score{display:block;font-size:26px;font-weight:900;color:#f6e7ca;}"
        ".player-sheet-ability-save{display:block;font-size:12px;color:#d0b27b;}"
        ".player-sheet-tabs{display:flex;gap:10px;flex-wrap:wrap;}"
        ".player-sheet-tab{appearance:none;border:none;padding:10px 16px;border-radius:999px;"
        "background:rgba(255,255,255,.04);color:#b7a98d;border:1px solid rgba(214,176,112,.12);font-weight:700;cursor:pointer;}"
        ".player-sheet-tab.is-active{background:linear-gradient(180deg,rgba(197,149,75,.3),rgba(110,76,32,.36));"
        "color:#f7e6c6;border-color:rgba(223,187,122,.3);font-weight:800;letter-spacing:.08em;}"
        ".player-sheet-panel{padding:14px;border-radius:20px;background:rgba(8,8,10,.72);border:1px solid rgba(214,176,112,.16);"
        "display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px 16px;}"
        ".player-sheet-skill-row,.player-sheet-equipment-row{padding:10px 12px;border-radius:14px;background:rgba(255,255,255,.03);"
        "border:1px solid rgba(214,176,112,.08);display:flex;justify-content:space-between;gap:10px;color:#eee2c8;}"
        ".player-sheet-equipment-row{grid-column:1 / -1;display:grid;grid-template-columns:minmax(0,1fr) 72px 92px 88px;}"
        ".player-sheet-empty{grid-column:1 / -1;padding:14px;border-radius:14px;background:rgba(255,255,255,.03);"
        "border:1px solid rgba(214,176,112,.08);color:#d8c8aa;}"
        ".player-sheet-empty p{margin:8px 0 0;color:#a8997f;}"
        "@media (max-width: 1080px){.player-sheet-grid{grid-template-columns:1fr;}.player-sheet-portrait-frame{min-height:220px;}.player-sheet-panel{grid-template-columns:repeat(2,minmax(0,1fr));}}"
        "@media (max-width: 760px){.player-sheet-shell{padding:16px;}.player-sheet-abilities{grid-template-columns:repeat(2,minmax(0,1fr));}.player-sheet-panel{grid-template-columns:1fr;}.player-sheet-equipment-row{grid-template-columns:1fr 64px 88px 76px;}}"
    )


def build_player_sheet_runtime_script(player_sheet: dict[str, object]) -> str:
    player_sheet_json = json.dumps(player_sheet, ensure_ascii=False)
    return (
        f"window.__PLAYER_SHEET__ = {player_sheet_json};"
        "window.__PLAYER_SHEET_ACTIVE_TAB__ = 'skills';"
        "window.formatSignedModifier = function(value){"
        "if(typeof value!=='number'){return '--';}"
        "if(value>0){return '+' + value;}"
        "if(value===0){return '0';}"
        "return String(value);"
        "};"
        "window.renderPlayerSheet = function(playerSheet){"
        "var summary=(playerSheet&&playerSheet.summary)||{};"
        "var summaryRoot=document.querySelector('[data-role=\"player-sheet-summary\"]');"
        "if(summaryRoot){summaryRoot.innerHTML='"
        "<div class=\"player-sheet-name\">' + (summary.name||'未命名角色') + '</div>' + "
        "'<div class=\"player-sheet-class\">' + ((summary.subclass_name||summary.class_name||'未知职业') + ' · ' + (summary.level||'--') + '级') + '</div>' + "
        "'<div class=\"player-sheet-health\">' + (summary.hp_current ?? '--') + ' / ' + (summary.hp_max ?? '--') + ' HP · AC ' + (summary.ac ?? '--') + '</div>' + "
        "'<div class=\"player-sheet-spell\">法术豁免 ' + (summary.spell_save_dc ?? '--') + ' · 法术攻击 ' + window.formatSignedModifier(summary.spell_attack_bonus) + '</div>';}"
        "var abilityRoot=document.querySelector('[data-role=\"player-sheet-abilities\"]');"
        "if(abilityRoot){abilityRoot.innerHTML=((playerSheet&&playerSheet.abilities)||[]).map(function(item){"
        "return '<div class=\"player-sheet-ability\">' + "
        "'<span class=\"player-sheet-ability-label\">' + item.label + '</span>' + "
        "'<strong class=\"player-sheet-ability-score\">' + item.score + '</strong>' + "
        "'<span class=\"player-sheet-ability-save\">豁免 ' + window.formatSignedModifier(item.save_bonus) + '</span>' + "
        "'</div>';"
        "}).join('');}"
        "var tabRoot=document.querySelector('[data-role=\"player-sheet-tabs\"]');"
        "if(tabRoot){tabRoot.innerHTML=["
        "'<button class=\"player-sheet-tab' + (window.__PLAYER_SHEET_ACTIVE_TAB__==='skills' ? ' is-active' : '') + '\" data-player-sheet-tab=\"skills\">技能</button>',"
        "'<button class=\"player-sheet-tab' + (window.__PLAYER_SHEET_ACTIVE_TAB__==='equipment' ? ' is-active' : '') + '\" data-player-sheet-tab=\"equipment\">装备</button>',"
        "'<button class=\"player-sheet-tab' + (window.__PLAYER_SHEET_ACTIVE_TAB__==='extras' ? ' is-active' : '') + '\" data-player-sheet-tab=\"extras\">后续追加</button>'"
        "].join('');}"
        "window.renderPlayerSheetPanel(playerSheet, window.__PLAYER_SHEET_ACTIVE_TAB__);"
        "return playerSheet;"
        "};"
        "window.renderPlayerSheetPanel = function(playerSheet, activeTab){"
        "var panelRoot=document.querySelector('[data-role=\"player-sheet-panel\"]');"
        "if(!panelRoot){return;}"
        "if(activeTab==='equipment'){panelRoot.innerHTML=((playerSheet&&playerSheet.tabs&&playerSheet.tabs.equipment)||[]).map(function(item){"
        "return '<div class=\"player-sheet-equipment-row\">' + "
        "'<strong>' + item.name + '</strong>' + "
        "'<span>' + window.formatSignedModifier(item.attack_bonus) + '</span>' + "
        "'<span>' + item.damage + '</span>' + "
        "'<span>' + (item.mastery||'--') + '</span>' + "
        "'</div>';"
        "}).join('') || '<div class=\"player-sheet-empty\">暂无装备数据</div>';return;}"
        "if(activeTab==='extras'){var extras=(playerSheet&&playerSheet.tabs&&playerSheet.tabs.extras)||{};"
        "panelRoot.innerHTML='<div class=\"player-sheet-empty\"><strong>' + (extras.placeholder_title||'后续追加') + '</strong><p>' + (extras.placeholder_body||'后续会加入更多角色信息。') + '</p></div>';return;}"
        "panelRoot.innerHTML=((playerSheet&&playerSheet.tabs&&playerSheet.tabs.skills)||[]).map(function(item){"
        "return '<div class=\"player-sheet-skill-row\">' + "
        "'<span>' + item.label + '</span>' + "
        "'<strong>' + window.formatSignedModifier(item.modifier) + '</strong>' + "
        "'</div>';"
        "}).join('');"
        "};"
        "document.addEventListener('click',function(event){"
        "var button=event.target&&event.target.closest('[data-player-sheet-tab]');"
        "if(!button){return;}"
        "window.__PLAYER_SHEET_ACTIVE_TAB__=button.getAttribute('data-player-sheet-tab')||'skills';"
        "window.renderPlayerSheet(window.__PLAYER_SHEET__);"
        "});"
        "window.renderPlayerSheet(window.__PLAYER_SHEET__);"
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
        player_sheet = build_static_player_sheet()
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
            f"{build_player_sheet_styles()}"
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
            f"{render_player_sheet_shell(player_sheet)}"
            "</div>"
            "</main>"
            "<script>"
            f"window.__BATTLEMAP_STATE__ = {json.dumps(initial_state, ensure_ascii=False)};"
            "window.__LAST_TOOL_RESULT__ = null;"
            "window.__LAST_TOOL_ERROR__ = null;"
            f"{build_player_sheet_runtime_script(player_sheet)}"
            "window.getEncounterState = function(){return window.__BATTLEMAP_STATE__;};"
            "window.getLastToolResult = function(){return window.__LAST_TOOL_RESULT__;};"
            "window.getLastToolError = function(){return window.__LAST_TOOL_ERROR__;};"
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
            "window.__LAST_TOOL_ERROR__ = null;"
            "if(!toolResult.encounter_state||typeof toolResult.encounter_state !== 'object'){"
            "throw new Error('tool result does not contain encounter_state');}"
            "var appliedState=window.applyEncounterState(toolResult.encounter_state);"
            "document.dispatchEvent(new CustomEvent('battlemap:tool-result-applied',{detail:{toolResult:toolResult,encounterState:appliedState}}));"
            "return appliedState;"
            "};"
            "window.applyToolError = function(toolError){"
            "if(!toolError||typeof toolError !== 'object'){throw new Error('tool error must be an object');}"
            "window.__LAST_TOOL_ERROR__ = toolError;"
            "var appliedState=window.getEncounterState();"
            "if(toolError.encounter_state&&typeof toolError.encounter_state === 'object'){"
            "appliedState=window.applyEncounterState(toolError.encounter_state);"
            "}"
            "document.dispatchEvent(new CustomEvent('battlemap:tool-error-applied',{detail:{toolError:toolError,encounterState:appliedState}}));"
            "return toolError;"
            "};"
            "window.__BATTLEMAP_RUNTIME__ = {"
            "channel:'battlemap-runtime',"
            "applyEncounterState:function(nextState){return window.applyEncounterState(nextState);},"
            "applyToolResult:function(toolResult){return window.applyToolResult(toolResult);},"
            "applyToolError:function(toolError){return window.applyToolError(toolError);},"
            "getEncounterState:function(){return window.getEncounterState();},"
            "getLastToolError:function(){return window.getLastToolError();}"
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
            "return;"
            "}"
            "if(data.action==='apply_tool_error'){"
            "window.applyToolError(data.payload);"
            "document.dispatchEvent(new CustomEvent('battlemap:runtime-message-applied',{detail:{action:data.action,encounterState:window.getEncounterState(),toolError:data.payload}}));"
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
