from __future__ import annotations

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity


class RenderBattlemapView:
    """把 encounter 渲染成更接近现代在线 TRPG 界面的网页 battlemap 视图。"""

    CLASS_EMOJI = {
        "barbarian": "🪓",
        "bard": "🎼",
        "cleric": "⛪",
        "druid": "🐻",
        "fighter": "🗡",
        "monk": "🥋",
        "paladin": "🛡",
        "ranger": "🏹",
        "rogue": "🫥",
        "sorcerer": "🧙‍♂️",
        "warlock": "⚡",
        "wizard": "📜",
    }
    SIDE_LABELS = {"ally": "友方", "enemy": "敌方", "neutral": "中立", "summon": "召唤"}
    CATEGORY_LABELS = {"pc": "角色", "npc": "同伴", "monster": "怪物", "summon": "召唤物", "hazard": "危险"}
    ZONE_PALETTE = (
        {
            "name": "紫晶封锁",
            "fill": "rgba(235,200,255,.3)",
            "border": "rgba(244,214,255,.82)",
            "edge": "rgba(235,200,255,.34)",
            "glow": "rgba(205,124,255,.32)",
            "glow_soft": "rgba(205,124,255,.24)",
        },
        {
            "name": "霜雾缓滞",
            "fill": "rgba(155,225,255,.28)",
            "border": "rgba(198,243,255,.84)",
            "edge": "rgba(155,225,255,.34)",
            "glow": "rgba(91,202,255,.28)",
            "glow_soft": "rgba(91,202,255,.2)",
        },
        {
            "name": "余烬灼域",
            "fill": "rgba(255,198,145,.28)",
            "border": "rgba(255,222,183,.84)",
            "edge": "rgba(255,198,145,.34)",
            "glow": "rgba(255,146,89,.28)",
            "glow_soft": "rgba(255,146,89,.2)",
        },
        {
            "name": "蚀绿瘴幕",
            "fill": "rgba(181,238,188,.26)",
            "border": "rgba(216,248,220,.84)",
            "edge": "rgba(181,238,188,.34)",
            "glow": "rgba(104,214,130,.28)",
            "glow_soft": "rgba(104,214,130,.2)",
        },
    )

    def execute(
        self,
        encounter: Encounter,
        recent_forced_movement: dict[str, object] | None = None,
        recent_turn_effects: list[dict[str, object]] | None = None,
        recent_activity: list[dict[str, object]] | None = None,
        spell_area_overlays: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        return {
            "title": encounter.name,
            "html": self._render_document(
                encounter,
                recent_forced_movement,
                recent_turn_effects,
                recent_activity,
                spell_area_overlays,
            ),
            "dimensions": {
                "width": encounter.map.width,
                "height": encounter.map.height,
                "grid_size_feet": encounter.map.grid_size_feet,
            },
        }

    def _render_document(
        self,
        encounter: Encounter,
        recent_forced_movement: dict[str, object] | None = None,
        recent_turn_effects: list[dict[str, object]] | None = None,
        recent_activity: list[dict[str, object]] | None = None,
        spell_area_overlays: list[dict[str, object]] | None = None,
    ) -> str:
        return (
            '<section class="battlemap-shell war-room battlefield-panel">'
            f"{self._render_styles(encounter)}"
            '<div class="war-room__chrome"></div>'
            '<div class="war-room__noise"></div>'
            f"{self._render_header(encounter)}"
            '<div class="battlemap-layout battlemap-frame">'
            f"{self._render_grid(encounter, recent_forced_movement, spell_area_overlays)}"
            f"{self._render_sidebar(encounter, recent_forced_movement, recent_turn_effects, recent_activity)}"
            "</div>"
            "</section>"
        )

    def _render_header(self, encounter: Encounter) -> str:
        return (
            '<header class="battlemap-header">'
            '<div class="battlemap-header__layout">'
            '<div class="battlemap-header__copy">'
            '<div class="battlemap-kicker">遭遇战术面板</div>'
            f"<h2>{encounter.name}</h2>"
            f"<p>{encounter.map.description}</p>"
            '<div class="battlemap-meta-strip">'
            f'<span class="meta-chip">地图 {encounter.map.width} × {encounter.map.height}</span>'
            f'<span class="meta-chip">比例 {encounter.map.grid_size_feet} 尺 / 格</span>'
            f'<span class="meta-chip meta-chip--accent">第 {encounter.round} 轮</span>'
            "</div>"
            "</div>"
            '<section class="header-initiative hud-panel">'
            '<div class="header-initiative__top"><h3 class="sidebar-label">先攻表</h3></div>'
            f'<div class="header-initiative__body">{self._render_initiative_table(encounter)}</div>'
            "</section>"
            "</div>"
            "</header>"
        )

    def _render_styles(self, encounter: Encounter) -> str:
        return (
            "<style>"
            ".battlemap-shell{"
            "--bg-0:#071019;--bg-1:#0d1825;--bg-2:#122133;--panel:rgba(11,20,32,.72);--panel-strong:rgba(14,24,37,.9);"
            "--line:rgba(158,182,214,.16);--line-soft:rgba(158,182,214,.08);--text:#ecf2ff;--muted:#93a5bf;--gold:#d8b36a;"
            "--ally:#8ec5ff;--enemy:#ff8177;--neutral:#afb7c4;--zone:#b082ff;"
            "--forced-highlight:rgba(111,212,255,.88);--forced-highlight-soft:rgba(111,212,255,.24);"
            "--forced-highlight-strong:rgba(204,242,255,.96);"
            "font-family:'Avenir Next','Segoe UI',sans-serif;color:var(--text);position:relative;overflow:hidden;"
            "padding:24px;border-radius:28px;border:1px solid rgba(164,187,220,.13);"
            "background:radial-gradient(circle at top left,rgba(61,103,174,.26),transparent 20%),"
            "radial-gradient(circle at top right,rgba(225,182,103,.1),transparent 18%),"
            "linear-gradient(180deg,#0d1520 0%,#0a1119 100%);"
            "box-shadow:0 40px 120px rgba(3,6,12,.58),inset 0 1px 0 rgba(255,255,255,.04);}"
            ".war-room__chrome,.war-room__noise{position:absolute;inset:0;pointer-events:none;}"
            ".war-room__chrome{background:linear-gradient(180deg,rgba(255,255,255,.06),transparent 22%),"
            "radial-gradient(circle at 16% 12%,rgba(116,157,255,.18),transparent 20%),"
            "radial-gradient(circle at 84% 14%,rgba(248,190,101,.1),transparent 16%);}"
            ".war-room__noise{opacity:.16;background-image:radial-gradient(rgba(255,255,255,.18) .7px,transparent .7px);background-size:22px 22px;mix-blend-mode:soft-light;}"
            ".battlemap-header{position:relative;z-index:1;margin-bottom:18px;padding:22px 24px 20px;border-radius:22px;"
            "background:linear-gradient(180deg,rgba(14,24,37,.92),rgba(10,18,28,.82));"
            "border:1px solid rgba(164,187,220,.12);box-shadow:inset 0 1px 0 rgba(255,255,255,.04),0 18px 40px rgba(3,8,16,.28);}"
            ".battlemap-header__layout{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(280px,.8fr);gap:18px;align-items:start;}"
            ".battlemap-header__copy{min-width:0;}"
            ".battlemap-kicker{display:inline-flex;align-items:center;padding:6px 12px;border-radius:999px;"
            "background:rgba(127,162,219,.14);border:1px solid rgba(127,162,219,.22);color:#dbe8ff;font-size:11px;letter-spacing:.18em;text-transform:uppercase;}"
            ".battlemap-header h2{margin:14px 0 8px;font-size:clamp(30px,4vw,44px);line-height:1;letter-spacing:-.04em;}"
            ".battlemap-header p{margin:0;max-width:64ch;color:var(--muted);line-height:1.65;}"
            ".battlemap-meta-strip{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px;}"
            ".meta-chip{display:inline-flex;align-items:center;min-height:34px;padding:0 14px;border-radius:999px;"
            "background:rgba(255,255,255,.04);border:1px solid rgba(164,187,220,.12);color:#d9e6fb;font-size:13px;}"
            ".meta-chip--accent{background:rgba(216,179,106,.12);border-color:rgba(216,179,106,.22);color:#f0d39c;}"
            ".header-initiative{position:relative;overflow:hidden;align-self:stretch;padding:16px;border-radius:20px;background:linear-gradient(180deg,rgba(16,27,41,.96),rgba(10,18,29,.92));border:1px solid rgba(164,187,220,.12);box-shadow:inset 0 1px 0 rgba(255,255,255,.03);}"
            ".header-initiative::before{content:'';position:absolute;inset:auto -10% 58% auto;width:160px;height:160px;background:radial-gradient(circle,rgba(91,136,217,.13),transparent 68%);pointer-events:none;}"
            ".header-initiative__top{position:relative;z-index:1;margin-bottom:10px;}"
            ".header-initiative__body{position:relative;z-index:1;max-height:208px;padding-right:6px;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:rgba(143,174,220,.45) rgba(255,255,255,.04);}"
            ".header-initiative__body::-webkit-scrollbar{width:10px;}"
            ".header-initiative__body::-webkit-scrollbar-track{border-radius:999px;background:rgba(255,255,255,.04);}"
            ".header-initiative__body::-webkit-scrollbar-thumb{border-radius:999px;background:linear-gradient(180deg,rgba(143,174,220,.62),rgba(86,114,158,.72));border:2px solid rgba(9,16,26,.88);}"
            ".header-initiative__body::-webkit-scrollbar-thumb:hover{background:linear-gradient(180deg,rgba(173,203,247,.72),rgba(104,133,182,.82));}"
            ".battlemap-layout{display:grid;grid-template-columns:minmax(0,1fr) 368px;gap:18px;align-items:stretch;position:relative;z-index:1;}"
            ".battlemap-frame{padding:0;background:none;}"
            ".battlemap-stage{min-width:0;}"
            ".tactical-surface{position:relative;overflow:hidden;border-radius:24px;background:linear-gradient(180deg,rgba(10,18,28,.94),rgba(7,13,21,.96));"
            "border:1px solid rgba(164,187,220,.12);box-shadow:0 20px 60px rgba(2,5,10,.42),inset 0 1px 0 rgba(255,255,255,.03);}"
            ".surface-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;padding:16px 18px 12px;border-bottom:1px solid rgba(164,187,220,.08);}"
            ".surface-title{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:#a8b8cf;margin-bottom:8px;}"
            ".surface-name{font-size:22px;font-weight:700;letter-spacing:-.03em;}"
            ".surface-copy{margin-top:6px;color:var(--muted);font-size:14px;line-height:1.6;max-width:40ch;}"
            ".entity-pills{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;}"
            ".entity-pill{display:inline-flex;align-items:center;gap:8px;padding:8px 12px;border-radius:999px;background:rgba(255,255,255,.04);"
            "border:1px solid rgba(164,187,220,.12);font-size:12px;color:#dce7fa;}"
            ".entity-pill strong{font-size:13px;font-weight:600;}"
            ".surface-body{position:relative;padding:14px;}"
            ".grid-sheen{position:absolute;inset:14px;border-radius:18px;pointer-events:none;"
            "background:radial-gradient(circle at 24% 18%,rgba(113,154,255,.12),transparent 24%),"
            "radial-gradient(circle at 74% 76%,rgba(216,179,106,.08),transparent 22%),"
            "linear-gradient(180deg,rgba(255,255,255,.04),transparent 24%);}"
            ".battlemap-grid-frame{position:relative;padding:2px;border-radius:20px;background:rgba(43,60,84,.52);box-shadow:inset 0 0 0 1px rgba(121,149,191,.18);}"
            ".battlemap-spell-overlays{position:absolute;inset:1px;pointer-events:none;z-index:3;overflow:hidden;border-radius:18px;}"
            ".battlemap-spell-overlay{position:absolute;left:calc((var(--overlay-x) - .5) * (100% / var(--map-width)));top:calc((var(--map-height) - var(--overlay-y) + .5) * (100% / var(--map-height)));width:calc(var(--overlay-radius) * 2 * (100% / var(--map-width)));height:calc(var(--overlay-radius) * 2 * (100% / var(--map-height)));transform:translate(-50%,-50%);border-radius:999px;border:2px solid rgba(255,186,132,.94);background:radial-gradient(circle,rgba(255,137,82,.24),rgba(255,137,82,.12) 54%,rgba(255,137,82,0) 72%);box-shadow:0 0 36px rgba(255,137,82,.24),inset 0 0 28px rgba(255,233,190,.12);}"
            ".battlemap-grid{position:relative;display:grid;width:100%;grid-template-columns: repeat("
            f"{encounter.map.width}"
            ", minmax(0, 1fr));gap:1px;padding:1px;border-radius:18px;overflow:hidden;"
            "background:rgba(165,191,228,.28);box-shadow:0 22px 48px rgba(0,0,0,.28),inset 0 0 0 1px rgba(210,228,255,.16);}"
            ".tile{position:relative;display:flex;align-items:center;justify-content:center;aspect-ratio:1/1;min-width:0;min-height:0;"
            "overflow:hidden;background:linear-gradient(180deg,#182433,#111927);font-size:clamp(10px,1.2vw,18px);}"
            ".tile::before{content:'';position:absolute;inset:0;background:linear-gradient(180deg,rgba(255,255,255,.045),rgba(255,255,255,0));pointer-events:none;}"
            ".tile::after{content:'';position:absolute;inset:0;border:1px solid rgba(214,228,255,.06);pointer-events:none;}"
            ".tile--downed{outline:2px solid rgba(232,86,86,.92);outline-offset:-2px;}"
            ".tile--dead{outline:2px solid rgba(144,150,158,.82);outline-offset:-2px;}"
            ".tile__terrain-art{position:absolute;inset:0;pointer-events:none;opacity:.78;z-index:0;}"
            ".tile__terrain-art--wall{background:linear-gradient(180deg,rgba(255,255,255,.08),transparent 42%),repeating-linear-gradient(135deg,rgba(255,255,255,.1) 0 5px,rgba(0,0,0,0) 5px 10px);}"
            ".tile__terrain-art--difficult{background:radial-gradient(circle at 40% 48%,rgba(130,213,238,.18),transparent 54%),radial-gradient(circle at 68% 62%,rgba(130,213,238,.12),transparent 42%);}"
            ".tile__terrain-art--high-ground{background:linear-gradient(180deg,rgba(255,226,168,.22),transparent 42%),repeating-linear-gradient(0deg,rgba(255,220,152,.08) 0 3px,rgba(0,0,0,0) 3px 8px);}"
            ".tile__terrain-art--zone{background:radial-gradient(circle at center,var(--zone-fill,rgba(235,200,255,.3)) 0,rgba(255,255,255,0) 70%);mix-blend-mode:screen;opacity:.66;}"
            ".tile-tooltip{position:absolute;left:50%;top:4px;transform:translate(-50%,-4px);opacity:0;pointer-events:none;z-index:4;"
            "transition:opacity .14s ease,transform .14s ease;}"
            ".tile-tooltip__content{display:inline-flex;align-items:center;min-height:28px;padding:0 10px;border-radius:8px;"
            "background:rgba(83,92,108,.92);border:1px solid rgba(214,228,255,.18);color:#eef4ff;font-size:12px;letter-spacing:.04em;"
            "box-shadow:0 8px 20px rgba(0,0,0,.32);white-space:nowrap;}"
            ".tile:hover .tile-tooltip,.tile:focus-visible .tile-tooltip{opacity:1;transform:translate(-50%,0);}"
            ".tile--wall{background:linear-gradient(180deg,#344052,#222a37);}"
            ".tile--wall::before{background:repeating-linear-gradient(135deg,rgba(255,255,255,.055) 0 5px,rgba(0,0,0,0) 5px 10px);opacity:.48;}"
            ".tile--difficult{background:linear-gradient(180deg,#1c3442,#152733);}"
            ".tile--difficult::before{background:radial-gradient(circle at 48% 52%,rgba(130,213,238,.14),transparent 56%);}"
            ".tile--high-ground{background:linear-gradient(180deg,#3f3426,#272016);}"
            ".tile--high-ground::before{background:linear-gradient(180deg,rgba(236,199,131,.18),rgba(236,199,131,0));}"
            ".tile--zone{box-shadow:inset 0 0 0 1px var(--zone-edge,rgba(235,200,255,.34));}"
            ".tile--zone::after{inset:2px;border-radius:8px;border:1px solid var(--zone-border,rgba(244,214,255,.82));"
            "background:var(--zone-fill,rgba(235,200,255,.3));box-shadow:0 0 18px var(--zone-glow,rgba(205,124,255,.32)),inset 0 0 22px var(--zone-glow-soft,rgba(205,124,255,.24));}"
            ".tile--forced-origin,.tile--forced-path{box-shadow:inset 0 0 0 2px var(--forced-highlight),0 0 18px var(--forced-highlight-soft);}"
            ".tile--forced-destination,.tile--forced-blocked{box-shadow:inset 0 0 0 2px var(--forced-highlight),0 0 18px var(--forced-highlight-soft),0 0 0 1px var(--forced-highlight-strong);}"
            ".tile.current-turn{z-index:2;box-shadow:inset 0 0 0 2px rgba(216,179,106,.8),0 0 0 1px rgba(216,179,106,.22),0 0 18px rgba(216,179,106,.22);}"
            ".tile__occupant{position:relative;z-index:1;line-height:1;}"
            ".token{display:grid;place-items:center;width:72%;height:72%;border-radius:999px;font-size:clamp(10px,1.15vw,16px);font-weight:700;"
            "box-shadow:0 12px 30px rgba(0,0,0,.34),inset 0 1px 0 rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.08);}"
            ".token--ally{background:radial-gradient(circle at 30% 25%,#d4edff 0,#8abef6 42%,#4c76c6 100%);color:#0d1830;}"
            ".token--enemy{background:radial-gradient(circle at 30% 25%,#ffc1ba 0,#cb6670 40%,#6b2431 100%);color:#fff3f1;}"
            ".token--neutral{background:radial-gradient(circle at 30% 25%,#dee4ea 0,#8893a3 40%,#515b69 100%);color:#09111c;}"
            ".tile__remains{position:relative;z-index:1;display:grid;place-items:center;width:72%;height:72%;border-radius:16px;font-size:clamp(12px,1.25vw,18px);"
            "color:#f5f1e6;background:radial-gradient(circle at 30% 25%,rgba(255,255,255,.1),rgba(148,136,117,.18) 52%,rgba(34,30,27,.42) 100%);"
            "border:1px solid rgba(255,255,255,.08);box-shadow:0 10px 24px rgba(0,0,0,.28);}"
            ".battlemap-sidebar{display:grid;gap:14px;height:100%;grid-template-rows:auto minmax(0,1fr) auto auto;}"
            ".sidebar-card,.sidebar-block{position:relative;overflow:hidden;padding:16px;border-radius:22px;background:linear-gradient(180deg,rgba(13,22,34,.92),rgba(9,16,26,.88));"
            "border:1px solid rgba(164,187,220,.12);box-shadow:0 16px 42px rgba(3,8,16,.28),inset 0 1px 0 rgba(255,255,255,.03);}"
            ".sidebar-card::before,.sidebar-block::before{content:'';position:absolute;inset:auto -20% 68% auto;width:180px;height:180px;background:radial-gradient(circle,rgba(91,136,217,.12),transparent 66%);pointer-events:none;}"
            ".hud-panel{position:relative;}"
            ".sidebar-card--activity{display:flex;flex-direction:column;min-height:100%;}"
            ".sidebar-label{margin:0 0 12px;font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#90a4c1;}"
            ".current-banner{display:grid;gap:12px;padding:14px;border-radius:18px;background:linear-gradient(180deg,rgba(26,38,57,.95),rgba(15,24,37,.95));"
            "border:1px solid rgba(164,187,220,.1);}"
            ".current-banner__row{display:flex;align-items:center;gap:12px;}"
            ".current-banner .hero-icon{display:grid;place-items:center;width:44px;height:44px;border-radius:14px;background:rgba(216,179,106,.14);font-size:24px;}"
            ".current-banner strong{display:block;font-size:20px;line-height:1.1;}"
            ".current-banner span{color:var(--muted);font-size:13px;}"
            ".current-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;}"
            ".current-stat{padding:10px 12px;border-radius:14px;background:rgba(255,255,255,.035);border:1px solid rgba(164,187,220,.08);}"
            ".current-stat b{display:block;font-size:15px;}.current-stat small{color:var(--muted);font-size:11px;letter-spacing:.08em;}"
            ".turn-list{display:grid;gap:8px;}"
            ".initiative-table{width:100%;border-collapse:collapse;font-size:14px;}"
            ".initiative-table th,.initiative-table td{padding:10px 6px;border-bottom:1px solid rgba(164,187,220,.16);text-align:left;}"
            ".initiative-table th{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#90a4c1;}"
            ".initiative-table tr.is-current td{color:#f2d59c;font-weight:700;}"
            ".character-cards{display:grid;gap:10px;}"
            ".character-card{padding:14px;border-radius:18px;background:linear-gradient(180deg,rgba(18,29,44,.96),rgba(11,19,30,.96));border:1px solid rgba(164,187,220,.1);}"
            ".character-card.is-current{box-shadow:0 0 0 1px rgba(216,179,106,.34),0 18px 34px rgba(0,0,0,.22);border-color:rgba(216,179,106,.22);}"
            ".character-card--downed{border-color:rgba(232,86,86,.5);box-shadow:0 0 0 1px rgba(232,86,86,.42),0 18px 34px rgba(58,8,8,.22);}"
            ".character-card--dead{border-color:rgba(144,150,158,.52);box-shadow:0 0 0 1px rgba(144,150,158,.42),0 18px 34px rgba(14,16,20,.36);}"
            ".character-card__top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:10px;}"
            ".character-card__identity{display:flex;align-items:center;gap:12px;}.character-card__icon{display:grid;place-items:center;width:38px;height:38px;border-radius:12px;background:rgba(255,255,255,.05);font-size:20px;}"
            ".character-card__name{font-weight:700;font-size:15px;}.character-card__meta{font-size:12px;color:var(--muted);letter-spacing:.03em;}"
            ".character-card__stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;font-size:13px;}"
            ".character-card__stats div{padding:10px 10px 8px;border-radius:12px;background:rgba(255,255,255,.035);border:1px solid rgba(164,187,220,.06);}"
            ".character-card__bar{height:8px;margin-top:10px;border-radius:999px;background:rgba(255,255,255,.06);overflow:hidden;}"
            ".character-card__bar > span{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,#70c1ff,#d8b36a);}"
            ".activity-feed{display:grid;gap:10px;max-height:320px;padding-right:6px;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:rgba(143,174,220,.45) rgba(255,255,255,.04);}"
            ".sidebar-card--activity .activity-feed{flex:1;min-height:0;max-height:none;align-content:start;}"
            ".activity-feed::-webkit-scrollbar{width:10px;}"
            ".activity-feed::-webkit-scrollbar-track{border-radius:999px;background:rgba(255,255,255,.04);}"
            ".activity-feed::-webkit-scrollbar-thumb{border-radius:999px;background:linear-gradient(180deg,rgba(143,174,220,.62),rgba(86,114,158,.72));border:2px solid rgba(9,16,26,.88);}"
            ".activity-feed::-webkit-scrollbar-thumb:hover{background:linear-gradient(180deg,rgba(173,203,247,.72),rgba(104,133,182,.82));}"
            ".activity-item{position:relative;padding:12px 12px 12px 14px;border-radius:16px;background:linear-gradient(180deg,rgba(20,31,47,.95),rgba(12,20,31,.96));border:1px solid rgba(164,187,220,.09);}"
            ".activity-item::before{content:'';position:absolute;left:0;top:12px;bottom:12px;width:3px;border-radius:999px;background:var(--activity-accent,rgba(124,184,255,.88));box-shadow:0 0 16px var(--activity-accent-soft,rgba(124,184,255,.28));}"
            ".activity-item--turn-effect{--activity-accent:rgba(183,136,255,.9);--activity-accent-soft:rgba(183,136,255,.26);}"
            ".activity-item--forced{--activity-accent:rgba(111,212,255,.9);--activity-accent-soft:rgba(111,212,255,.26);}"
            ".activity-item--round{--activity-accent:rgba(216,179,106,.9);--activity-accent-soft:rgba(216,179,106,.24);}"
            ".activity-item__label{display:inline-flex;align-items:center;min-height:24px;padding:0 10px;border-radius:999px;background:rgba(255,255,255,.04);border:1px solid rgba(164,187,220,.12);color:#dbe7fa;font-size:11px;letter-spacing:.12em;text-transform:uppercase;}"
            ".activity-item__summary{margin-top:10px;color:#edf3ff;font-size:13px;line-height:1.6;}"
            ".activity-item__empty{color:var(--muted);font-size:13px;line-height:1.6;}"
            ".legend-list{display:grid;gap:8px;margin:0;padding:0;list-style:none;font-size:13px;color:#d9e6fb;}"
            ".legend-list li{padding:10px 12px;border-radius:14px;background:rgba(255,255,255,.03);border:1px solid rgba(164,187,220,.08);}"
            ".legend-list__terrain{display:flex;align-items:flex-start;gap:10px;}"
            ".terrain-swatch{display:inline-flex;flex:0 0 auto;width:14px;height:14px;margin-top:2px;border-radius:4px;border:1px solid rgba(214,228,255,.24);box-shadow:inset 0 0 0 1px rgba(255,255,255,.05);}"
            ".terrain-swatch--wall{background:linear-gradient(180deg,#344052,#222a37);}"
            ".terrain-swatch--difficult{background:linear-gradient(180deg,#1c3442,#152733);}"
            ".terrain-swatch--high-ground{background:linear-gradient(180deg,#3f3426,#272016);}"
            ".legend-list__zone{display:flex;align-items:flex-start;gap:10px;}"
            ".zone-swatch{display:inline-flex;flex:0 0 auto;width:14px;height:14px;margin-top:2px;border-radius:999px;border:1px solid var(--zone-border,rgba(255,255,255,.5));background:var(--zone-fill,rgba(255,255,255,.2));box-shadow:0 0 12px var(--zone-glow,rgba(255,255,255,.2));}"
            ".legend-zone-copy strong{display:block;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#f1f6ff;margin-bottom:2px;}"
            "@media (max-width: 1280px){.battlemap-header__layout{grid-template-columns:1fr;}.battlemap-layout{grid-template-columns:1fr;}.battlemap-sidebar{grid-template-columns:repeat(2,minmax(0,1fr));}}"
            "@media (max-width: 860px){.surface-head{display:grid;}.entity-pills{justify-content:flex-start;}.battlemap-sidebar{grid-template-columns:1fr;}.battlemap-shell{padding:14px;}.battlemap-header{padding:18px;}.header-initiative__body{max-height:180px;}}"
            "</style>"
        )

    def _render_grid(
        self,
        encounter: Encounter,
        recent_forced_movement: dict[str, object] | None = None,
        spell_area_overlays: list[dict[str, object]] | None = None,
    ) -> str:
        cells: list[str] = [
            '<section class="battlemap-stage tactical-surface"><div class="surface-head"><div>'
            '<div class="surface-title">共享战场</div>'
            f'<div class="surface-name">{encounter.map.name}</div>'
            f'<div class="surface-copy">{encounter.map.description}</div>'
            "</div>"
            f'<div class="entity-pills">{self._render_entity_pills(encounter)}</div>'
            '</div><div class="surface-body"><div class="grid-sheen"></div><div class="battlemap-grid-frame"><div class="battlemap-grid">'
        ]
        current_entity_id = encounter.current_entity_id
        for y in range(encounter.map.height, 0, -1):
            for x in range(1, encounter.map.width + 1):
                entity = self._find_entity_at(encounter, x, y)
                remains = self._find_remains_at(encounter, x, y)
                classes = self._tile_classes(encounter, x, y, entity, current_entity_id, recent_forced_movement)
                zone_match = self._zone_for_cell(encounter, x, y)
                style = ""
                if zone_match is not None:
                    _, zone_index = zone_match
                    zone_style = self._zone_style(zone_index)
                    style = (
                        f' style="--zone-fill:{zone_style["fill"]};--zone-border:{zone_style["border"]};'
                        f'--zone-edge:{zone_style["edge"]};--zone-glow:{zone_style["glow"]};--zone-glow-soft:{zone_style["glow_soft"]};"'
                    )
                terrain_art = self._render_terrain_art(encounter, x, y, zone_match is not None)
                occupant = ""
                if entity is not None:
                    occupant = f'<span class="tile__occupant {self._occupant_class(entity)}">{self._occupant_symbol(entity)}</span>'
                elif remains is not None:
                    label = str(remains.get("label") or "残骸")
                    icon = str(remains.get("icon") or "💀")
                    occupant = f'<span class="tile__remains" title="{label}">{icon}</span>'
                tooltip = f'<span class="tile-tooltip"><span class="tile-tooltip__content">({x}, {y})</span></span>'
                cells.append(f'<div class="{classes}" data-x="{x}" data-y="{y}" tabindex="0"{style}>{terrain_art}{tooltip}{occupant}</div>')
        cells.append("</div>")
        cells.append(self._render_spell_area_overlays(encounter, spell_area_overlays))
        cells.append("</div></div></section>")
        return "".join(cells)

    def _render_spell_area_overlays(
        self,
        encounter: Encounter,
        spell_area_overlays: list[dict[str, object]] | None,
    ) -> str:
        if not isinstance(spell_area_overlays, list) or not spell_area_overlays:
            return ""
        items: list[str] = [
            f'<div class="battlemap-spell-overlays" style="--map-width:{encounter.map.width};--map-height:{encounter.map.height};">'
        ]
        for overlay in spell_area_overlays:
            if not isinstance(overlay, dict):
                continue
            if overlay.get("kind") != "spell_area_circle":
                continue
            target_point = overlay.get("target_point")
            radius_tiles = overlay.get("radius_tiles")
            if not isinstance(target_point, dict):
                continue
            x = target_point.get("x")
            y = target_point.get("y")
            if not isinstance(x, int) or not isinstance(y, int):
                continue
            if not isinstance(radius_tiles, (int, float)):
                continue
            spell_name = str(overlay.get("source_spell_name") or overlay.get("source_spell_id") or "法术区域")
            items.append(
                '<div class="battlemap-spell-overlay" '
                f'data-spell-name="{spell_name}" '
                f'style="--overlay-x:{x};--overlay-y:{y};--overlay-radius:{radius_tiles};"></div>'
            )
        items.append("</div>")
        return "".join(items)

    def _render_entity_pills(self, encounter: Encounter) -> str:
        allies = sum(1 for entity in encounter.entities.values() if entity.side == "ally")
        enemies = sum(1 for entity in encounter.entities.values() if entity.side == "enemy")
        zones = len(encounter.map.zones)
        return (
            f'<span class="entity-pill"><strong>{allies}</strong> 友方单位</span>'
            f'<span class="entity-pill"><strong>{enemies}</strong> 敌方单位</span>'
            f'<span class="entity-pill"><strong>{zones}</strong> 特殊区域</span>'
        )

    def _render_sidebar(
        self,
        encounter: Encounter,
        recent_forced_movement: dict[str, object] | None = None,
        recent_turn_effects: list[dict[str, object]] | None = None,
        recent_activity: list[dict[str, object]] | None = None,
    ) -> str:
        current_entity = encounter.entities.get(encounter.current_entity_id) if encounter.current_entity_id else None
        current_name = current_entity.name if current_entity is not None else "未指定"
        current_icon = self._occupant_symbol(current_entity) if current_entity is not None else "•"
        current_hp = self._hp_label(current_entity) if current_entity is not None else "-"
        current_ac = str(current_entity.ac) if current_entity is not None else "-"
        current_pos = self._position_label(current_entity) if current_entity is not None else "-"
        return (
            '<aside class="battlemap-sidebar">'
            '<section class="sidebar-card sidebar-block hud-panel"><h3 class="sidebar-label">回合焦点</h3>'
            '<div class="current-banner current-turn">'
            f'<div class="current-banner__row"><span class="hero-icon">{current_icon}</span><div><strong>{current_name}</strong><span>第 {encounter.round} 轮 · 当前行动者</span></div></div>'
            '<div class="current-stats">'
            f'<div class="current-stat"><small>生命</small><b>{current_hp}</b></div>'
            f'<div class="current-stat"><small>护甲</small><b>{current_ac}</b></div>'
            f'<div class="current-stat"><small>位置</small><b>{current_pos}</b></div>'
            "</div></div></section>"
            '<section class="sidebar-card sidebar-block hud-panel sidebar-card--activity"><h3 class="sidebar-label">战况记录</h3><div class="activity-feed">'
            f"{self._render_recent_activity(encounter, recent_forced_movement, recent_turn_effects, recent_activity)}"
            "</div></section>"
            '<section class="sidebar-card sidebar-block hud-panel"><h3 class="sidebar-label">角色卡</h3><div class="character-cards">'
            f"{self._render_character_cards(encounter)}"
            "</div></section>"
            '<section class="sidebar-card sidebar-block hud-panel"><h3 class="sidebar-label">地图图例</h3><ul class="legend-list">'
            "<li>🛡 / 📜 / 🏹：友方职业单位</li>"
            "<li>字母：敌方单位</li>"
            '<li class="legend-list__terrain"><span class="terrain-swatch terrain-swatch--wall"></span><span>墙壁：不可穿越并阻挡视线。</span></li>'
            '<li class="legend-list__terrain"><span class="terrain-swatch terrain-swatch--difficult"></span><span>困难地形：进入时需要额外移动。</span></li>'
            '<li class="legend-list__terrain"><span class="terrain-swatch terrain-swatch--high-ground"></span><span>高台：提供抬升站位与视野优势。</span></li>'
            "<li>区域：法术或持续效果范围</li>"
            f"{self._render_zone_legend(encounter)}"
            "</ul></section>"
            "</aside>"
        )

    def _render_recent_activity(
        self,
        encounter: Encounter,
        recent_forced_movement: dict[str, object] | None,
        recent_turn_effects: list[dict[str, object]] | None,
        recent_activity: list[dict[str, object]] | None,
    ) -> str:
        if isinstance(recent_activity, list) and recent_activity:
            return self._render_recent_activity_from_feed(encounter, recent_activity)

        items: list[str] = [
            (
                '<article class="activity-item activity-item--round">'
                '<div class="activity-item__label">当前轮次</div>'
                f'<div class="activity-item__summary">第 {encounter.round} 轮进行中，当前行动者：{self._current_entity_name(encounter)}。</div>'
                "</article>"
            )
        ]

        if isinstance(recent_turn_effects, list):
            for effect in recent_turn_effects[:3]:
                if not isinstance(effect, dict):
                    continue
                summary = effect.get("summary")
                if not isinstance(summary, str) or not summary.strip():
                    continue
                items.append(
                    '<article class="activity-item activity-item--turn-effect">'
                    '<div class="activity-item__label">自动效果</div>'
                    f'<div class="activity-item__summary">{summary.strip()}</div>'
                    "</article>"
                )

        if isinstance(recent_forced_movement, dict):
            summary = recent_forced_movement.get("summary")
            if isinstance(summary, str) and summary.strip():
                items.append(
                    '<article class="activity-item activity-item--forced">'
                    '<div class="activity-item__label">强制位移</div>'
                    f'<div class="activity-item__summary">{summary.strip()}</div>'
                    "</article>"
                )

        if len(items) == 1:
            items.append(
                '<article class="activity-item">'
                '<div class="activity-item__label">等待更新</div>'
                '<div class="activity-item__summary activity-item__empty">本回合暂未记录新的自动结算。</div>'
                "</article>"
            )
        return "".join(items)

    def _render_recent_activity_from_feed(
        self,
        encounter: Encounter,
        recent_activity: list[dict[str, object]],
    ) -> str:
        items: list[str] = [
            (
                '<article class="activity-item activity-item--round">'
                '<div class="activity-item__label">当前轮次</div>'
                f'<div class="activity-item__summary">第 {encounter.round} 轮进行中，当前行动者：{self._current_entity_name(encounter)}。</div>'
                "</article>"
            )
        ]

        for entry in recent_activity:
            if not isinstance(entry, dict):
                continue
            summary = entry.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                continue
            event_type = entry.get("event_type")
            items.append(
                f'<article class="activity-item {self._activity_item_class(event_type)}">'
                f'<div class="activity-item__label">{self._activity_label(event_type)}</div>'
                f'<div class="activity-item__summary">{summary.strip()}</div>'
                "</article>"
            )

        return "".join(items)

    def _activity_item_class(self, event_type: object) -> str:
        if event_type == "turn_effect_resolved":
            return "activity-item--turn-effect"
        if event_type == "forced_movement_resolved":
            return "activity-item--forced"
        return ""

    def _activity_label(self, event_type: object) -> str:
        mapping = {
            "movement_resolved": "移动",
            "attack_resolved": "攻击",
            "damage_applied": "伤害",
            "healing_applied": "治疗",
            "spell_declared": "施法",
            "saving_throw_resolved": "豁免",
            "forced_movement_resolved": "强制位移",
            "zone_effect_resolved": "区域效果",
            "turn_effect_resolved": "自动效果",
            "turn_ended": "回合结束",
            "spell_retargeted": "转移标记",
        }
        return mapping.get(str(event_type), "事件")

    def _render_initiative_table(self, encounter: Encounter) -> str:
        items: list[str] = []
        items.append('<table class="initiative-table"><thead><tr><th>先攻</th><th>单位</th><th>位置</th></tr></thead><tbody>')
        for entity_id in encounter.turn_order:
            entity = encounter.entities[entity_id]
            row_class = ' class="is-current"' if entity_id == encounter.current_entity_id else ""
            items.append(
                f'<tr{row_class}><td>{entity.initiative}</td><td>{self._occupant_symbol(entity)} {entity.name}</td>'
                f"<td>{self._position_label(entity)}</td></tr>"
            )
        items.append("</tbody></table>")
        return "".join(items)

    def _render_character_cards(self, encounter: Encounter) -> str:
        items: list[str] = []
        for entity_id in encounter.turn_order:
            entity = encounter.entities[entity_id]
            card_class = "character-card is-current" if entity_id == encounter.current_entity_id else "character-card"
            hp_label = self._hp_label(entity)
            if self._is_dead_entity(entity):
                card_class += " character-card--dead"
                hp_label = "死亡"
            if self._is_downed_entity(entity):
                card_class += " character-card--downed"
            items.append(
                f'<article class="{card_class}">'
                '<div class="character-card__top">'
                f'<div class="character-card__identity"><span class="character-card__icon">{self._occupant_symbol(entity)}</span>'
                f'<div><div class="character-card__name">{entity.name}</div><div class="character-card__meta">{self._side_label(entity.side)} · {self._category_label(entity.category)}</div></div></div>'
                f'<div class="character-card__meta">先攻 {entity.initiative}</div>'
                "</div>"
                '<div class="character-card__stats">'
                f'<div><strong>生命</strong><br/>{hp_label}</div>'
                f'<div><strong>AC</strong><br/>{entity.ac}</div>'
                f'<div><strong>位置</strong><br/>{self._position_label(entity)}</div>'
                "</div>"
                f'<div class="character-card__bar"><span style="width:{self._hp_percent(entity):.0f}%"></span></div>'
                "</article>"
            )
        return "".join(items)

    def _render_zone_legend(self, encounter: Encounter) -> str:
        items: list[str] = []
        for zone_index, zone in enumerate(encounter.map.zones):
            zone_style = self._zone_style(zone_index)
            zone_name = str(zone.get("name") or zone_style["name"]).strip()
            note = zone.get("note")
            if isinstance(note, str) and note.strip():
                items.append(
                    '<li class="legend-list__zone">'
                    f'<span class="zone-swatch" style="--zone-fill:{zone_style["fill"]};--zone-border:{zone_style["border"]};--zone-glow:{zone_style["glow"]};"></span>'
                    f'<span class="legend-zone-copy"><strong>{zone_name}</strong>区域效果：{note.strip()}</span>'
                    "</li>"
                )
        return "".join(items)

    def _render_terrain_art(self, encounter: Encounter, x: int, y: int, has_zone: bool) -> str:
        items: list[str] = []
        terrain_type = self._terrain_type_at(encounter, x, y)
        if terrain_type == "wall":
            items.append('<span class="tile__terrain-art tile__terrain-art--wall"></span>')
        elif terrain_type == "difficult_terrain":
            items.append('<span class="tile__terrain-art tile__terrain-art--difficult"></span>')
        elif terrain_type == "high_ground":
            items.append('<span class="tile__terrain-art tile__terrain-art--high-ground"></span>')
        if has_zone:
            items.append('<span class="tile__terrain-art tile__terrain-art--zone"></span>')
        return "".join(items)

    def _tile_classes(
        self,
        encounter: Encounter,
        x: int,
        y: int,
        entity: EncounterEntity | None,
        current_entity_id: str | None,
        recent_forced_movement: dict[str, object] | None = None,
    ) -> str:
        classes = ["tile"]
        for terrain in encounter.map.terrain:
            if terrain.get("x") != x or terrain.get("y") != y:
                continue
            terrain_type = terrain.get("type")
            if terrain_type == "wall":
                classes.append("tile--wall")
            elif terrain_type == "difficult_terrain":
                classes.append("tile--difficult")
            elif terrain_type == "high_ground":
                classes.append("tile--high-ground")

        if self._cell_in_zone(encounter, x, y):
            classes.append("tile--zone")
        forced_highlight = self._forced_movement_highlight(recent_forced_movement, x, y)
        if forced_highlight["is_origin"]:
            classes.append("tile--forced-origin")
        if forced_highlight["is_path"]:
            classes.append("tile--forced-path")
        if forced_highlight["is_destination"]:
            classes.append("tile--forced-destination")
        if forced_highlight["is_blocked"]:
            classes.append("tile--forced-blocked")
        if entity is not None:
            if self._is_dead_entity(entity):
                classes.append("tile--dead")
            elif self._is_downed_entity(entity):
                classes.append("tile--downed")
        if entity is not None and entity.entity_id == current_entity_id:
            classes.append("current-turn")
        return " ".join(classes)

    def _forced_movement_highlight(
        self,
        recent_forced_movement: dict[str, object] | None,
        x: int,
        y: int,
    ) -> dict[str, bool]:
        if not isinstance(recent_forced_movement, dict):
            return {"is_origin": False, "is_path": False, "is_destination": False, "is_blocked": False}
        cell = {"x": x, "y": y}
        start_position = recent_forced_movement.get("start_position")
        final_position = recent_forced_movement.get("final_position")
        resolved_path = recent_forced_movement.get("resolved_path")
        blocked = bool(recent_forced_movement.get("blocked", False))
        is_origin = start_position == cell
        is_destination = final_position == cell
        is_path = isinstance(resolved_path, list) and any(step == cell for step in resolved_path)
        is_blocked = blocked and is_destination
        return {
            "is_origin": is_origin,
            "is_path": is_path,
            "is_destination": is_destination,
            "is_blocked": is_blocked,
        }

    def _cell_in_zone(self, encounter: Encounter, x: int, y: int) -> bool:
        return self._zone_for_cell(encounter, x, y) is not None

    def _terrain_type_at(self, encounter: Encounter, x: int, y: int) -> str | None:
        for terrain in encounter.map.terrain:
            if terrain.get("x") == x and terrain.get("y") == y:
                terrain_type = terrain.get("type")
                if isinstance(terrain_type, str):
                    return terrain_type
        return None

    def _zone_for_cell(self, encounter: Encounter, x: int, y: int) -> tuple[dict[str, object], int] | None:
        for zone_index, zone in enumerate(encounter.map.zones):
            if [x, y] in zone.get("cells", []):
                return zone, zone_index
        return None

    def _zone_style(self, zone_index: int) -> dict[str, str]:
        return dict(self.ZONE_PALETTE[zone_index % len(self.ZONE_PALETTE)])

    def _find_entity_at(self, encounter: Encounter, x: int, y: int) -> EncounterEntity | None:
        for entity in encounter.entities.values():
            if entity.position["x"] == x and entity.position["y"] == y:
                return entity
        return None

    def _find_remains_at(self, encounter: Encounter, x: int, y: int) -> dict[str, object] | None:
        for remains in getattr(encounter.map, "remains", []):
            position = remains.get("position")
            if not isinstance(position, dict):
                continue
            if position.get("x") == x and position.get("y") == y:
                return remains
        return None

    def _current_entity_name(self, encounter: Encounter) -> str:
        if encounter.current_entity_id is None:
            return "未指定"
        entity = encounter.entities.get(encounter.current_entity_id)
        if entity is None:
            return "未指定"
        return entity.name

    def _occupant_symbol(self, entity: EncounterEntity | None) -> str:
        if entity is None:
            return "•"
        if entity.category == "pc":
            class_name = entity.source_ref.get("class_name")
            if isinstance(class_name, str):
                return self.CLASS_EMOJI.get(class_name.lower(), "P")
            return "P"
        if entity.side == "enemy":
            return "E"
        return "N"

    def _occupant_class(self, entity: EncounterEntity) -> str:
        classes: list[str]
        if entity.side == "enemy":
            classes = ["token", "token--enemy"]
        elif entity.category == "pc":
            classes = ["token", "token--ally"]
        else:
            classes = ["token", "token--neutral"]
        return " ".join(classes)

    def _is_dead_entity(self, entity: EncounterEntity) -> bool:
        if entity.category not in {"pc", "npc"}:
            return False
        return entity.combat_flags.get("is_dead") is True

    def _is_downed_entity(self, entity: EncounterEntity) -> bool:
        if entity.category not in {"pc", "npc"}:
            return False
        if self._is_dead_entity(entity):
            return False
        return entity.hp.get("current", 0) == 0

    def _side_label(self, side: str) -> str:
        return self.SIDE_LABELS.get(side, side)

    def _category_label(self, category: str) -> str:
        return self.CATEGORY_LABELS.get(category, category)

    def _position_label(self, entity: EncounterEntity) -> str:
        return f"({entity.position['x']}, {entity.position['y']})"

    def _hp_label(self, entity: EncounterEntity) -> str:
        return f"{entity.hp['current']}/{entity.hp['max']}"

    def _hp_percent(self, entity: EncounterEntity) -> float:
        max_hp = entity.hp.get("max", 0)
        if not max_hp:
            return 0
        return max(0, min(100, entity.hp.get("current", 0) / max_hp * 100))
