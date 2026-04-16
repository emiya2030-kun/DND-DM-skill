"""battlemap dev 热重载监督器测试。"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_battlemap_dev import (
    BattlemapDevWatchHandler,
    ReloadState,
    build_reload_payload,
    build_worker_command,
    should_reload_path,
)


class RunBattlemapDevTests(unittest.TestCase):
    def test_reload_state_bumps_token_when_mark_restarted(self) -> None:
        state = ReloadState()

        before = state.current_token
        state.mark_restarted(worker_port=8871)

        self.assertNotEqual(before, state.current_token)
        self.assertEqual(state.worker_port, 8871)

    def test_reload_payload_contains_current_token_and_worker_port(self) -> None:
        state = ReloadState()
        state.mark_restarted(worker_port=8871)

        payload = build_reload_payload(state)

        self.assertEqual(payload["worker_port"], 8871)
        self.assertEqual(payload["reload_token"], state.current_token)

    def test_watch_handler_marks_reload_on_python_file_change(self) -> None:
        state = ReloadState()
        handler = BattlemapDevWatchHandler(
            restart_callback=lambda: state.mark_restarted(worker_port=8872)
        )

        before = state.current_token
        handler._handle_path("/tmp/demo.py")

        self.assertNotEqual(before, state.current_token)
        self.assertEqual(state.worker_port, 8872)

    def test_should_reload_path_ignores_runtime_database_files(self) -> None:
        self.assertFalse(should_reload_path("/tmp/project/data/db/events.json"))
        self.assertTrue(should_reload_path("/tmp/project/tools/services/demo.py"))

    def test_build_worker_command_includes_dev_reload_path(self) -> None:
        command = build_worker_command(worker_port=8873)

        self.assertIn("scripts/run_battlemap_localhost.py", command[1])
        self.assertIn("--dev-reload-path", command)
        self.assertIn("/dev/reload", command)


if __name__ == "__main__":
    unittest.main()
