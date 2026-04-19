# Player Character Sheet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 localhost battlemap 页面地图下方新增固定主角角色卡，先落地厚重 RPG 风格静态 UI，再接入现有 `encounter_state` 做动态刷新与 tab 保持。

**Architecture:** 继续沿用 `scripts/run_battlemap_localhost.py` 的服务端拼页模式，在 battlemap 根区域后追加一个独立 `player-sheet` section。前端用原生 JS 维护统一 `player_sheet` 对象和激活 tab；第二步通过 `buildPlayerSheet(encounterState)` 从现有状态适配动态数据，避免第一轮就扩张为完整角色系统重构。

**Tech Stack:** Python, unittest, localhost battlemap HTML/CSS/vanilla JS

---

## File Map

- Modify: `trpg-battle-system/scripts/run_battlemap_localhost.py`
  - 为 localhost battlemap 页面增加主角卡 HTML/CSS/JS
  - 新增局部 helper，避免继续把整块 UI 堆在单个长字符串中
- Modify: `trpg-battle-system/test/test_run_battlemap_localhost.py`
  - 为角色卡 HTML 输出和运行时脚本补测试
- Optional Modify: `trpg-battle-system/tools/services/encounter/get_encounter_state.py`
  - 仅在 Phase 2 发现现有投影字段明显不够时补最小投影，不提前做完整 `player_sheet`

## Implementation Notes

- 第一轮固定主角卡允许用静态 `player_sheet`
- 去掉预览里的“角色定位”文案区
- 顶部摘要必须是 `44 / 44 HP · AC 16` 这种写法
- `技能` 页签里即使加值为 `0` 也必须显示
- `后续追加` 第一轮只做占位页
- 新状态应用后必须保持当前激活 tab

### Task 1: Static Player Sheet Shell In Localhost Battlemap

**Files:**
- Modify: `trpg-battle-system/test/test_run_battlemap_localhost.py`
- Modify: `trpg-battle-system/scripts/run_battlemap_localhost.py`

- [ ] **Step 1: Write the failing localhost page test for static player sheet structure**

```python
    def test_render_localhost_page_includes_player_sheet_shell_and_tabs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = ensure_preview_encounter(repo)

            html = render_localhost_battlemap_page(
                encounter_id=encounter.encounter_id,
                page_title="Battlemap Localhost",
                initial_state={
                    "encounter_id": encounter.encounter_id,
                    "encounter_name": encounter.name,
                    "round": encounter.round,
                    "battlemap_details": {
                        "name": encounter.map.name,
                        "description": encounter.map.description,
                        "dimensions": f"{encounter.map.width} x {encounter.map.height} tiles",
                        "grid_size": f"Each tile represents {encounter.map.grid_size_feet} feet",
                    },
                    "battlemap_view": {"html": "<section>map</section>"},
                },
            )

            self.assertIn('data-role="player-sheet-shell"', html)
            self.assertIn('data-role="player-sheet-portrait"', html)
            self.assertIn('data-role="player-sheet-tabs"', html)
            self.assertIn(">技能<", html)
            self.assertIn(">装备<", html)
            self.assertIn(">后续追加<", html)
            self.assertIn("44 / 44 HP · AC 16", html)
            repo.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_run_battlemap_localhost.RunBattlemapLocalhostTests.test_render_localhost_page_includes_player_sheet_shell_and_tabs -v`

Expected: FAIL because the localhost page does not yet contain `player-sheet-shell`.

- [ ] **Step 3: Add static player sheet helper functions and HTML shell**

```python
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
    return (
        '<section class="player-sheet-shell" data-role="player-sheet-shell">'
        '<div class="player-sheet-grid">'
        '<aside class="player-sheet-portrait" data-role="player-sheet-portrait"></aside>'
        '<div class="player-sheet-main">'
        '<div class="player-sheet-summary" data-role="player-sheet-summary"></div>'
        '<div class="player-sheet-abilities" data-role="player-sheet-abilities"></div>'
        '<div class="player-sheet-tabs" data-role="player-sheet-tabs"></div>'
        '<div class="player-sheet-panel" data-role="player-sheet-panel"></div>'
        "</div></div></section>"
    )
```

- [ ] **Step 4: Add the player sheet CSS block and append the shell after the battlemap root**

