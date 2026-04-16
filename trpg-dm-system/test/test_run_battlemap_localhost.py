"""localhost battlemap 服务脚本测试。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_battlemap_localhost import (
    PREVIEW_ENCOUNTER_ID,
    ensure_preview_encounter,
    render_localhost_battlemap_page,
)
from tools.repositories import EncounterRepository


class RunBattlemapLocalhostTests(unittest.TestCase):
    def test_ensure_preview_encounter_seeds_shared_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")

            encounter = ensure_preview_encounter(repo)

            self.assertEqual(encounter.encounter_id, PREVIEW_ENCOUNTER_ID)
            reloaded = repo.get(PREVIEW_ENCOUNTER_ID)
            self.assertIsNotNone(reloaded)
            self.assertEqual(reloaded.entities["ent_ally_wizard_001"].position, {"x": 5, "y": 4})
            repo.close()

    def test_render_localhost_page_injects_hidden_polling_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = ensure_preview_encounter(repo)

            html = render_localhost_battlemap_page(
                encounter=encounter,
                page_title="Battlemap Localhost",
            )

            self.assertIn("fetch('/api/encounter-state?encounter_id=' + encodeURIComponent(encounterId)", html)
            self.assertIn("setInterval(fetchLatestEncounterState", html)
            self.assertIn("battlemap:polling-sync-applied", html)
            self.assertIn("Battlemap Localhost", html)
            self.assertNotIn("window.__BATTLEMAP_DEV__", html)
            repo.close()

    def test_render_localhost_page_can_inject_dev_reload_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = ensure_preview_encounter(repo)

            html = render_localhost_battlemap_page(
                encounter=encounter,
                page_title="Battlemap Dev",
                dev_reload_path="/dev/reload",
            )

            self.assertIn("/dev/reload", html)
            self.assertIn("window.__BATTLEMAP_DEV__", html)
            self.assertIn("window.location.reload()", html)
            repo.close()


if __name__ == "__main__":
    unittest.main()
