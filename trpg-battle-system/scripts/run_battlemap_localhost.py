#!/usr/bin/env python3
"""启动一个本地 battlemap 页面服务,并从共享 encounter 仓储轮询最新状态."""

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
from tools.repositories import EncounterRepository, EncounterTemplateRepository
from tools.services import (
    CreateEncounterFromTemplate,
    GetEncounterState,
    ListEncounterTemplates,
    RenderBattlemapPage,
    RestoreEncounterFromTemplate,
    RollInitiativeAndStartEncounter,
    SaveEncounterTemplate,
)
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
                "ac": 16,
                "speed": {"walk": 30, "remaining": 30},
                "source_ref": {
                    "class_name": "monk",
                    "level": 5,
                },
                "class_features": {"monk": {"level": 5}},
                "ability_scores": {"str": 8, "dex": 17, "con": 14, "int": 8, "wis": 16, "cha": 10},
                "ability_mods": {"str": -1, "dex": 3, "con": 2, "int": -1, "wis": 3, "cha": 0},
                "proficiency_bonus": 3,
                "save_proficiencies": ["str", "dex"],
                "skill_training": {
                    "athletics": "none",
                    "acrobatics": "none",
                    "sleight_of_hand": "expertise",
                    "stealth": "proficient",
                    "investigation": "expertise",
                    "arcana": "proficient",
                    "history": "none",
                    "nature": "none",
                    "religion": "none",
                    "perception": "expertise",
                    "insight": "expertise",
                    "animal_handling": "none",
                    "medicine": "none",
                    "survival": "none",
                    "persuasion": "expertise",
                    "deception": "none",
                    "intimidation": "none",
                    "performance": "none",
                },
                "skill_modifiers": {
                    "athletics": -1,
                    "acrobatics": 3,
                    "sleight_of_hand": 5,
                    "stealth": 5,
                    "investigation": 1,
                    "arcana": 1,
                    "history": -1,
                    "nature": -1,
                    "religion": -1,
                    "perception": 5,
                    "insight": 5,
                    "animal_handling": 3,
                    "medicine": 3,
                    "survival": 3,
                    "persuasion": 2,
                    "deception": 0,
                    "intimidation": 0,
                    "performance": 0,
                },
                "weapons": [
                    {
                        "weapon_id": "dagger",
                        "name": "匕首",
                        "category": "simple",
                        "kind": "melee",
                        "damage": [{"formula": "1d4", "type": "piercing"}],
                        "properties": ["finesse", "light", "thrown"],
                        "range": {"normal": 5, "long": 5},
                        "thrown_range": {"normal": 20, "long": 60},
                        "mastery": "迅击",
                    }
                ],
                "inventory": [
                    {"name": "链条", "quantity": 1},
                    {"name": "绳索", "quantity": 1},
                    {"name": "铁钉", "quantity": 10},
                    {"name": "火绒盒", "quantity": 1},
                ],
                "currency": {"gp": 127},
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
        preview_entity = encounter.entities.get("ent_ally_wizard_001")
        if preview_entity is not None:
            changed = False
            desired_source_ref = {
                "class_name": "monk",
                "level": 5,
            }
            desired_skill_training = {
                "athletics": "none",
                "acrobatics": "none",
                "sleight_of_hand": "expertise",
                "stealth": "proficient",
                "investigation": "expertise",
                "arcana": "proficient",
                "history": "none",
                "nature": "none",
                "religion": "none",
                "perception": "expertise",
                "insight": "expertise",
                "animal_handling": "none",
                "medicine": "none",
                "survival": "none",
                "persuasion": "expertise",
                "deception": "none",
                "intimidation": "none",
                "performance": "none",
            }
            desired_skill_modifiers = {
                "athletics": -1,
                "acrobatics": 3,
                "sleight_of_hand": 5,
                "stealth": 5,
                "investigation": 1,
                "arcana": 1,
                "history": -1,
                "nature": -1,
                "religion": -1,
                "perception": 5,
                "insight": 5,
                "animal_handling": 3,
                "medicine": 3,
                "survival": 3,
                "persuasion": 2,
                "deception": 0,
                "intimidation": 0,
                "performance": 0,
            }
            desired_abilities = {"str": 8, "dex": 17, "con": 14, "int": 8, "wis": 16, "cha": 10}
            desired_mods = {"str": -1, "dex": 3, "con": 2, "int": -1, "wis": 3, "cha": 0}
            if preview_entity.source_ref != desired_source_ref:
                preview_entity.source_ref = desired_source_ref
                changed = True
            if preview_entity.skill_training != desired_skill_training:
                preview_entity.skill_training = desired_skill_training
                changed = True
            if preview_entity.ac != 16:
                preview_entity.ac = 16
                changed = True
            desired_speed = {"walk": 40, "remaining": 40}
            if preview_entity.speed != desired_speed:
                preview_entity.speed = desired_speed
                changed = True
            if preview_entity.ability_scores != desired_abilities:
                preview_entity.ability_scores = desired_abilities
                changed = True
            desired_class_features = {"monk": {"level": 5}}
            if preview_entity.class_features != desired_class_features:
                preview_entity.class_features = desired_class_features
                changed = True
            if preview_entity.ability_mods != desired_mods:
                preview_entity.ability_mods = desired_mods
                changed = True
            if preview_entity.proficiency_bonus != 3:
                preview_entity.proficiency_bonus = 3
                changed = True
            if preview_entity.save_proficiencies != ["str", "dex"]:
                preview_entity.save_proficiencies = ["str", "dex"]
                changed = True
            if preview_entity.skill_modifiers != desired_skill_modifiers:
                preview_entity.skill_modifiers = desired_skill_modifiers
                changed = True
            if isinstance(preview_entity.equipped_armor, dict):
                preview_entity.equipped_armor = None
                changed = True
            if isinstance(preview_entity.equipped_shield, dict):
                preview_entity.equipped_shield = None
                changed = True
            desired_weapons = [
                {
                    "weapon_id": "dagger",
                    "name": "匕首",
                    "category": "simple",
                    "kind": "melee",
                    "damage": [{"formula": "1d4", "type": "piercing"}],
                    "properties": ["finesse", "light", "thrown"],
                    "range": {"normal": 5, "long": 5},
                    "thrown_range": {"normal": 20, "long": 60},
                    "mastery": "迅击",
                }
            ]
            if preview_entity.weapons != desired_weapons:
                preview_entity.weapons = desired_weapons
                changed = True
            if not getattr(preview_entity, "inventory", []):
                preview_entity.inventory = [
                    {"name": "链条", "quantity": 1},
                    {"name": "绳索", "quantity": 1},
                    {"name": "铁钉", "quantity": 10},
                    {"name": "火绒盒", "quantity": 1},
                ]
                changed = True
            if not isinstance(getattr(preview_entity, "currency", None), dict) or not preview_entity.currency:
                preview_entity.currency = {"gp": 127}
                changed = True
            if changed:
                repository.save(encounter)
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