```python
            ".player-sheet-shell{position:relative;padding:18px;border-radius:28px;"
            "background:linear-gradient(180deg,rgba(29,24,19,.96),rgba(11,12,14,.98));"
            "border:1px solid rgba(214,176,112,.22);"
            "box-shadow:0 24px 48px rgba(0,0,0,.35),inset 0 1px 0 rgba(255,237,203,.05);}"
            ".player-sheet-grid{display:grid;grid-template-columns:170px minmax(0,1fr);gap:16px;}"
            ".player-sheet-tab{appearance:none;border:none;padding:10px 16px;border-radius:999px;}"
            ".player-sheet-tab.is-active{background:linear-gradient(180deg,rgba(197,149,75,.3),rgba(110,76,32,.36));}"
```

```python
            f'<div data-role="battlemap-view-root">{battlemap_html}</div>'
            f"{render_player_sheet_shell(build_static_player_sheet())}"
```

- [ ] **Step 5: Add static rendering script for summary, abilities, tabs, and default `skills` panel**

```python
            f"window.__PLAYER_SHEET__ = {json.dumps(build_static_player_sheet(), ensure_ascii=False)};"
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
            "<div class=\"player-sheet-name\">' + (summary.name||'未命名角色') + '</div>' +"
            "'<div class=\"player-sheet-class\">' + ((summary.subclass_name||summary.class_name||'未知职业') + ' · ' + (summary.level||'--') + '级') + '</div>' +"
            "'<div class=\"player-sheet-health\">' + (summary.hp_current ?? '--') + ' / ' + (summary.hp_max ?? '--') + ' HP · AC ' + (summary.ac ?? '--') + '</div>' +"
            "'<div class=\"player-sheet-spell\">法术豁免 ' + (summary.spell_save_dc ?? '--') + ' · 法术攻击 ' + window.formatSignedModifier(summary.spell_attack_bonus) + '</div>';"
            "}"
            "var abilityRoot=document.querySelector('[data-role=\"player-sheet-abilities\"]');"
            "if(abilityRoot){abilityRoot.innerHTML=((playerSheet&&playerSheet.abilities)||[]).map(function(item){"
            "return '<div class=\"player-sheet-ability\">'"
            " + '<span class=\"player-sheet-ability-label\">' + item.label + '</span>'"
            " + '<strong class=\"player-sheet-ability-score\">' + item.score + '</strong>'"
            " + '<span class=\"player-sheet-ability-save\">豁免 ' + window.formatSignedModifier(item.save_bonus) + '</span>'"
            " + '</div>';"
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
            "return '<div class=\"player-sheet-equipment-row\">'"
            " + '<strong>' + item.name + '</strong>'"
            " + '<span>' + window.formatSignedModifier(item.attack_bonus) + '</span>'"
            " + '<span>' + item.damage + '</span>'"
            " + '<span>' + (item.mastery||'--') + '</span>'"
            " + '</div>';"
            "}).join('') || '<div class=\"player-sheet-empty\">暂无装备数据</div>';return;}"
            "if(activeTab==='extras'){"
            "var extras=(playerSheet&&playerSheet.tabs&&playerSheet.tabs.extras)||{};"
            "panelRoot.innerHTML='<div class=\"player-sheet-empty\"><strong>' + (extras.placeholder_title||'后续追加') + '</strong><p>' + (extras.placeholder_body||'后续会加入更多角色信息。') + '</p></div>';return;}"
            "panelRoot.innerHTML=((playerSheet&&playerSheet.tabs&&playerSheet.tabs.skills)||[]).map(function(item){"
            "return '<div class=\"player-sheet-skill-row\">'"
            " + '<span>' + item.label + '</span>'"
            " + '<strong>' + window.formatSignedModifier(item.modifier) + '</strong>'"
            " + '</div>';"
            "}).join('');"
            "};"
            "window.renderPlayerSheet(window.__PLAYER_SHEET__);"
```

- [ ] **Step 6: Run the focused localhost page test**

Run: `python3 -m unittest test.test_run_battlemap_localhost.RunBattlemapLocalhostTests.test_render_localhost_page_includes_player_sheet_shell_and_tabs -v`

Expected: PASS

- [ ] **Step 7: Commit the static player sheet shell**

```bash
git -C /Users/runshi.zhang/DND-DM-skill add \
  trpg-battle-system/scripts/run_battlemap_localhost.py \
  trpg-battle-system/test/test_run_battlemap_localhost.py
git -C /Users/runshi.zhang/DND-DM-skill commit -m "feat: add static player sheet shell"
```

### Task 2: Tab Switching And Zero-Value Skill Visibility

**Files:**
- Modify: `trpg-battle-system/test/test_run_battlemap_localhost.py`
- Modify: `trpg-battle-system/scripts/run_battlemap_localhost.py`

