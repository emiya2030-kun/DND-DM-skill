"""样板快照服务测试。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from test.test_encounter_repository import build_encounter
from tools.models import Encounter
from tools.repositories import EncounterRepository, EncounterTemplateRepository
from tools.services import (
    CreateEncounterFromTemplate,
    ListEncounterTemplates,
    RestoreEncounterFromTemplate,
    SaveEncounterTemplate,
)


class EncounterTemplateServicesTests(unittest.TestCase):
    def test_save_template_persists_snapshot_and_rejects_duplicate_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            template_repo = EncounterTemplateRepository(Path(tmp_dir) / "encounter_templates.json")
            encounter_repo.save(build_encounter())
            service = SaveEncounterTemplate(encounter_repo, template_repo)

            saved = service.execute(encounter_id="enc_repo_test", template_name="礼拜堂稳定版")

            self.assertEqual(saved["name"], "礼拜堂稳定版")
            self.assertEqual(saved["source_encounter_id"], "enc_repo_test")
            self.assertIn("snapshot", saved)

            with self.assertRaisesRegex(ValueError, "already exists"):
                service.execute(encounter_id="enc_repo_test", template_name="礼拜堂稳定版")

            encounter_repo.close()
            template_repo.close()

    def test_list_templates_returns_saved_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            template_repo = EncounterTemplateRepository(Path(tmp_dir) / "encounter_templates.json")
            encounter_repo.save(build_encounter())
            save_service = SaveEncounterTemplate(encounter_repo, template_repo)
            list_service = ListEncounterTemplates(template_repo)

            save_service.execute(encounter_id="enc_repo_test", template_name="B")
            save_service.execute(encounter_id="enc_repo_test", template_name="A")

            templates = list_service.execute()

            self.assertEqual([item["name"] for item in templates], ["A", "B"])
            encounter_repo.close()
            template_repo.close()

    def test_restore_template_overwrites_target_encounter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            template_repo = EncounterTemplateRepository(Path(tmp_dir) / "encounter_templates.json")
            source = build_encounter()
            encounter_repo.save(source)
            template = SaveEncounterTemplate(encounter_repo, template_repo).execute(
                encounter_id=source.encounter_id,
                template_name="礼拜堂稳定版",
            )
            modified = build_encounter()
            modified.name = "Broken"
            modified.encounter_id = "enc_restore_target"
            encounter_repo.save(modified)
            restore_service = RestoreEncounterFromTemplate(encounter_repo, template_repo)

            restored = restore_service.execute(
                template_id=str(template["template_id"]),
                target_encounter_id="enc_restore_target",
            )

            self.assertIsInstance(restored, Encounter)
            self.assertEqual(restored.encounter_id, "enc_restore_target")
            self.assertEqual(restored.name, "Repository Test Encounter")
            persisted = encounter_repo.get("enc_restore_target")
            assert persisted is not None
            self.assertEqual(persisted.name, "Repository Test Encounter")
            encounter_repo.close()
            template_repo.close()

    def test_create_encounter_from_template_clones_snapshot_with_new_id_and_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            template_repo = EncounterTemplateRepository(Path(tmp_dir) / "encounter_templates.json")
            source = build_encounter()
            encounter_repo.save(source)
            template = SaveEncounterTemplate(encounter_repo, template_repo).execute(
                encounter_id=source.encounter_id,
                template_name="礼拜堂稳定版",
            )
            create_service = CreateEncounterFromTemplate(encounter_repo, template_repo)

            created = create_service.execute(
                template_id=str(template["template_id"]),
                encounter_id="enc_clone_001",
                encounter_name="新副本",
            )

            self.assertEqual(created.encounter_id, "enc_clone_001")
            self.assertEqual(created.name, "新副本")
            self.assertEqual(created.map.name, source.map.name)
            persisted = encounter_repo.get("enc_clone_001")
            assert persisted is not None
            self.assertEqual(persisted.name, "新副本")
            encounter_repo.close()
            template_repo.close()


if __name__ == "__main__":
    unittest.main()