def build_empty_player_sheet() -> dict[str, object]:
    return {
        "summary": {
            "name": "",
            "class_name": "",
            "subclass_name": "",
            "level": None,
            "hp_current": None,
            "hp_max": None,
            "ac": None,
            "speed": None,
            "spell_save_dc": None,
            "spell_attack_bonus": None,
            "portrait_url": None,
        },
        "abilities": [],
        "tabs": {
            "skills": [],
            "equipment": {
                "weapons": [],
                "armor": {
                    "title": "穿戴护甲",
                    "items": [],
                },
                "backpacks": [],
            },
            "extras": {
                "placeholder_title": "后续追加",
                "placeholder_body": "后续会加入特性、状态、资源与法术相关信息.",
            },
        },
    }


def _render_player_sheet_summary_markup(summary: dict[str, object] | None) -> str:
    summary = summary if isinstance(summary, dict) else {}
    name = summary.get("name") or "未命名角色"
    class_name = summary.get("class_name") or "未知职业"
    subclass_name = summary.get("subclass_name")
    class_display = subclass_name or class_name
    level = summary.get("level")
    hp_current = summary.get("hp_current")
    hp_max = summary.get("hp_max")
    ac = summary.get("ac")
    speed = summary.get("speed")
    spell_save_dc = summary.get("spell_save_dc")
    spell_attack_bonus = summary.get("spell_attack_bonus")
    hp_fill = 0.0
    if isinstance(hp_current, (int, float)) and isinstance(hp_max, (int, float)) and hp_max > 0:
        hp_fill = max(0.0, min(100.0, (float(hp_current) / float(hp_max)) * 100.0))

    def render_value(value: object, *, suffix: str = "") -> str:
        if value is None:
            return f"--{suffix}"
        return f"{value}{suffix}"

    spell_attack_text = render_value(
        f"+{spell_attack_bonus}" if isinstance(spell_attack_bonus, int) and spell_attack_bonus > 0 else spell_attack_bonus
    )

    return (
        f'<div class="player-sheet-name">{name}</div>'
        f'<div class="player-sheet-class">{class_display} · {render_value(level, suffix="级")}</div>'
        '<div class="player-sheet-summary-grid">'
        f'<article class="player-sheet-summary-stat player-sheet-summary-stat--primary" style="--hp-fill:{hp_fill:.1f}%;">'
        '<span class="player-sheet-summary-stat-label">HP</span>'
        f'<strong class="player-sheet-summary-stat-value">{render_value(hp_current)} / {render_value(hp_max)}</strong>'
        '<span class="player-sheet-summary-stat-note">当前生命</span>'
        "</article>"
        '<article class="player-sheet-summary-stat">'
        '<span class="player-sheet-summary-stat-label">AC</span>'
        f'<strong class="player-sheet-summary-stat-value">{render_value(ac)}</strong>'
        '<span class="player-sheet-summary-stat-note">防御等级</span>'
        "</article>"
        '<article class="player-sheet-summary-stat">'
        '<span class="player-sheet-summary-stat-label">速度</span>'
        f'<strong class="player-sheet-summary-stat-value">{render_value(speed, suffix=" 尺")}</strong>'
        '<span class="player-sheet-summary-stat-note">当前移动</span>'
        "</article>"
        "</div>"
        f'<div class="player-sheet-spell">法术豁免 {render_value(spell_save_dc)} · 法术攻击 {spell_attack_text}</div>'
    )


def build_player_sheet_from_state(initial_state: dict[str, object] | None) -> dict[str, object]:
    empty_sheet = build_empty_player_sheet()
    if not isinstance(initial_state, dict):
        return empty_sheet
    player_sheet = initial_state.get("player_sheet_source")
    if isinstance(player_sheet, dict):
        return player_sheet
    return empty_sheet


def render_player_sheet_shell(player_sheet: dict[str, object], *, embedded: bool = False) -> str:
    summary = player_sheet.get("summary", {}) if isinstance(player_sheet, dict) else {}
    shell_class = "player-sheet-shell is-embedded" if embedded else "player-sheet-shell"
    return (
        f'<section class="{shell_class}" data-role="player-sheet-shell">'
        '<div class="player-sheet-grid">'
        '<aside class="player-sheet-portrait" data-role="player-sheet-portrait">'
        '<div class="player-sheet-portrait-frame">'
        '<div class="player-sheet-portrait-mark"></div>'
        '<div class="player-sheet-portrait-label">主角头像</div>'
        "</div>"
        "</aside>"
        '<div class="player-sheet-main">'
        f'<div class="player-sheet-summary" data-role="player-sheet-summary">{_render_player_sheet_summary_markup(summary)}</div>'
        '<div class="player-sheet-abilities" data-role="player-sheet-abilities"></div>'
        '<div class="player-sheet-tabs" data-role="player-sheet-tabs"></div>'
        '<div class="player-sheet-panel" data-role="player-sheet-panel"></div>'
        "</div>"
        "</div>"
        "</section>"
    )


def render_template_tools_shell() -> str:
    return (
        '<section class="template-tools" data-role="template-tools">'
        '<div class="template-tools__heading">'
        "<strong>样板快照</strong>"
        "<span>保存当前遭遇，方便随时回退</span>"
        "</div>"
        '<div class="template-tools__controls">'
        '<input type="text" class="template-tools__input" data-role="template-name-input" placeholder="输入样板名，如：礼拜堂稳定版" />'
        '<button type="button" class="template-tools__button" data-action="save-template">保存样板</button>'
        '<select class="template-tools__select" data-role="template-select"><option value="">选择样板</option></select>'
        '<button type="button" class="template-tools__button" data-action="restore-template">恢复当前遭遇</button>'
        '<button type="button" class="template-tools__button" data-action="clone-template">复制新遭遇</button>'
        "</div>"
        '<div class="template-tools__status" data-role="template-status">尚未保存样板。</div>'
        "</section>"
    )