- [ ] **Step 1: Add a failing test for tab runtime and zero-value skill output**

```python
    def test_render_localhost_page_player_sheet_scripts_keep_zero_skills_and_tab_state(self) -> None:
        html = render_localhost_battlemap_page(
            encounter_id="enc_preview_demo",
            page_title="Battlemap Localhost",
            initial_state={
                "encounter_id": "enc_preview_demo",
                "encounter_name": "测试遭遇",
                "round": 1,
                "battlemap_details": {
                    "name": "测试地图",
                    "description": "desc",
                    "dimensions": "10 x 10 tiles",
                    "grid_size": "Each tile represents 5 feet",
                },
                "battlemap_view": {"html": "<section>map</section>"},
            },
        )

        self.assertIn("window.__PLAYER_SHEET_ACTIVE_TAB__", html)
        self.assertIn("modifier===0", html)
        self.assertIn("欺瞞", html.replace("欺瞒", "欺瞞"))
        self.assertIn("后续追加", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_run_battlemap_localhost.RunBattlemapLocalhostTests.test_render_localhost_page_player_sheet_scripts_keep_zero_skills_and_tab_state -v`

Expected: FAIL because the tab runtime is still incomplete or the assertions are absent.

- [ ] **Step 3: Harden the panel renderer so zero skill modifiers render explicitly**

```python
            "var formatSignedModifier=function(value){"
            "if(typeof value!=='number'){return '--';}"
            "if(value>0){return '+' + value;}"
            "if(value===0){return '0';}"
            "return String(value);"
            "};"
            "var renderSkillRows=function(items){"
            "return items.map(function(item){"
            "return '<div class=\"player-sheet-skill-row\"><span>' + item.label + '</span><strong>' + formatSignedModifier(item.modifier) + '</strong></div>';"
            "}).join('');"
            "};"
```

- [ ] **Step 4: Add delegated tab switching that preserves `window.__PLAYER_SHEET_ACTIVE_TAB__`**

```python
            "document.addEventListener('click',function(event){"
            "var button=event.target&&event.target.closest('[data-player-sheet-tab]');"
            "if(!button){return;}"
            "window.__PLAYER_SHEET_ACTIVE_TAB__=button.getAttribute('data-player-sheet-tab')||'skills';"
            "window.renderPlayerSheet(window.__PLAYER_SHEET__);"
            "});"
```

- [ ] **Step 5: Run both localhost page tests**

Run: `python3 -m unittest test.test_run_battlemap_localhost.RunBattlemapLocalhostTests.test_render_localhost_page_includes_player_sheet_shell_and_tabs test.test_run_battlemap_localhost.RunBattlemapLocalhostTests.test_render_localhost_page_player_sheet_scripts_keep_zero_skills_and_tab_state -v`

Expected: PASS

- [ ] **Step 6: Commit tab interaction and zero-value skill rendering**

```bash
git -C /Users/runshi.zhang/DND-DM-skill add \
  trpg-battle-system/scripts/run_battlemap_localhost.py \
  trpg-battle-system/test/test_run_battlemap_localhost.py
git -C /Users/runshi.zhang/DND-DM-skill commit -m "feat: add player sheet tab switching"
```

### Task 3: Adapt Player Sheet From Encounter State While Preserving Active Tab

**Files:**
- Modify: `trpg-battle-system/test/test_run_battlemap_localhost.py`
- Modify: `trpg-battle-system/scripts/run_battlemap_localhost.py`
- Reference: `trpg-battle-system/tools/services/encounter/get_encounter_state.py`

- [ ] **Step 1: Add a failing test that requires dynamic player sheet refresh hooks**

```python
    def test_render_localhost_page_player_sheet_syncs_from_encounter_state(self) -> None:
        html = render_localhost_battlemap_page(
            encounter_id="enc_preview_demo",
            page_title="Battlemap Localhost",
            initial_state={
                "encounter_id": "enc_preview_demo",
                "encounter_name": "测试遭遇",
                "round": 1,
                "battlemap_details": {
                    "name": "测试地图",
                    "description": "desc",
                    "dimensions": "10 x 10 tiles",
                    "grid_size": "Each tile represents 5 feet",
                },
                "battlemap_view": {"html": "<section>map</section>"},
                "current_turn_entity": {
                    "name": "米伦",
                    "hp": {"current": 22, "max": 27, "temp": 0},
                    "ac": 14,
                    "available_actions": {
                        "weapons": [{"name": "长杖", "attack_bonus": 5, "damage": "1d8+3"}],
                    },
                },
            },
        )

        self.assertIn("window.buildPlayerSheet", html)
        self.assertIn("window.__PLAYER_SHEET__ = window.buildPlayerSheet(window.__BATTLEMAP_STATE__)", html)
        self.assertIn("window.renderPlayerSheet(window.__PLAYER_SHEET__)", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_run_battlemap_localhost.RunBattlemapLocalhostTests.test_render_localhost_page_player_sheet_syncs_from_encounter_state -v`

