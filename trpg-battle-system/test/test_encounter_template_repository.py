"""样板快照仓储测试。"""

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from test.test_encounter_repository import build_encounter
from tools.repositories import EncounterTemplateRepository


def build_template_record(
    *,
    template_id: str = "tpl_chapel_v1",
    name: str = "礼拜堂稳定版",
    source_encounter_id: str = "enc_preview_demo",
) -> dict[str, object]:
    return {
        "template_id": template_id,
        "name": name,
        "source_encounter_id": source_encounter_id,
        "snapshot": build_encounter().to_dict(),
        "created_at": "2026-04-19T00:00:00Z",
        "updated_at": "2026-04-19T00:00:00Z",
    }


class EncounterTemplateRepositoryTests(unittest.TestCase):
    def test_save_and_get_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterTemplateRepository(Path(tmp_dir) / "encounter_templates.json")
            template = build_template_record()

            repo.save(template)
            loaded = repo.get(template["template_id"])

            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded["name"], "礼拜堂稳定版")
            self.assertEqual(loaded["source_encounter_id"], "enc_preview_demo")
            repo.close()

    def test_list_templates_returns_sorted_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterTemplateRepository(Path(tmp_dir) / "encounter_templates.json")
            repo.save(build_template_record(template_id="tpl_b", name="B"))
            repo.save(build_template_record(template_id="tpl_a", name="A"))

            templates = repo.list_templates()

            self.assertEqual([item["name"] for item in templates], ["A", "B"])
            repo.close()

    def test_delete_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterTemplateRepository(Path(tmp_dir) / "encounter_templates.json")
            template = build_template_record()
            repo.save(template)

            removed = repo.delete(template["template_id"])

            self.assertEqual(removed, 1)
            self.assertIsNone(repo.get(template["template_id"]))
            repo.close()

    def test_repositories_sharing_same_path_serialize_db_access(self) -> None:
        class GuardedTinyDb:
            def __init__(self) -> None:
                self.in_flight = 0
                self.concurrent_access_detected = False

            def _enter(self) -> None:
                self.in_flight += 1
                if self.in_flight > 1:
                    self.concurrent_access_detected = True
                time.sleep(0.05)

            def _exit(self) -> None:
                self.in_flight -= 1

            def upsert(self, *_args, **_kwargs) -> None:
                self._enter()
                self._exit()

            def get(self, *_args, **_kwargs):
                self._enter()
                self._exit()
                return None

            def remove(self, *_args, **_kwargs):
                self._enter()
                self._exit()
                return []

            def all(self):
                self._enter()
                self._exit()
                return []

            def close(self) -> None:
                return

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "encounter_templates.json"
            repo_a = EncounterTemplateRepository(db_path)
            repo_b = EncounterTemplateRepository(db_path)
            guarded_db = GuardedTinyDb()
            repo_a._db.close()
            repo_b._db.close()
            repo_a._db = guarded_db
            repo_b._db = guarded_db
            barrier = threading.Barrier(2)

            def save_worker() -> None:
                barrier.wait(timeout=1)
                repo_a.save(build_template_record())

            def get_worker() -> None:
                barrier.wait(timeout=1)
                repo_b.get("tpl_chapel_v1")

            thread_a = threading.Thread(target=save_worker)
            thread_b = threading.Thread(target=get_worker)
            thread_a.start()
            thread_b.start()
            thread_a.join(timeout=2)
            thread_b.join(timeout=2)

            self.assertFalse(guarded_db.concurrent_access_detected)
            repo_a.close()
            repo_b.close()


if __name__ == "__main__":
    unittest.main()