def inject_player_sheet_into_battlemap_html(battlemap_html: str, player_sheet_shell: str) -> str:
    role_card_start = battlemap_html.find(
        '<section class="sidebar-card sidebar-block hud-panel"><h3 class="sidebar-label">角色卡</h3>'
    )
    layout_close = battlemap_html.find("</aside></div></section>")
    if role_card_start < 0 or layout_close < 0:
        return battlemap_html + player_sheet_shell

    role_card_end = battlemap_html.find("</div></section>", role_card_start)
    if role_card_end < 0:
        return battlemap_html + player_sheet_shell
    role_card_end += len("</div></section>")

    html_without_role_card = battlemap_html[:role_card_start] + battlemap_html[role_card_end:]
    html_without_role_card = html_without_role_card.replace(
        '<aside class="battlemap-sidebar">',
        '<aside class="battlemap-sidebar battlemap-sidebar--embedded-sheet">',
        1,
    )
    html_without_role_card = html_without_role_card.replace(
        '<section class="sidebar-card sidebar-block hud-panel"><h3 class="sidebar-label">地图图例</h3>',
        '<section class="sidebar-card sidebar-block hud-panel sidebar-card--legend"><h3 class="sidebar-label">地图图例</h3>',
        1,
    )
    footer_markup = (
        '<section class="battlemap-footer-panels">'
        f'<div class="battlemap-footer-main">{player_sheet_shell}</div>'
        "</section>"
    )
    return html_without_role_card.replace("</aside></div></section>", f"</aside></div>{footer_markup}</section>", 1)


def build_template_tools_styles() -> str:
    return (
        ".template-tools{display:grid;gap:12px;margin-bottom:16px;padding:16px 18px;border-radius:20px;"
        "background:linear-gradient(180deg,rgba(31,24,18,.92),rgba(10,12,16,.9));border:1px solid rgba(214,176,112,.18);"
        "box-shadow:0 18px 32px rgba(0,0,0,.22),inset 0 1px 0 rgba(255,236,205,.05);position:relative;z-index:1;}"
        ".template-tools__heading{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;}"
        ".template-tools__heading strong{font-size:16px;letter-spacing:.16em;text-transform:uppercase;color:#f1dfb8;}"
        ".template-tools__heading span{font-size:12px;color:#9b8a70;}"
        ".template-tools__controls{display:grid;grid-template-columns:minmax(220px,1.2fr) auto minmax(180px,1fr) auto auto;gap:10px;align-items:center;}"
        ".template-tools__input,.template-tools__select{width:100%;padding:11px 14px;border-radius:14px;border:1px solid rgba(214,176,112,.16);"
        "background:rgba(255,255,255,.04);color:#f3e6cc;outline:none;}"
        ".template-tools__button{appearance:none;border:none;padding:11px 15px;border-radius:14px;cursor:pointer;font-weight:800;"
        "color:#f7e6c6;background:linear-gradient(180deg,rgba(197,149,75,.3),rgba(110,76,32,.36));border:1px solid rgba(223,187,122,.3);}"
        ".template-tools__status{min-height:20px;font-size:12px;color:#c9b89b;}"
        "@media (max-width: 980px){.template-tools__controls{grid-template-columns:1fr 1fr;}.template-tools__button{width:100%;}}"
        "@media (max-width: 760px){.template-tools{padding:14px;}.template-tools__controls{grid-template-columns:1fr;}}"
    )


