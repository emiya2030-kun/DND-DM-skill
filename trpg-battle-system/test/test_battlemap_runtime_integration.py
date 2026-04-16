import tempfile
import unittest
from argparse import Namespace
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import Mock, patch

from scripts.run_battlemap_localhost import (
    bootstrap_runtime_encounter,
    main,
    post_runtime_command,
    render_localhost_battlemap_page,
)


class BattlemapRuntimeIntegrationTests(unittest.TestCase):
    def test_bootstrap_runtime_encounter_posts_start_random_command(self) -> None:
        with patch(
            "scripts.run_battlemap_localhost.post_runtime_command",
            return_value={"ok": True},
        ) as post_runtime_command:
            bootstrap_runtime_encounter(
                runtime_base_url="http://127.0.0.1:8771",
                encounter_id="enc_preview_demo",
                theme="forest_road",
            )
        post_runtime_command.assert_called_once_with(
            "http://127.0.0.1:8771",
            command="start_random_encounter",
            args={"encounter_id": "enc_preview_demo", "theme": "forest_road"},
        )

    def test_render_localhost_page_polls_runtime_backed_api(self) -> None:
        html = render_localhost_battlemap_page(
            encounter_id="enc_preview_demo",
            page_title="Battlemap Localhost",
        )
        self.assertIn("/api/encounter-state?encounter_id=", html)
        self.assertIn("fetchLatestEncounterState", html)
        self.assertIn("fetchLatestEncounterState();", html)

    def test_bootstrap_runtime_encounter_raises_when_runtime_returns_not_ok(self) -> None:
        with patch("scripts.run_battlemap_localhost.post_runtime_command", return_value={"ok": False, "error": "boom"}):
            with self.assertRaises(RuntimeError):
                bootstrap_runtime_encounter(
                    runtime_base_url="http://127.0.0.1:8771",
                    encounter_id="enc_preview_demo",
                    theme=None,
                )

    def test_post_runtime_command_raises_runtime_error_when_http_error_body_is_not_json(self) -> None:
        error = HTTPError(
            url="http://127.0.0.1:8771/runtime/command",
            code=502,
            msg="Bad Gateway",
            hdrs=None,
            fp=BytesIO(b"upstream exploded"),
        )
        with patch("scripts.run_battlemap_localhost.urlopen", side_effect=error):
            with self.assertRaises(RuntimeError) as error_context:
                post_runtime_command(
                    "http://127.0.0.1:8771",
                    command="start_random_encounter",
                    args={"encounter_id": "enc_preview_demo"},
                )

        self.assertIn("runtime command request failed: 502", str(error_context.exception))

    def test_main_attempts_runtime_bootstrap_when_runtime_base_url_is_provided(self) -> None:
        fake_server = Mock()
        fake_server.serve_forever.side_effect = RuntimeError("stop")
        with patch(
            "scripts.run_battlemap_localhost.argparse.ArgumentParser.parse_args",
            return_value=Namespace(
                host="127.0.0.1",
                port=8765,
                runtime_base_url="http://127.0.0.1:8771",
                theme="forest_road",
                dev_reload_path=None,
            ),
        ):
            with patch("scripts.run_battlemap_localhost.bootstrap_runtime_encounter") as bootstrap:
                with patch("scripts.run_battlemap_localhost.ThreadingHTTPServer", return_value=fake_server):
                    with self.assertRaises(RuntimeError):
                        main()
        bootstrap.assert_called_once_with(
            runtime_base_url="http://127.0.0.1:8771",
            encounter_id="enc_preview_demo",
            theme="forest_road",
        )


if __name__ == "__main__":
    unittest.main()
