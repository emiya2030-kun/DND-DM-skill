"""localhost battlemap 服务脚本测试。"""

import json
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
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
            self.assertIn(">技能<", html)
            self.assertIn(">装备<", html)
            self.assertIn(">后续追加<", html)
            self.assertIn("44 / 44 HP · AC 16", html)
            repo.close()

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
        self.assertIn("if(value===0){return '0';}", html)
        self.assertIn("驯服动物", html)
        self.assertIn("欺瞒", html)
        self.assertIn("后续追加", html)

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
                        "spell_save_dc": 14,
                        "spell_attack_bonus": 6,
                        "portrait_url": None,
                    },
                    "abilities": [
                        {"key": "str", "label": "力量", "score": 10, "save_bonus": 0},
                    ],
                    "tabs": {
                        "skills": [{"key": "arcana", "label": "奥秘", "modifier": 1}],
                        "equipment": [{"name": "刺剑", "attack_bonus": 5, "damage": "1d8+3", "mastery": "--"}],
                        "extras": {"placeholder_title": "后续追加", "placeholder_body": "动态资料"},
                    },
                },
            },
        )

        self.assertIn("window.buildPlayerSheet = function(nextState)", html)
        self.assertIn("window.__PLAYER_SHEET__ = window.buildPlayerSheet(window.__BATTLEMAP_STATE__);", html)
        self.assertIn("window.__PLAYER_SHEET__=window.buildPlayerSheet(nextState);", html)
        self.assertIn("艾瑞克", html)
        self.assertIn("动态资料", html)


if __name__ == "__main__":
    unittest.main()