def build_player_sheet_styles() -> str:
    return (
        ".player-sheet-shell{position:relative;padding:18px;border-radius:28px;"
        "background:linear-gradient(180deg,rgba(29,24,19,.96),rgba(11,12,14,.98));"
        "border:1px solid rgba(214,176,112,.22);"
        "box-shadow:0 24px 48px rgba(0,0,0,.35),inset 0 1px 0 rgba(255,237,203,.05);}"
        ".player-sheet-grid{display:grid;grid-template-columns:170px minmax(0,1fr);gap:16px;align-items:stretch;}"
        ".player-sheet-shell.is-embedded{padding:0;border:none;border-radius:0;background:none;box-shadow:none;}"
        ".player-sheet-shell.is-embedded .player-sheet-grid{grid-template-columns:180px minmax(0,1fr);gap:12px;}"
        ".player-sheet-shell.is-embedded .player-sheet-portrait-frame{min-height:160px;padding:12px;}"
        ".player-sheet-shell.is-embedded .player-sheet-name{font-size:30px;}"
        ".player-sheet-shell.is-embedded .player-sheet-abilities{grid-template-columns:repeat(3,minmax(0,1fr));}"
        ".player-sheet-shell.is-embedded .player-sheet-panel{grid-template-columns:1fr;}"
        ".player-sheet-shell.is-embedded .player-sheet-tab{padding:9px 14px;font-size:12px;}"
        ".battlemap-sidebar.battlemap-sidebar--embedded-sheet{grid-template-rows:auto minmax(0,0.5fr) minmax(0,0.5fr);}"
        ".battlemap-sidebar--embedded-sheet .sidebar-card--activity{display:grid;grid-template-rows:auto minmax(0,1fr);min-height:0;}"
        ".battlemap-sidebar--embedded-sheet .sidebar-card--legend{display:grid;grid-template-rows:auto minmax(0,1fr);min-height:0;}"
        ".battlemap-sidebar--embedded-sheet .activity-feed{min-height:0;max-height:none;}"
        ".battlemap-sidebar--embedded-sheet .legend-list{min-height:0;overflow-y:auto;overscroll-behavior:contain;"
        "scrollbar-width:thin;scrollbar-color:rgba(143,174,220,.45) rgba(255,255,255,.04);}"
        ".battlemap-sidebar--embedded-sheet .legend-list::-webkit-scrollbar{width:10px;}"
        ".battlemap-sidebar--embedded-sheet .legend-list::-webkit-scrollbar-track{border-radius:999px;background:rgba(255,255,255,.04);}"
        ".battlemap-sidebar--embedded-sheet .legend-list::-webkit-scrollbar-thumb{border-radius:999px;background:linear-gradient(180deg,rgba(143,174,220,.62),rgba(86,114,158,.72));border:2px solid rgba(9,16,26,.88);}"
        ".battlemap-sidebar--embedded-sheet .legend-list::-webkit-scrollbar-thumb:hover{background:linear-gradient(180deg,rgba(173,203,247,.72),rgba(104,133,182,.82));}"
        ".battlemap-footer-panels{display:grid;grid-template-columns:minmax(0,1fr);gap:18px;align-items:start;"
        "margin-top:18px;position:relative;z-index:1;}"
        ".battlemap-footer-main{min-width:0;}"
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
        ".player-sheet-summary-grid{margin-top:14px;display:grid;grid-template-columns:minmax(0,1.45fr) repeat(2,minmax(120px,.8fr));gap:12px;}"
        ".player-sheet-summary-stat{position:relative;padding:14px 16px;border-radius:18px;"
        "background:linear-gradient(180deg,rgba(30,26,21,.94),rgba(12,12,14,.95));border:1px solid rgba(214,176,112,.16);"
        "box-shadow:inset 0 1px 0 rgba(255,242,214,.05);display:grid;gap:4px;align-content:start;min-height:92px;}"
        ".player-sheet-summary-stat::before{content:'';position:absolute;inset:0;border-radius:inherit;pointer-events:none;"
        "background:linear-gradient(135deg,rgba(255,255,255,.05),transparent 38%);opacity:.55;}"
        ".player-sheet-summary-stat--primary{background:linear-gradient(90deg,rgba(118,26,24,.94) 0,var(--hp-fill,0%),rgba(63,64,70,.86) var(--hp-fill,0%),rgba(38,39,44,.9) 100%),linear-gradient(180deg,rgba(82,24,20,.96),rgba(26,11,10,.96));"
        "border-color:rgba(255,151,135,.2);}"
        ".player-sheet-summary-stat-label{position:relative;z-index:1;font-size:11px;color:#bda98d;letter-spacing:.16em;text-transform:uppercase;}"
        ".player-sheet-summary-stat-value{position:relative;z-index:1;font-size:30px;line-height:1;color:#f7ead1;font-weight:900;letter-spacing:.01em;}"
        ".player-sheet-summary-stat--primary .player-sheet-summary-stat-value{color:#ffe4da;}"
        ".player-sheet-summary-stat-note{position:relative;z-index:1;font-size:12px;color:#96856f;letter-spacing:.04em;}"
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
        "border:1px solid rgba(214,176,112,.08);gap:10px;color:#eee2c8;}"
        ".player-sheet-skill-table{grid-column:1 / -1;display:grid;gap:10px;}"
        ".player-sheet-skill-header,.player-sheet-skill-row{display:grid;grid-template-columns:64px minmax(0,1fr) 96px 72px;align-items:center;}"
        ".player-sheet-skill-header{padding:0 12px;color:#9f8d70;font-size:11px;letter-spacing:.12em;text-transform:uppercase;}"
        ".player-sheet-skill-row{padding:10px 12px;}"
        ".player-sheet-skill-training{font-weight:900;color:#e5c98d;text-align:center;}"
        ".player-sheet-skill-ability{color:#b9ab92;font-size:13px;text-align:center;}"
        ".player-sheet-skill-total{text-align:right;}"
        ".player-sheet-equipment-row{grid-column:1 / -1;display:grid;grid-template-columns:minmax(0,1fr) 72px 92px 88px;}"
        ".player-sheet-equipment-layout{grid-column:1 / -1;display:grid;gap:14px;}"
        ".player-sheet-equipment-section{border-radius:18px;padding:14px 14px 16px;background:linear-gradient(180deg,rgba(35,28,21,.88),rgba(10,10,12,.9));"
        "border:1px solid rgba(214,176,112,.14);box-shadow:inset 0 1px 0 rgba(255,235,204,.05);}"
        ".player-sheet-equipment-heading{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:12px;}"
        ".player-sheet-equipment-heading strong{font-size:15px;letter-spacing:.18em;text-transform:uppercase;color:#f0dfbc;}"
        ".player-sheet-equipment-heading span{font-size:11px;color:#9f8d70;letter-spacing:.12em;text-transform:uppercase;}"
        ".player-sheet-equipment-table{display:grid;gap:10px;}"
        ".player-sheet-equipment-card{padding:12px 14px;border-radius:16px;background:rgba(255,255,255,.03);border:1px solid rgba(214,176,112,.1);}"
        ".player-sheet-equipment-card + .player-sheet-equipment-card{margin-top:0;}"
        ".player-sheet-equipment-topline{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;}"
        ".player-sheet-equipment-name{font-size:18px;font-weight:800;color:#f6e9cf;letter-spacing:.01em;}"
        ".player-sheet-equipment-badge{display:inline-flex;align-items:center;padding:4px 10px;border-radius:999px;background:rgba(216,179,106,.12);"
        "border:1px solid rgba(216,179,106,.2);font-size:11px;color:#e4c489;letter-spacing:.12em;text-transform:uppercase;}"
        ".player-sheet-equipment-properties{margin-top:8px;color:#cdbb9d;font-size:13px;line-height:1.6;}"
        ".player-sheet-equipment-stats{margin-top:12px;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;}"
        ".player-sheet-equipment-stat{padding:10px 8px;border-radius:12px;background:rgba(0,0,0,.18);border:1px solid rgba(214,176,112,.08);text-align:center;}"
        ".player-sheet-equipment-stat-label{display:block;font-size:10px;color:#8f7f67;letter-spacing:.1em;text-transform:uppercase;}"
        ".player-sheet-equipment-stat-value{display:block;margin-top:5px;font-size:14px;font-weight:800;color:#f5e6c8;}"
        ".player-sheet-armor-table{display:grid;gap:10px;}"
        ".player-sheet-armor-row{display:grid;grid-template-columns:minmax(0,1.4fr) 96px 84px 84px;gap:10px;align-items:center;padding:12px 14px;border-radius:16px;background:rgba(255,255,255,.03);border:1px solid rgba(214,176,112,.1);}"
        ".player-sheet-armor-cell{display:grid;gap:4px;}"
        ".player-sheet-armor-name{font-size:17px;font-weight:800;color:#f6e9cf;}"
        ".player-sheet-armor-sub{font-size:11px;color:#99886d;letter-spacing:.1em;text-transform:uppercase;}"
        ".player-sheet-pack-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;}"
        ".player-sheet-pack-item{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;border-radius:14px;"
        "background:rgba(255,255,255,.03);border:1px solid rgba(214,176,112,.08);color:#eee2c8;}"
        ".player-sheet-pack-gold{display:inline-flex;align-items:center;gap:8px;padding:6px 12px;border-radius:999px;background:rgba(216,179,106,.12);border:1px solid rgba(216,179,106,.2);color:#f0d48b;font-weight:800;}"
        ".player-sheet-empty{grid-column:1 / -1;padding:14px;border-radius:14px;background:rgba(255,255,255,.03);"
        "border:1px solid rgba(214,176,112,.08);color:#d8c8aa;}"
        ".player-sheet-empty p{margin:8px 0 0;color:#a8997f;}"
        "@media (max-width: 1080px){.player-sheet-grid,.player-sheet-shell.is-embedded .player-sheet-grid{grid-template-columns:1fr;}.player-sheet-portrait-frame{min-height:220px;}.player-sheet-summary-grid{grid-template-columns:repeat(3,minmax(0,1fr));}.player-sheet-panel{grid-template-columns:repeat(2,minmax(0,1fr));}.battlemap-footer-panels{grid-template-columns:1fr;}.player-sheet-equipment-stats{grid-template-columns:repeat(4,minmax(0,1fr));}}"
        "@media (max-width: 760px){.player-sheet-shell{padding:16px;}.player-sheet-summary-grid{grid-template-columns:1fr;}.player-sheet-summary-stat{min-height:0;}.player-sheet-summary-stat-value{font-size:24px;}.player-sheet-abilities{grid-template-columns:repeat(2,minmax(0,1fr));}.player-sheet-panel{grid-template-columns:1fr;}.player-sheet-equipment-row{grid-template-columns:1fr 64px 88px 76px;}.player-sheet-equipment-stats,.player-sheet-pack-grid{grid-template-columns:repeat(2,minmax(0,1fr));}.player-sheet-armor-row{grid-template-columns:minmax(0,1fr) repeat(3,72px);}.player-sheet-skill-header,.player-sheet-skill-row{grid-template-columns:48px minmax(0,1fr) 72px 56px;}}"
    )


