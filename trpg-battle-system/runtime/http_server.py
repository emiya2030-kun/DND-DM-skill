from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from runtime.commands import COMMAND_HANDLERS
from runtime.dispatcher import execute_runtime_command


def build_runtime_handler_class(*, runtime_context):
    class BattleRuntimeHandler(BaseHTTPRequestHandler):
        context = runtime_context
        context_lock = threading.Lock()

        @staticmethod
        def build_health_payload() -> dict[str, object]:
            return {
                "status": "ok",
                "commands": sorted(COMMAND_HANDLERS.keys()),
            }

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/runtime/health":
                self._write_json(200, self.build_health_payload())
                return
            if parsed.path == "/runtime/encounter-state":
                if self.context is None:
                    self._write_error_json(500, "runtime_context_missing", "runtime context not configured")
                    return
                encounter_id = parse_qs(parsed.query).get("encounter_id", [""])[0]
                if not encounter_id.strip():
                    self._write_error_json(400, "invalid_request", "encounter_id is required")
                    return
                with self.context_lock:
                    try:
                        payload = self.context.get_encounter_state(encounter_id)
                    except ValueError as error:
                        self._write_error_json(404, "encounter_not_found", str(error))
                        return
                self._write_json(200, payload)
                return
            self._write_error_json(404, "not_found", "Not Found")

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/runtime/command":
                self._write_error_json(404, "not_found", "Not Found")
                return
            if self.context is None:
                self._write_error_json(500, "runtime_context_missing", "runtime context not configured")
                return

            content_length_header = self.headers.get("Content-Length", "0")
            try:
                content_length = int(content_length_header or "0")
            except (TypeError, ValueError):
                self._write_error_json(400, "invalid_request", "invalid Content-Length header")
                return
            if content_length < 0:
                self._write_error_json(400, "invalid_request", "invalid Content-Length header")
                return

            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body or b"{}")
            except json.JSONDecodeError:
                self._write_error_json(400, "invalid_json", "request body must be valid JSON")
                return
            if not isinstance(payload, dict):
                self._write_error_json(400, "invalid_request", "request body must be a JSON object")
                return

            command = payload.get("command")
            if not isinstance(command, str) or not command.strip():
                self._write_error_json(400, "invalid_request", "command is required")
                return
            args = payload.get("args", {})
            if not isinstance(args, dict):
                self._write_error_json(400, "invalid_request", "args must be an object")
                return

            with self.context_lock:
                try:
                    result = execute_runtime_command(
                        self.context,
                        command=command,
                        args=args,
                        handlers=COMMAND_HANDLERS,
                    )
                except ValueError as error:
                    self._write_error_json(400, "invalid_request", str(error))
                    return
                except Exception:
                    self._write_error_json(500, "internal_error", "internal server error")
                    return
            self._write_json(200, result)

        def _write_json(self, status: int, payload: dict[str, object]) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _write_error_json(self, status: int, error_code: str, message: str) -> None:
            self._write_json(
                status,
                {
                    "ok": False,
                    "error_code": error_code,
                    "message": message,
                },
            )

        def log_message(self, format: str, *args: object) -> None:
            return

    return BattleRuntimeHandler