Expected: FAIL because the page still uses only static player sheet data.

- [ ] **Step 3: Add a minimal `buildPlayerSheet(nextState)` adapter with static fallback**

```python
            "window.buildPlayerSheet = function(nextState){"
            "var fallback=" + json.dumps(build_static_player_sheet(), ensure_ascii=False) + ";"
            "if(!nextState||typeof nextState!=='object'){return fallback;}"
            "var actor=nextState.current_turn_entity;"
            "if(!actor||typeof actor!=='object'){return fallback;}"
            "var summary=fallback.summary;"
            "var hp=actor.hp||{};"
            "return {"
            "summary:{"
            "name:typeof actor.name==='string'&&actor.name?actor.name:summary.name,"
            "class_name:summary.class_name,"
            "subclass_name:summary.subclass_name,"
            "level:summary.level,"
            "hp_current:typeof hp.current==='number'?hp.current:summary.hp_current,"
            "hp_max:typeof hp.max==='number'?hp.max:summary.hp_max,"
            "ac:typeof actor.ac==='number'?actor.ac:summary.ac,"
            "spell_save_dc:summary.spell_save_dc,"
            "spell_attack_bonus:summary.spell_attack_bonus,"
            "portrait_url:summary.portrait_url"
            "},"
            "abilities:fallback.abilities,"
            "tabs:{"
            "skills:fallback.tabs.skills,"
            "equipment:(actor.available_actions&&actor.available_actions.weapons)||fallback.tabs.equipment,"
            "extras:fallback.tabs.extras"
            "}"
            "};"
            "};"
```

- [ ] **Step 4: Update state application to rebuild player sheet from latest encounter state without resetting tab**

```python
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
            "window.__PLAYER_SHEET__ = window.buildPlayerSheet(nextState);"
            "window.renderPlayerSheet(window.__PLAYER_SHEET__);"
            "document.dispatchEvent(new CustomEvent('battlemap:state-applied',{detail:{encounterState:nextState}}));"
            "return nextState;"
            "};"
```

- [ ] **Step 5: Run the localhost page suite**

Run: `python3 -m unittest test.test_run_battlemap_localhost -v`

Expected: PASS

- [ ] **Step 6: Commit dynamic player sheet adaptation**

```bash
git -C /Users/runshi.zhang/DND-DM-skill add \
  trpg-battle-system/scripts/run_battlemap_localhost.py \
  trpg-battle-system/test/test_run_battlemap_localhost.py
git -C /Users/runshi.zhang/DND-DM-skill commit -m "feat: sync player sheet from encounter state"
```

### Task 4: Final Verification And Manual Review Surface

**Files:**
- Modify: `trpg-battle-system/scripts/run_battlemap_localhost.py`
- Modify: `trpg-battle-system/test/test_run_battlemap_localhost.py`

- [ ] **Step 1: Run the targeted localhost and preview page suites**

Run: `python3 -m unittest test.test_run_battlemap_localhost test.test_render_battlemap_page -v`

Expected: PASS

- [ ] **Step 2: Run the full regression suite if targeted tests pass**

Run: `python3 -m unittest discover -s test -v`

Expected: PASS

- [ ] **Step 3: Inspect the localhost page manually if a runtime is available**

Run: `python3 scripts/run_battlemap_localhost.py --runtime-base-url http://127.0.0.1:8771`

Expected: 页面底部出现主角卡；切换 `技能 / 装备 / 后续追加` 时只切面板，不影响地图；轮询刷新后仍保留当前 tab。

- [ ] **Step 4: Commit final polish if any manual review adjustments were required**

```bash
git -C /Users/runshi.zhang/DND-DM-skill add \
  trpg-battle-system/scripts/run_battlemap_localhost.py \
  trpg-battle-system/test/test_run_battlemap_localhost.py
git -C /Users/runshi.zhang/DND-DM-skill commit -m "refactor: polish localhost player sheet UI"
```
