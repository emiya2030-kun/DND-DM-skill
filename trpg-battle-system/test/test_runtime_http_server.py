from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from runtime.context import build_runtime_context
from runtime.http_server import build_runtime_handler_class
from runtime.http_server import ThreadingHTTPServer


class RuntimeHttpServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.context = build_runtime_context(data_dir=Path(self.temp_dir.name))
        handler_cls = build_runtime_handler_class(runtime_context=self.context)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.context.close()
        self.temp_dir.cleanup()

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, object] | None = None,
    ) -> tuple[int, dict[str, object]]:
        headers = {}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")

        request = Request(f"{self.base_url}{path}", data=data, method=method, headers=headers)
        try:
            with urlopen(request, timeout=5) as response:
                body = response.read().decode("utf-8")
                return response.status, json.loads(body)
        except HTTPError as error:
            body = error.read().decode("utf-8")
            return error.code, json.loads(body)

    def _request_raw(
        self,
        method: str,
        path: str,
        *,
        body: bytes,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, payload
        finally:
            connection.close()

    def test_health_endpoint_returns_ok_payload(self) -> None:
        status, payload = self._request("GET", "/runtime/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("commands", payload)
        self.assertIn("execute_attack", payload["commands"])

    def test_unknown_command_returns_structured_json_payload(self) -> None:
        status, payload = self._request(
            "POST",
            "/runtime/command",
            payload={"command": "unknown_command", "args": {"encounter_id": "enc_missing"}},
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "unknown_command")

    def test_encounter_state_requires_encounter_id_and_returns_json_error(self) -> None:
        status, payload = self._request("GET", "/runtime/encounter-state")
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "invalid_request")

    def test_command_endpoint_rejects_malformed_json_with_stable_json_error(self) -> None:
        status, payload = self._request_raw(
            "POST",
            "/runtime/command",
            body=b"{",
            headers={"Content-Type": "application/json", "Content-Length": "1"},
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "invalid_json")

    def test_command_endpoint_rejects_non_object_args(self) -> None:
        status, payload = self._request(
            "POST",
            "/runtime/command",
            payload={"command": "start_random_encounter", "args": []},
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "invalid_request")
        self.assertEqual(payload["message"], "args must be an object")

    def test_command_end_turn_and_advance_missing_encounter_id_returns_command_error_payload(self) -> None:
        status, payload = self._request(
            "POST",
            "/runtime/command",
            payload={"command": "end_turn_and_advance", "args": {}},
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "end_turn_and_advance")
        self.assertEqual(payload["error_code"], "encounter_id is required")

    def test_command_endpoint_rejects_invalid_content_length_with_stable_json_error(self) -> None:
        status, payload = self._request_raw(
            "POST",
            "/runtime/command",
            body=b"{}",
            headers={"Content-Type": "application/json", "Content-Length": "abc"},
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "invalid_request")

    def test_command_execution_unexpected_exception_returns_internal_error_json(self) -> None:
        with patch("runtime.http_server.execute_runtime_command", side_effect=RuntimeError("boom")):
            status, payload = self._request(
                "POST",
                "/runtime/command",
                payload={"command": "start_random_encounter", "args": {}},
            )

        self.assertEqual(status, 500)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "internal_error")
