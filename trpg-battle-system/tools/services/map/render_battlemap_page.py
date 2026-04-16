from __future__ import annotations

import json

from tools.models.encounter import Encounter
from tools.services.map.render_battlemap_view import RenderBattlemapView


class RenderBattlemapPage:
    """把 battlemap 片段包装成完整可打开的 HTML 页面。"""

    def __init__(
        self,
        battlemap_view_service: RenderBattlemapView | None = None,
    ):
        self.battlemap_view_service = battlemap_view_service or RenderBattlemapView()

    def execute(self, encounter: Encounter) -> str:
        spell_area_overlays = self._extract_spell_area_overlays(encounter)
        view = self.battlemap_view_service.execute(encounter, spell_area_overlays=spell_area_overlays)
        client_state = self._build_client_state(encounter, view, spell_area_overlays)

        return (
            "<!DOCTYPE html>"
            '<html lang="zh-CN">'
            "<head>"
            '<meta charset="utf-8" />'
            '<meta name="viewport" content="width=device-width, initial-scale=1" />'
            f"<title>{encounter.name} 战斗地图预览</title>"
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
            f'<span class="topbar-chip" data-role="map-name-chip">{encounter.map.name}</span>'
            f'<span class="topbar-chip topbar-chip--accent" data-role="round-chip">第 {encounter.round} 轮</span>'
            "</div>"
            '<div class="hero-grid">'
            '<div class="hero-copy hero-card">'
            f'<h1 data-role="encounter-title">{encounter.name}</h1>'
            f'<p data-role="map-description">{encounter.map.description}</p>'
            "</div>"
            '<div class="hero-facts facts">'
            f'<div class="fact"><span class="fact-label">地图尺寸</span><span class="fact-value" data-role="dimensions-value">{encounter.map.width} × {encounter.map.height}</span></div>'
            f'<div class="fact"><span class="fact-label">比例尺</span><span class="fact-value" data-role="grid-size-value">每格 {encounter.map.grid_size_feet} 尺</span></div>'
            f'<div class="fact"><span class="fact-label">当前轮次</span><span class="fact-value" data-role="round-value">第 {encounter.round} 轮</span></div>'
            "</div></div>"
            "</section>"
            f'<div data-role="battlemap-view-root">{view["html"]}</div>'
            "</div>"
            "</main>"
            "<script>"
            f"window.__BATTLEMAP_STATE__ = {json.dumps(client_state, ensure_ascii=False)};"
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

    def _build_client_state(
        self,
        encounter: Encounter,
        view: dict[str, object],
        spell_area_overlays: list[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "encounter_id": encounter.encounter_id,
            "encounter_name": encounter.name,
            "round": encounter.round,
            "battlemap_details": {
                "name": encounter.map.name,
                "description": encounter.map.description,
                "dimensions": f"{encounter.map.width} x {encounter.map.height} tiles",
                "grid_size": f"Each tile represents {encounter.map.grid_size_feet} feet",
            },
            "spell_area_overlays": spell_area_overlays,
            "battlemap_view": view,
        }

    def _extract_spell_area_overlays(self, encounter: Encounter) -> list[dict[str, object]]:
        overlays: list[dict[str, object]] = []
        for note in encounter.encounter_notes:
            if not isinstance(note, dict) or note.get("type") != "spell_area_overlay":
                continue
            payload = note.get("payload")
            if isinstance(payload, dict):
                overlays.append(dict(payload))
        return overlays[-1:]
