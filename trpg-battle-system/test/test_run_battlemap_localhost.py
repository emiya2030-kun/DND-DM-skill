"""localhost battlemap 服务脚本测试。"""

import json
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_battlemap_localhost import (
    BattlemapLocalhostHandler,
    PREVIEW_ENCOUNTER_ID,
    ensure_preview_encounter,
    render_localhost_battlemap_page,
)
from scripts.run_battlemap_localhost import ThreadingHTTPServer
from tools.repositories import EncounterRepository


class RunBattlemapLocalhostTests(unittest.TestCase):
    def _request_json(self, base_url: str, path: str) -> tuple[int, dict[str, object]]:
        try:
            with urlopen(f"{base_url}{path}", timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def _request_json_with_body(
        self,
        base_url: str,
        path: str,
        *,
        method: str,
        body: dict[str, object],
    ) -> tuple[int, dict[str, object]]:
        request = Request(
            f"{base_url}{path}",
            data=json.dumps(body).encode("utf-8"),
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def test_api_encounter_state_runtime_proxy_forwards_success_status_and_body(self) -> None:
        BattlemapLocalhostHandler.repository = None
        BattlemapLocalhostHandler.runtime_base_url = "http://127.0.0.1:8771"
        BattlemapLocalhostHandler.page_title = "Battlemap Localhost"
        BattlemapLocalhostHandler.dev_reload_path = None
        server = ThreadingHTTPServer(("127.0.0.1", 0), BattlemapLocalhostHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with patch(
                "scripts.run_battlemap_localhost.fetch_runtime_encounter_state",
                return_value={"ok": True, "encounter_id": "enc_preview_demo"},
            ):
                status, payload = self._request_json(base_url, "/api/encounter-state?encounter_id=enc_preview_demo")

            self.assertEqual(status, 200)
            self.assertEqual(payload["encounter_id"], "enc_preview_demo")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_api_encounter_state_runtime_proxy_forwards_http_error_status_and_json(self) -> None:
        BattlemapLocalhostHandler.repository = None
        BattlemapLocalhostHandler.runtime_base_url = "http://127.0.0.1:8771"
        BattlemapLocalhostHandler.page_title = "Battlemap Localhost"
        BattlemapLocalhostHandler.dev_reload_path = None
        server = ThreadingHTTPServer(("127.0.0.1", 0), BattlemapLocalhostHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with patch(
                "scripts.run_battlemap_localhost.fetch_runtime_encounter_state",
                return_value={"ok": False, "error_code": "encounter_not_found", "_status": 404},
            ):
                status, payload = self._request_json(base_url, "/api/encounter-state?encounter_id=enc_missing")

            self.assertEqual(status, 404)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error_code"], "encounter_not_found")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_api_encounter_state_runtime_proxy_maps_runtime_unavailable_to_502(self) -> None:
        BattlemapLocalhostHandler.repository = None
        BattlemapLocalhostHandler.runtime_base_url = "http://127.0.0.1:8771"
        BattlemapLocalhostHandler.page_title = "Battlemap Localhost"
        BattlemapLocalhostHandler.dev_reload_path = None
        server = ThreadingHTTPServer(("127.0.0.1", 0), BattlemapLocalhostHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with patch(
                "scripts.run_battlemap_localhost.fetch_runtime_encounter_state",
                side_effect=RuntimeError("down"),
            ):
                with self.assertRaises(HTTPError) as error_context:
                    urlopen(f"{base_url}/api/encounter-state?encounter_id=enc_preview_demo", timeout=5)

            self.assertEqual(error_context.exception.code, 502)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_ensure_preview_encounter_seeds_shared_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")

            with patch("tools.services.encounter.roll_initiative_and_start_encounter.randint", side_effect=[12, 10, 8]):
                with patch("tools.services.encounter.roll_initiative_and_start_encounter.random", side_effect=[0.11, 0.22, 0.33]):
                    encounter = ensure_preview_encounter(repo)

            self.assertEqual(encounter.encounter_id, PREVIEW_ENCOUNTER_ID)
            reloaded = repo.get(PREVIEW_ENCOUNTER_ID)
            self.assertIsNotNone(reloaded)
            self.assertEqual(reloaded.entities["ent_ally_wizard_001"].position, {"x": 5, "y": 5})
            self.assertEqual(
                reloaded.turn_order,
                ["ent_ally_wizard_001", "ent_ally_ranger_001", "ent_enemy_brute_001"],
            )
            self.assertEqual(reloaded.current_entity_id, "ent_ally_wizard_001")
            self.assertEqual(reloaded.round, 1)
            preview_player = reloaded.entities["ent_ally_wizard_001"]
            self.assertEqual(preview_player.source_ref["class_name"], "monk")
            self.assertEqual(preview_player.source_ref["level"], 5)
            self.assertNotIn("skill_training", preview_player.source_ref)
            self.assertEqual(preview_player.skill_training["stealth"], "proficient")
            self.assertEqual(preview_player.skill_training["sleight_of_hand"], "expertise")
            self.assertEqual(preview_player.ac, 16)
            self.assertEqual(preview_player.speed, {"walk": 40, "remaining": 40})
            self.assertEqual(preview_player.ability_scores["dex"], 17)
            self.assertEqual(preview_player.ability_scores["wis"], 16)
            self.assertEqual(preview_player.currency, {"gp": 127})
            repo.close()

    def test_render_localhost_page_injects_hidden_polling_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = ensure_preview_encounter(repo)

            html = render_localhost_battlemap_page(
                encounter_id=encounter.encounter_id,
                page_title="Battlemap Localhost",
            )

            self.assertIn("fetch('/api/encounter-state?encounter_id=' + encodeURIComponent(encounterId)", html)
            self.assertIn("fetchLatestEncounterState();", html)
            self.assertIn("setInterval(fetchLatestEncounterState", html)
            self.assertIn("battlemap:polling-sync-applied", html)
            self.assertIn("window.applyToolError", html)
            self.assertIn("window.getLastToolError", html)
            self.assertIn("battlemap:tool-error-applied", html)
            self.assertIn("apply_tool_error", html)
            self.assertIn("Battlemap Localhost", html)
            self.assertNotIn("window.__BATTLEMAP_DEV__", html)
            repo.close()

    def test_root_page_uses_runtime_initial_state_for_configured_encounter(self) -> None:
        BattlemapLocalhostHandler.repository = None
        BattlemapLocalhostHandler.runtime_base_url = "http://127.0.0.1:8771"
        BattlemapLocalhostHandler.page_title = "Battlemap Localhost"
        BattlemapLocalhostHandler.dev_reload_path = None
        BattlemapLocalhostHandler.encounter_id = "enc_warlock_lv5_test"
        server = ThreadingHTTPServer(("127.0.0.1", 0), BattlemapLocalhostHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with patch(
                "scripts.run_battlemap_localhost.fetch_runtime_encounter_state",
                return_value={
                    "encounter_id": "enc_warlock_lv5_test",
                    "encounter_name": "Warlock Lv5 Test Battle",
                    "round": 1,
                    "battlemap_details": {
                        "name": "邪契荒原",
                        "description": "Kael 与魔宠正在压制前线敌人。",
                        "dimensions": "15 x 15 tiles",
                        "grid_size": "Each tile represents 5 feet",
                    },
                    "battlemap_view": {"html": "<section>Kael 在这里</section>"},
                },
            ):
                with urlopen(f"{base_url}/", timeout=5) as response:
                    html = response.read().decode("utf-8")

            self.assertIn("Warlock Lv5 Test Battle", html)
            self.assertIn("Kael 在这里", html)
            self.assertNotIn("月祷礼拜堂攻防战", html)
            self.assertNotIn("米伦", html)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_render_localhost_page_can_inject_dev_reload_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = ensure_preview_encounter(repo)

            html = render_localhost_battlemap_page(
                encounter_id=encounter.encounter_id,
                page_title="Battlemap Dev",
                dev_reload_path="/dev/reload",
            )

            self.assertIn("/dev/reload", html)
            self.assertIn("window.__BATTLEMAP_DEV__", html)
            self.assertIn("window.location.reload()", html)
            repo.close()

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
            self.assertNotIn('data-role="encounter-hero"', html)
            self.assertNotIn('data-role="encounter-title"', html)
            self.assertNotIn("战斗地图预览", html)
            self.assertNotIn("地图尺寸", html)
            self.assertNotIn("比例尺", html)
            self.assertIn(">技能<", html)
            self.assertIn(">装备<", html)
            self.assertIn(">后续追加<", html)
            self.assertIn("player-sheet-summary-grid", html)
            self.assertIn("player-sheet-summary-stat", html)
            self.assertIn("player-sheet-summary-stat-label", html)
            repo.close()

    def test_render_localhost_page_includes_template_controls(self) -> None:
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

        self.assertIn('data-role="template-tools"', html)
        self.assertIn('data-role="template-name-input"', html)
        self.assertIn('data-role="template-select"', html)
        self.assertIn('data-action="save-template"', html)
        self.assertIn('data-action="restore-template"', html)
        self.assertIn('data-action="clone-template"', html)
        self.assertIn("window.loadEncounterTemplates = async function()", html)

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
                "player_sheet_source": {
                    "summary": {
                        "name": "米伦",
                        "class_name": "武僧",
                        "subclass_name": "--",
                        "level": 5,
                        "hp_current": 22,
                        "hp_max": 27,
                        "ac": 16,
                        "speed": 40,
                        "spell_save_dc": None,
                        "spell_attack_bonus": None,
                        "portrait_url": None,
                    },
                    "abilities": [],
                    "tabs": {
                        "skills": [
                            {
                                "key": "animal_handling",
                                "label": "驯兽",
                                "modifier": 3,
                                "ability_label": "感知",
                                "training_indicator": "🅞",
                            },
                            {
                                "key": "deception",
                                "label": "欺瞒",
                                "modifier": 0,
                                "ability_label": "魅力",
                                "training_indicator": "X",
                            },
                        ],
                        "equipment": {"weapons": [], "armor": {"title": "穿戴护甲", "items": []}, "backpacks": []},
                        "extras": {"placeholder_title": "后续追加", "placeholder_body": "动态资料"},
                    },
                },
            },
        )

        self.assertIn("window.__PLAYER_SHEET_ACTIVE_TAB__", html)
        self.assertIn("if(value===0){return '0';}", html)
        self.assertIn("驯兽", html)
        self.assertIn("检定能力", html)
        self.assertIn("🅞", html)
        self.assertIn("欺瞒", html)
        self.assertIn("后续追加", html)
        self.assertIn("player-sheet-summary-grid", html)
        self.assertIn("速度", html)
        self.assertIn("40 尺", html)
        self.assertIn("--hp-fill:81.5%", html)

    def test_render_localhost_page_player_sheet_equipment_tab_uses_structured_sections(self) -> None:
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
                "player_sheet_source": {
                    "summary": {
                        "name": "测试角色",
                        "class_name": "战士",
                        "subclass_name": "奥法骑士",
                        "level": 4,
                        "hp_current": 44,
                        "hp_max": 44,
                        "ac": 16,
                        "speed": 30,
                        "spell_save_dc": 13,
                        "spell_attack_bonus": 5,
                        "portrait_url": None,
                    },
                    "abilities": [],
                    "tabs": {
                        "skills": [],
                        "equipment": {
                            "weapons": [
                                {
                                    "name": "手斧",
                                    "properties": "轻型,投掷(射程 20/60)",
                                    "proficient": "O",
                                    "attack_display": "D20+4",
                                    "damage_display": "1d6+1",
                                    "damage_type": "挥砍",
                                    "mastery": "侵扰",
                                },
                                {
                                    "name": "匕首",
                                    "properties": "灵巧,轻型,投掷(射程 20/60)",
                                    "proficient": "O",
                                    "attack_display": "D20+7",
                                    "damage_display": "1d4+4",
                                    "damage_type": "穿刺",
                                    "mastery": "迅击",
                                },
                            ],
                            "armor": {
                                "title": "穿戴护甲",
                                "items": [
                                    {"name": "皮甲", "category": "輕甲", "ac": "11", "dex": "+2"},
                                    {"name": "盾牌", "category": "無", "ac": "0", "dex": "0"},
                                ],
                            },
                            "backpacks": [
                                {
                                    "name": "背包1",
                                    "gold": 127,
                                    "items": [{"name": "链条", "quantity": "×1"}],
                                }
                            ],
                        },
                        "extras": {"placeholder_title": "后续追加", "placeholder_body": "动态资料"},
                    },
                },
            },
        )

        self.assertIn("武器", html)
        self.assertIn("护甲", html)
        self.assertIn("背包1", html)
        self.assertIn("手斧", html)
        self.assertIn("匕首", html)
        self.assertIn("穿戴护甲", html)
        self.assertIn("皮甲", html)
        self.assertIn("盾牌", html)
        self.assertIn("链条", html)
        self.assertIn('"proficient": "O"', html)
        self.assertNotIn("☑", html)
        self.assertIn("D20+7", html)
        self.assertIn("1d6+1", html)
        self.assertIn("GP", html)
        self.assertIn("轻型,投掷(射程 20/60)", html)
        self.assertIn("灵巧,轻型,投掷(射程 20/60)", html)
        self.assertIn("輕甲", html)
        self.assertIn("11", html)

    def test_render_localhost_page_player_sheet_builds_from_encounter_state_source(self) -> None:
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
                "player_sheet_source": {
                    "summary": {
                        "name": "艾瑞克",
                        "class_name": "圣武士",
                        "subclass_name": "远古誓言",
                        "level": 5,
                        "hp_current": 18,
                        "hp_max": 20,
                        "ac": 15,
                        "speed": 30,
                        "spell_save_dc": 14,
                        "spell_attack_bonus": 6,
                        "portrait_url": None,
                    },
                    "abilities": [
                        {"key": "str", "label": "力量", "score": 10, "save_bonus": 0},
                    ],
                    "tabs": {
                        "skills": [{"key": "arcana", "label": "奥秘", "modifier": 1}],
                        "equipment": {
                            "weapons": [
                                {
                                    "name": "刺剑",
                                    "proficient": "O",
                                    "attack_display": "D20+5",
                                    "damage_display": "1d8+3",
                                    "damage_type": "穿刺",
                                    "properties": "灵巧",
                                    "mastery": "--",
                                }
                            ],
                            "armor": {
                                "title": "穿戴护甲",
                                "items": [{"name": "皮甲", "category": "輕甲", "ac": "11", "dex": "+2"}],
                            },
                            "backpacks": [{"name": "背包1", "gold": 23, "items": [{"name": "链条", "quantity": "×1"}]}],
                        },
                        "extras": {"placeholder_title": "后续追加", "placeholder_body": "动态资料"},
                    },
                },
            },
        )

        self.assertIn("window.buildPlayerSheet = function(nextState)", html)
        self.assertIn("window.__PLAYER_SHEET__ = window.buildPlayerSheet(window.__BATTLEMAP_STATE__);", html)
        self.assertIn("window.__PLAYER_SHEET__=window.buildPlayerSheet(nextState);", html)
        self.assertIn("艾瑞克", html)
        self.assertIn("player-sheet-summary-stat-label", html)
        self.assertIn("速度", html)
        self.assertIn("30 尺", html)
        self.assertIn("--hp-fill:90.0%", html)
        self.assertIn("D20+5", html)
        self.assertIn('"gold": 23', html)
        self.assertIn("动态资料", html)

    def test_render_localhost_page_player_sheet_does_not_fall_back_to_sample_equipment_when_dynamic_equipment_empty(self) -> None:
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
                "player_sheet_source": {
                    "summary": {
                        "name": "米伦",
                        "class_name": "法师",
                        "subclass_name": "塑能学派",
                        "level": 6,
                        "hp_current": 22,
                        "hp_max": 27,
                        "ac": 14,
                        "speed": 30,
                        "spell_save_dc": 14,
                        "spell_attack_bonus": 6,
                        "portrait_url": None,
                    },
                    "abilities": [
                        {"key": "int", "label": "智力", "score": 18, "save_bonus": 7},
                    ],
                    "tabs": {
                        "skills": [{"key": "arcana", "label": "奥秘", "modifier": 7}],
                        "equipment": [],
                        "extras": {"placeholder_title": "后续追加", "placeholder_body": "动态资料"},
                    },
                },
            },
        )

        self.assertIn("米伦", html)
        self.assertNotIn("手斧", html)
        self.assertNotIn("皮甲", html)
        self.assertNotIn("链条", html)
        self.assertIn('"equipment": []', html)

    def test_render_localhost_page_player_sheet_without_backend_source_does_not_include_static_sample_content(self) -> None:
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

        self.assertNotIn("奎里昂", html)
        self.assertNotIn("手斧", html)
        self.assertNotIn("皮甲", html)
        self.assertNotIn('"gold": 127', html)

    def test_root_page_with_repository_mode_includes_player_sheet_shell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            ensure_preview_encounter(repo)

            BattlemapLocalhostHandler.repository = repo
            BattlemapLocalhostHandler.runtime_base_url = None
            BattlemapLocalhostHandler.page_title = "Battlemap Localhost"
            BattlemapLocalhostHandler.dev_reload_path = None
            BattlemapLocalhostHandler.encounter_id = PREVIEW_ENCOUNTER_ID
            server = ThreadingHTTPServer(("127.0.0.1", 0), BattlemapLocalhostHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                with urlopen(f"{base_url}/", timeout=5) as response:
                    html = response.read().decode("utf-8")

                self.assertIn('data-role="player-sheet-shell"', html)
                self.assertIn('data-role="player-sheet-tabs"', html)
                self.assertIn('data-role="template-tools"', html)
                self.assertIn(">技能<", html)
                self.assertIn("window.buildPlayerSheet = function(nextState)", html)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                if BattlemapLocalhostHandler.template_repository is not None:
                    BattlemapLocalhostHandler.template_repository.close()
                    BattlemapLocalhostHandler.template_repository = None
                repo.close()

    def test_render_localhost_page_places_player_sheet_below_grid_and_left_of_legend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = ensure_preview_encounter(repo)
            from tools.services import GetEncounterState

            state = GetEncounterState(repo).execute(encounter.encounter_id)
            html = render_localhost_battlemap_page(
                encounter_id=encounter.encounter_id,
                page_title="Battlemap Localhost",
                initial_state=state,
            )

            layout_index = html.find('<div class="battlemap-layout battlemap-frame">')
            footer_index = html.find('class="battlemap-footer-panels"')
            sheet_index = html.find('data-role="player-sheet-shell"')
            focus_index = html.find('<h3 class="sidebar-label">回合焦点</h3>')
            activity_index = html.find('<h3 class="sidebar-label">战况记录</h3>')
            legend_index = html.find('<h3 class="sidebar-label">地图图例</h3>')

            self.assertGreater(layout_index, -1)
            self.assertGreater(footer_index, layout_index)
            self.assertGreater(sheet_index, footer_index)
            self.assertGreater(focus_index, -1)
            self.assertGreater(activity_index, focus_index)
            self.assertGreater(legend_index, activity_index)
            self.assertNotIn('<div class="battlemap-footer-side">', html)
            self.assertNotIn('<h3 class="sidebar-label">角色卡</h3>', html)
            self.assertIn('<aside class="battlemap-sidebar battlemap-sidebar--embedded-sheet">', html)
            self.assertIn(
                ".battlemap-sidebar.battlemap-sidebar--embedded-sheet{grid-template-rows:auto",
                html,
            )
            self.assertIn(
                ".battlemap-sidebar--embedded-sheet .sidebar-card--activity{display:grid;grid-template-rows:auto minmax(0,1fr);",
                html,
            )
            self.assertIn(
                ".battlemap-sidebar--embedded-sheet .sidebar-card--legend{display:grid;grid-template-rows:auto minmax(0,1fr);",
                html,
            )
            self.assertIn(".battlemap-sidebar--embedded-sheet .activity-feed{min-height:0;max-height:none;}", html)
            self.assertIn(".battlemap-sidebar--embedded-sheet .legend-list{min-height:0;overflow-y:auto;", html)
            repo.close()

    def test_api_encounter_templates_lists_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            ensure_preview_encounter(repo)

            BattlemapLocalhostHandler.repository = repo
            BattlemapLocalhostHandler.runtime_base_url = None
            BattlemapLocalhostHandler.page_title = "Battlemap Localhost"
            BattlemapLocalhostHandler.dev_reload_path = None
            BattlemapLocalhostHandler.encounter_id = PREVIEW_ENCOUNTER_ID
            server = ThreadingHTTPServer(("127.0.0.1", 0), BattlemapLocalhostHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                create_status, create_payload = self._request_json_with_body(
                    base_url,
                    "/api/encounter-templates",
                    method="POST",
                    body={"encounter_id": PREVIEW_ENCOUNTER_ID, "name": "礼拜堂稳定版"},
                )
                status, payload = self._request_json(base_url, "/api/encounter-templates")

                self.assertEqual(create_status, 201)
                self.assertEqual(status, 200)
                self.assertIn("templates", payload)
                self.assertEqual(payload["templates"][0]["name"], "礼拜堂稳定版")
                self.assertEqual(payload["templates"][0]["template_id"], create_payload["template"]["template_id"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                if BattlemapLocalhostHandler.template_repository is not None:
                    BattlemapLocalhostHandler.template_repository.close()
                    BattlemapLocalhostHandler.template_repository = None
                repo.close()

    def test_api_encounter_templates_create_restore_and_clone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            ensure_preview_encounter(repo)

            BattlemapLocalhostHandler.repository = repo
            BattlemapLocalhostHandler.runtime_base_url = None
            BattlemapLocalhostHandler.page_title = "Battlemap Localhost"
            BattlemapLocalhostHandler.dev_reload_path = None
            BattlemapLocalhostHandler.encounter_id = PREVIEW_ENCOUNTER_ID
            server = ThreadingHTTPServer(("127.0.0.1", 0), BattlemapLocalhostHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                create_status, create_payload = self._request_json_with_body(
                    base_url,
                    "/api/encounter-templates",
                    method="POST",
                    body={"encounter_id": PREVIEW_ENCOUNTER_ID, "name": "礼拜堂稳定版"},
                )
                self.assertEqual(create_status, 201)
                template_id = str(create_payload["template"]["template_id"])

                repo_encounter = repo.get(PREVIEW_ENCOUNTER_ID)
                assert repo_encounter is not None
                repo_encounter.name = "Broken"
                repo.save(repo_encounter)

                restore_status, restore_payload = self._request_json_with_body(
                    base_url,
                    "/api/encounter-templates/restore",
                    method="POST",
                    body={"template_id": template_id, "target_encounter_id": PREVIEW_ENCOUNTER_ID},
                )
                clone_status, clone_payload = self._request_json_with_body(
                    base_url,
                    "/api/encounter-templates/create-encounter",
                    method="POST",
                    body={
                        "template_id": template_id,
                        "encounter_id": "enc_clone_test",
                        "encounter_name": "克隆副本",
                    },
                )

                self.assertEqual(restore_status, 200)
                self.assertEqual(restore_payload["encounter"]["name"], "月祷礼拜堂攻防战")
                self.assertEqual(clone_status, 201)
                self.assertEqual(clone_payload["encounter"]["encounter_id"], "enc_clone_test")
                self.assertEqual(clone_payload["encounter"]["name"], "克隆副本")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                repo.close()


if __name__ == "__main__":
    unittest.main()