def build_player_sheet_runtime_script(player_sheet: dict[str, object]) -> str:
    player_sheet_json = json.dumps(player_sheet, ensure_ascii=False)
    player_sheet_shell = json.dumps(render_player_sheet_shell(player_sheet, embedded=True), ensure_ascii=False)
    return (
        f"window.__PLAYER_SHEET_DEFAULTS__ = {player_sheet_json};"
        f"window.__PLAYER_SHEET_SHELL__ = {player_sheet_shell};"
        "window.__PLAYER_SHEET_ACTIVE_TAB__ = 'skills';"
        "window.normalizePlayerSheet = function(candidate){"
        "var fallback=window.__PLAYER_SHEET_DEFAULTS__||{};"
        "var source=(candidate&&typeof candidate==='object')?candidate:{};"
        "var merged=Object.assign({}, fallback, source);"
        "var fallbackSummary=(fallback&&fallback.summary&&typeof fallback.summary==='object')?fallback.summary:{};"
        "var sourceSummary=(source&&source.summary&&typeof source.summary==='object')?source.summary:{};"
        "var fallbackTabs=(fallback&&fallback.tabs&&typeof fallback.tabs==='object')?fallback.tabs:{};"
        "var sourceTabs=(source&&source.tabs&&typeof source.tabs==='object')?source.tabs:{};"
        "merged.summary=Object.assign({}, fallbackSummary, sourceSummary);"
        "merged.abilities=Array.isArray(source.abilities)?source.abilities:(Array.isArray(fallback.abilities)?fallback.abilities:[]);"
        "merged.tabs=Object.assign({}, fallbackTabs, sourceTabs);"
        "return merged;"
        "};"
        "window.buildPlayerSheet = function(nextState){"
        "if(nextState&&typeof nextState==='object'&&nextState.player_sheet_source&&typeof nextState.player_sheet_source==='object'){"
        "return window.normalizePlayerSheet(nextState.player_sheet_source);"
        "}"
        "return window.normalizePlayerSheet(window.__PLAYER_SHEET_DEFAULTS__);"
        "};"
        "window.__PLAYER_SHEET__ = window.buildPlayerSheet(window.__BATTLEMAP_STATE__);"
        "window.mountPlayerSheet = function(){"
        "var slot=document.querySelector('.battlemap-footer-main');"
        "if(!slot){return false;}"
        "if(!slot.querySelector('[data-role=\"player-sheet-shell\"]')){slot.innerHTML=window.__PLAYER_SHEET_SHELL__;}"
        "return true;"
        "};"
        "window.formatSignedModifier = function(value){"
        "if(typeof value!=='number'){return '--';}"
        "if(value>0){return '+' + value;}"
        "if(value===0){return '0';}"
        "return String(value);"
        "};"
        "window.renderPlayerSheetLegacyEquipment = function(items){"
        "return (items||[]).map(function(item){"
        "return '<div class=\"player-sheet-equipment-row\">' + "
        "'<strong>' + item.name + '</strong>' + "
        "'<span>' + window.formatSignedModifier(item.attack_bonus) + '</span>' + "
        "'<span>' + item.damage + '</span>' + "
        "'<span>' + (item.mastery||'--') + '</span>' + "
        "'</div>';"
        "}).join('') || '<div class=\"player-sheet-empty\">暂无装备数据</div>';"
        "};"
        "window.renderPlayerSheetStructuredEquipment = function(equipment){"
        "var weapons=(equipment&&Array.isArray(equipment.weapons))?equipment.weapons:[];"
        "var armor=(equipment&&equipment.armor&&typeof equipment.armor==='object')?equipment.armor:null;"
        "var backpacks=(equipment&&Array.isArray(equipment.backpacks))?equipment.backpacks:[];"
        "var weaponHtml=weapons.map(function(item){"
        "return '<article class=\"player-sheet-equipment-card\">' + "
        "'<div class=\"player-sheet-equipment-topline\"><strong class=\"player-sheet-equipment-name\">' + (item.name||'未命名武器') + '</strong>' + "
        "'<span class=\"player-sheet-equipment-badge\">精通 ' + (item.mastery||'--') + '</span></div>' + "
        "'<div class=\"player-sheet-equipment-properties\">' + (item.properties||'无') + '</div>' + "
        "'<div class=\"player-sheet-equipment-stats\">' + "
        "'<div class=\"player-sheet-equipment-stat\"><span class=\"player-sheet-equipment-stat-label\">熟练</span><span class=\"player-sheet-equipment-stat-value\">' + (item.proficient||'--') + '</span></div>' + "
        "'<div class=\"player-sheet-equipment-stat\"><span class=\"player-sheet-equipment-stat-label\">攻击骰</span><span class=\"player-sheet-equipment-stat-value\">' + (item.attack_display||item.attack_die||'--') + '</span></div>' + "
        "'<div class=\"player-sheet-equipment-stat\"><span class=\"player-sheet-equipment-stat-label\">伤害骰</span><span class=\"player-sheet-equipment-stat-value\">' + (item.damage_display||item.damage_die||'--') + '</span></div>' + "
        "'<div class=\"player-sheet-equipment-stat\"><span class=\"player-sheet-equipment-stat-label\">类型</span><span class=\"player-sheet-equipment-stat-value\">' + (item.damage_type||'--') + '</span></div>' + "
        "'</div></article>';"
        "}).join('') || '<div class=\"player-sheet-empty\">暂无武器数据</div>';"
        "var armorHtml='';"
        "if(armor){var armorItems=Array.isArray(armor.items)?armor.items:[];"
        "armorHtml='<div class=\"player-sheet-equipment-heading\"><strong>' + (armor.title||'穿戴护甲') + '</strong><span>防御配置</span></div>' + "
        "'<div class=\"player-sheet-armor-table\">' + "
        "(armorItems.map(function(item){return '<div class=\"player-sheet-armor-row\">' + "
        "'<div class=\"player-sheet-armor-cell\"><strong class=\"player-sheet-armor-name\">' + (item.name||'--') + '</strong><span class=\"player-sheet-armor-sub\">已装备</span></div>' + "
        "'<div class=\"player-sheet-equipment-stat\"><span class=\"player-sheet-equipment-stat-label\">属性</span><span class=\"player-sheet-equipment-stat-value\">' + (item.category||'--') + '</span></div>' + "
        "'<div class=\"player-sheet-equipment-stat\"><span class=\"player-sheet-equipment-stat-label\">防御</span><span class=\"player-sheet-equipment-stat-value\">' + (item.ac||'--') + '</span></div>' + "
        "'<div class=\"player-sheet-equipment-stat\"><span class=\"player-sheet-equipment-stat-label\">敏捷</span><span class=\"player-sheet-equipment-stat-value\">' + (item.dex||'--') + '</span></div>' + "
        "'</div>';}).join('') || '<div class=\"player-sheet-empty\">暂无护甲数据</div>') + "
        "'</div>';}"
        "else{armorHtml='<div class=\"player-sheet-empty\">暂无护甲数据</div>';}"
        "var packsHtml=backpacks.map(function(pack){"
        "var items=Array.isArray(pack.items)?pack.items:[];"
        "return '<section class=\"player-sheet-equipment-section\">' + "
        "'<div class=\"player-sheet-equipment-heading\"><strong>' + (pack.name||'背包') + '</strong><span class=\"player-sheet-pack-gold\">' + ((pack.gold ?? '--') + ' GP') + '</span></div>' + "
        "'<div class=\"player-sheet-pack-grid\">' + "
        "(items.map(function(item){return '<div class=\"player-sheet-pack-item\"><span>' + (item.name||'未命名物品') + '</span><strong>' + (item.quantity||'--') + '</strong></div>';}).join('') || '<div class=\"player-sheet-empty\">暂无背包物品</div>') + "
        "'</div></section>';"
        "}).join('') || '<section class=\"player-sheet-equipment-section\"><div class=\"player-sheet-empty\">暂无背包数据</div></section>';"
        "return '<div class=\"player-sheet-equipment-layout\">' + "
        "'<section class=\"player-sheet-equipment-section\"><div class=\"player-sheet-equipment-heading\"><strong>武器</strong><span>攻击配置</span></div><div class=\"player-sheet-equipment-table\">' + weaponHtml + '</div></section>' + "
        "'<section class=\"player-sheet-equipment-section\"><div class=\"player-sheet-equipment-heading\"><strong>护甲</strong><span>防御配置</span></div>' + armorHtml + '</section>' + "
        "packsHtml + "
        "'</div>';"
        "};"
        "window.renderPlayerSheet = function(playerSheet){"
        "if(!window.mountPlayerSheet()){return playerSheet;}"
        "var summary=(playerSheet&&playerSheet.summary)||{};"
        "var hpFill=0;"
        "if(typeof summary.hp_current==='number'&&typeof summary.hp_max==='number'&&summary.hp_max>0){hpFill=Math.max(0,Math.min(100,(summary.hp_current/summary.hp_max)*100));}"
        "var summaryRoot=document.querySelector('[data-role=\"player-sheet-summary\"]');"
        "if(summaryRoot){summaryRoot.innerHTML='"
        "<div class=\"player-sheet-name\">' + (summary.name||'未命名角色') + '</div>' + "
        "'<div class=\"player-sheet-class\">' + ((summary.subclass_name||summary.class_name||'未知职业') + ' · ' + ((summary.level ?? '--') + '级')) + '</div>' + "
        "'<div class=\"player-sheet-summary-grid\">' + "
        "'<article class=\"player-sheet-summary-stat player-sheet-summary-stat--primary\" style=\"--hp-fill:' + hpFill.toFixed(1) + '%;\"><span class=\"player-sheet-summary-stat-label\">HP</span><strong class=\"player-sheet-summary-stat-value\">' + (summary.hp_current ?? '--') + ' / ' + (summary.hp_max ?? '--') + '</strong><span class=\"player-sheet-summary-stat-note\">当前生命</span></article>' + "
        "'<article class=\"player-sheet-summary-stat\"><span class=\"player-sheet-summary-stat-label\">AC</span><strong class=\"player-sheet-summary-stat-value\">' + (summary.ac ?? '--') + '</strong><span class=\"player-sheet-summary-stat-note\">防御等级</span></article>' + "
        "'<article class=\"player-sheet-summary-stat\"><span class=\"player-sheet-summary-stat-label\">速度</span><strong class=\"player-sheet-summary-stat-value\">' + (summary.speed ?? '--') + ' 尺</strong><span class=\"player-sheet-summary-stat-note\">当前移动</span></article>' + "
        "'</div>' + "
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
        "if(activeTab==='equipment'){var equipment=(playerSheet&&playerSheet.tabs&&playerSheet.tabs.equipment)||[];"
        "panelRoot.innerHTML=Array.isArray(equipment)?window.renderPlayerSheetLegacyEquipment(equipment):window.renderPlayerSheetStructuredEquipment(equipment);return;}"
        "if(activeTab==='extras'){var extras=(playerSheet&&playerSheet.tabs&&playerSheet.tabs.extras)||{};"
        "panelRoot.innerHTML='<div class=\"player-sheet-empty\"><strong>' + (extras.placeholder_title||'后续追加') + '</strong><p>' + (extras.placeholder_body||'后续会加入更多角色信息.') + '</p></div>';return;}"
        "var skills=((playerSheet&&playerSheet.tabs&&playerSheet.tabs.skills)||[]);"
        "panelRoot.innerHTML='<div class=\"player-sheet-skill-table\">' + "
        "'<div class=\"player-sheet-skill-header\"><span>熟练</span><span>技能</span><span>检定能力</span><span>总值</span></div>' + "
        "skills.map(function(item){return '<div class=\"player-sheet-skill-row\">' + "
        "'<span class=\"player-sheet-skill-training\">' + (item.training_indicator||'X') + '</span>' + "
        "'<span>' + item.label + '</span>' + "
        "'<span class=\"player-sheet-skill-ability\">' + (item.ability_label||'--') + '</span>' + "
        "'<strong class=\"player-sheet-skill-total\">' + window.formatSignedModifier(item.modifier) + '</strong>' + "
        "'</div>';}).join('') + "
        "'</div>';"
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


def build_template_tools_runtime_script(encounter_id: str) -> str:
    return (
        f"window.__BATTLEMAP_CURRENT_ENCOUNTER_ID__ = {json.dumps(encounter_id, ensure_ascii=False)};"
        "window.setTemplateStatus = function(message,isError){"
        "var node=document.querySelector('[data-role=\"template-status\"]');"
        "if(!node){return;}"
        "node.textContent=message||'';"
        "node.style.color=isError?'#ffb4a6':'#c9b89b';"
        "};"
        "window.renderEncounterTemplateOptions = function(templates){"
        "var select=document.querySelector('[data-role=\"template-select\"]');"
        "if(!select){return;}"
        "var currentValue=select.value;"
        "var options=['<option value=\"\">选择样板</option>'].concat((templates||[]).map(function(item){"
        "return '<option value=\"' + item.template_id + '\">' + item.name + '</option>';"
        "}));"
        "select.innerHTML=options.join('');"
        "if(currentValue){select.value=currentValue;}"
        "};"
        "window.loadEncounterTemplates = async function(){"
        "var response=await fetch('/api/encounter-templates',{cache:'no-store'});"
        "var payload=await response.json();"
        "if(!response.ok){throw new Error(payload.error||'failed to load templates');}"
        "window.__ENCOUNTER_TEMPLATES__=payload.templates||[];"
        "window.renderEncounterTemplateOptions(window.__ENCOUNTER_TEMPLATES__);"
        "return window.__ENCOUNTER_TEMPLATES__;"
        "};"
        "window.saveEncounterTemplate = async function(){"
        "var input=document.querySelector('[data-role=\"template-name-input\"]');"
        "var templateName=input&&typeof input.value==='string'?input.value.trim():'';"
        "if(!templateName){window.setTemplateStatus('请先输入样板名。',true);return null;}"
        "var response=await fetch('/api/encounter-templates',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({encounter_id:window.__BATTLEMAP_CURRENT_ENCOUNTER_ID__,name:templateName})});"
        "var payload=await response.json();"
        "if(!response.ok){throw new Error(payload.error||'failed to save template');}"
        "window.setTemplateStatus('已保存样板：' + payload.template.name,false);"
        "await window.loadEncounterTemplates();"
        "return payload.template;"
        "};"
        "window.restoreEncounterTemplate = async function(){"
        "var select=document.querySelector('[data-role=\"template-select\"]');"
        "var templateId=select&&typeof select.value==='string'?select.value:'';"
        "if(!templateId){window.setTemplateStatus('请先选择一个样板。',true);return null;}"
        "var response=await fetch('/api/encounter-templates/restore',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({template_id:templateId,target_encounter_id:window.__BATTLEMAP_CURRENT_ENCOUNTER_ID__})});"
        "var payload=await response.json();"
        "if(!response.ok){throw new Error(payload.error||'failed to restore template');}"
        "window.setTemplateStatus('已恢复样板：' + payload.template.name,false);"
        "if(payload.encounter_state&&typeof payload.encounter_state==='object'){window.applyEncounterState(payload.encounter_state);}"
        "return payload;"
        "};"
        "window.cloneEncounterFromTemplate = async function(){"
        "var select=document.querySelector('[data-role=\"template-select\"]');"
        "var templateId=select&&typeof select.value==='string'?select.value:'';"
        "if(!templateId){window.setTemplateStatus('请先选择一个样板。',true);return null;}"
        "var nextEncounterId=window.prompt('请输入新遭遇 ID','enc_clone_' + Date.now());"
        "if(!nextEncounterId){return null;}"
        "var nextEncounterName=window.prompt('请输入新遭遇名称','样板副本');"
        "var response=await fetch('/api/encounter-templates/create-encounter',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({template_id:templateId,encounter_id:nextEncounterId,encounter_name:nextEncounterName||''})});"
        "var payload=await response.json();"
        "if(!response.ok){throw new Error(payload.error||'failed to clone template');}"
        "window.setTemplateStatus('已创建新遭遇：' + payload.encounter.encounter_id,false);"
        "return payload;"
        "};"
        "document.addEventListener('click',function(event){"
        "var actionNode=event.target&&event.target.closest('[data-action]');"
        "if(!actionNode){return;}"
        "var action=actionNode.getAttribute('data-action');"
        "Promise.resolve().then(function(){"
        "if(action==='save-template'){return window.saveEncounterTemplate();}"
        "if(action==='restore-template'){return window.restoreEncounterTemplate();}"
        "if(action==='clone-template'){return window.cloneEncounterFromTemplate();}"
        "return null;"
        "}).catch(function(error){window.setTemplateStatus(error&&error.message?error.message:'操作失败',true);});"
        "});"
        "window.loadEncounterTemplates().catch(function(error){window.setTemplateStatus(error&&error.message?error.message:'无法加载样板列表',true);});"
    )


def render_localhost_battlemap_page(
    *,
    encounter_id: str,
    page_title: str,
    dev_reload_path: str | None = None,
    encounter: Encounter | None = None,
    initial_state: dict[str, object] | None = None,
) -> str:
    if initial_state is not None:
        player_sheet = build_player_sheet_from_state(initial_state)
        template_tools_html = render_template_tools_shell()
        battlemap_view = initial_state.get("battlemap_view")
        if not isinstance(battlemap_view, dict):
            battlemap_view = {}
        encounter_name = str(initial_state.get("encounter_name") or encounter_id)
        battlemap_html = str(battlemap_view.get("html") or "<section>等待战场数据同步.</section>")
        battlemap_html = inject_player_sheet_into_battlemap_html(
            battlemap_html,
            render_player_sheet_shell(player_sheet, embedded=True),
        )
        html = (
            "<!DOCTYPE html>"
            '<html lang="zh-CN">'
            "<head>"
            '<meta charset="utf-8" />'
            '<meta name="viewport" content="width=device-width, initial-scale=1" />'
            f"<title>{encounter_name}</title>"
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
            ".app-shell{display:grid;}"
            f"{build_template_tools_styles()}"
            f"{build_player_sheet_styles()}"
            "@media (max-width: 760px){.battlemap-preview{padding:16px 16px 28px;}}"
            "</style>"
            "</head>"
            "<body>"
            '<main class="battlemap-preview battlemap-app">'
            '<div class="app-shell">'
            f"{template_tools_html}"
            f'<div data-role="battlemap-view-root">{battlemap_html}</div>'
            "</div>"
            "</main>"
            "<script>"
            f"window.__BATTLEMAP_STATE__ = {json.dumps(initial_state, ensure_ascii=False)};"
            "window.__LAST_TOOL_RESULT__ = null;"
            "window.__LAST_TOOL_ERROR__ = null;"
            f"{build_template_tools_runtime_script(encounter_id)}"
            f"{build_player_sheet_runtime_script(player_sheet)}"
            "window.getEncounterState = function(){return window.__BATTLEMAP_STATE__;};"
            "window.getLastToolResult = function(){return window.__LAST_TOOL_RESULT__;};"
            "window.getLastToolError = function(){return window.__LAST_TOOL_ERROR__;};"
            "window.applyEncounterState = function(nextState){"
            "if(!nextState||typeof nextState !== 'object'){throw new Error('encounter state must be an object');}"
            "window.__BATTLEMAP_STATE__ = nextState;"
            "if(typeof nextState.encounter_id === 'string' && nextState.encounter_id){window.__BATTLEMAP_CURRENT_ENCOUNTER_ID__ = nextState.encounter_id;}"
            "window.__PLAYER_SHEET__=window.buildPlayerSheet(nextState);"
            "if(typeof nextState.encounter_name === 'string'){document.title = nextState.encounter_name;}"
            "if(nextState.battlemap_view&&typeof nextState.battlemap_view.html==='string'){"
            "var root=document.querySelector('[data-role=\"battlemap-view-root\"]');if(root){root.innerHTML=nextState.battlemap_view.html;}}"
            "window.renderPlayerSheet(window.__PLAYER_SHEET__);"
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
    template_repository: EncounterTemplateRepository | None = None
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
        if parsed.path == "/api/encounter-templates":
            self._serve_encounter_templates()
            return
        self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/encounter-templates":
            self._create_encounter_template()
            return
        if parsed.path == "/api/encounter-templates/restore":
            self._restore_encounter_template()
            return
        if parsed.path == "/api/encounter-templates/create-encounter":
            self._create_encounter_from_template()
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
            initial_state = GetEncounterState(self.repository).execute(encounter_id)
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

    def _serve_encounter_templates(self) -> None:
        try:
            template_repository = self._get_template_repository_or_raise()
        except ValueError as error:
            self._write_json_error(error, bad_request=500)
            return
        templates = ListEncounterTemplates(template_repository).execute()
        self._write_json_response(200, {"templates": templates})

    def _create_encounter_template(self) -> None:
        try:
            repository = self._get_repository_or_raise()
            template_repository = self._get_template_repository_or_raise()
            payload = self._read_json_body()
        except (ValueError, json.JSONDecodeError) as error:
            self._write_json_error(error, bad_request=400)
            return
        encounter_id = str(payload.get("encounter_id") or self.encounter_id)
        template_name = str(payload.get("name") or "")
        try:
            template = SaveEncounterTemplate(repository, template_repository).execute(
                encounter_id=encounter_id,
                template_name=template_name,
            )
        except ValueError as error:
            self._write_json_error(error, bad_request=404 if "not found" in str(error) else 409)
            return
        self._write_json_response(201, {"ok": True, "template": template})

    def _restore_encounter_template(self) -> None:
        try:
            repository = self._get_repository_or_raise()
            template_repository = self._get_template_repository_or_raise()
            payload = self._read_json_body()
        except (ValueError, json.JSONDecodeError) as error:
            self._write_json_error(error, bad_request=400)
            return
        template_id = str(payload.get("template_id") or "")
        target_encounter_id = str(payload.get("target_encounter_id") or self.encounter_id)
        try:
            template = template_repository.get(template_id)
            encounter = RestoreEncounterFromTemplate(repository, template_repository).execute(
                template_id=template_id,
                target_encounter_id=target_encounter_id,
            )
        except ValueError as error:
            self._write_json_error(error, bad_request=404 if "not found" in str(error) else 400)
            return
        encounter_state = GetEncounterState(repository).execute(target_encounter_id)
        self._write_json_response(
            200,
            {"ok": True, "template": template, "encounter": encounter.to_dict(), "encounter_state": encounter_state},
        )

    def _create_encounter_from_template(self) -> None:
        try:
            repository = self._get_repository_or_raise()
            template_repository = self._get_template_repository_or_raise()
            payload = self._read_json_body()
        except (ValueError, json.JSONDecodeError) as error:
            self._write_json_error(error, bad_request=400)
            return
        template_id = str(payload.get("template_id") or "")
        encounter_id = str(payload.get("encounter_id") or "")
        encounter_name = str(payload.get("encounter_name") or "")
        try:
            created = CreateEncounterFromTemplate(repository, template_repository).execute(
                template_id=template_id,
                encounter_id=encounter_id,
                encounter_name=encounter_name,
            )
        except ValueError as error:
            status_code = 404 if "not found" in str(error) else 409 if "already exists" in str(error) else 400
            self._write_json_error(error, bad_request=status_code)
            return
        self._write_json_response(201, {"ok": True, "encounter": created.to_dict()})

    def _get_repository_or_raise(self) -> EncounterRepository:
        if self.repository is None:
            raise ValueError("Repository not configured")
        return self.repository

    def _get_template_repository_or_raise(self) -> EncounterTemplateRepository:
        handler_cls = type(self)
        if self.repository is None:
            raise ValueError("Template repository not configured")
        if handler_cls.template_repository is not None:
            if handler_cls.template_repository._db_path.parent == self.repository._db_path.parent:
                return handler_cls.template_repository
            handler_cls.template_repository.close()
            handler_cls.template_repository = None
        template_db_path = self.repository._db_path.parent / "encounter_templates.json"
        handler_cls.template_repository = EncounterTemplateRepository(template_db_path)
        return handler_cls.template_repository

    def _read_json_body(self) -> dict[str, object]:
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length <= 0:
            return {}
        raw_body = self.rfile.read(content_length).decode("utf-8")
        if not raw_body.strip():
            return {}
        payload = json.loads(raw_body)
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _write_json_response(self, status_code: int, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _write_json_error(self, error: Exception, *, bad_request: int) -> None:
        self._write_json_response(bad_request, {"ok": False, "error": str(error)})


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
    BattlemapLocalhostHandler.template_repository = (
        EncounterTemplateRepository(repository._db_path.parent / "encounter_templates.json")
        if repository is not None
        else None
    )
    BattlemapLocalhostHandler.runtime_base_url = runtime_base_url
    BattlemapLocalhostHandler.page_title = "Battlemap Localhost"
    BattlemapLocalhostHandler.dev_reload_path = args.dev_reload_path
    BattlemapLocalhostHandler.encounter_id = encounter_id

    server = ThreadingHTTPServer((args.host, args.port), BattlemapLocalhostHandler)
    try:
        print(f"http://{args.host}:{args.port}")
        server.serve_forever()
    finally:
        if BattlemapLocalhostHandler.template_repository is not None:
            BattlemapLocalhostHandler.template_repository.close()
        if repository is not None:
            repository.close()
        server.server_close()


if __name__ == "__main__":
    main()
