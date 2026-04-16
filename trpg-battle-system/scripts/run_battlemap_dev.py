#!/usr/bin/env python3
"""battlemap 开发模式监督器。"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer
except ModuleNotFoundError:  # pragma: no cover - 运行时依赖提示由 main 处理
    FileSystemEvent = object  # type: ignore[assignment]

    class FileSystemEventHandler:  # type: ignore[no-redef]
        pass

    Observer = None  # type: ignore[assignment]


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKER_SCRIPT = PROJECT_ROOT / "scripts" / "run_battlemap_localhost.py"
WATCHED_DIRECTORIES = (
    PROJECT_ROOT / "tools",
    PROJECT_ROOT / "scripts",
    PROJECT_ROOT / "test",
    PROJECT_ROOT / "data" / "examples",
)
WATCHED_SUFFIXES = {".py", ".html", ".css"}
IGNORED_PATH_PARTS = {"__pycache__", ".git", ".pytest_cache", "data/db"}


def _new_reload_token() -> str:
    return f"{datetime.now(timezone.utc).isoformat()}-{time.time_ns()}"


@dataclass
class ReloadState:
    current_token: str = field(default_factory=_new_reload_token)
    worker_port: int | None = None

    def mark_restarted(self, worker_port: int) -> None:
        self.worker_port = worker_port
        self.current_token = _new_reload_token()


def build_reload_payload(state: ReloadState) -> dict[str, object]:
    return {
        "reload_token": state.current_token,
        "worker_port": state.worker_port,
    }


def should_reload_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if any(part in normalized for part in IGNORED_PATH_PARTS):
        return False
    return Path(normalized).suffix.lower() in WATCHED_SUFFIXES


def build_worker_command(
    *,
    worker_port: int,
    worker_host: str = "127.0.0.1",
) -> list[str]:
    return [
        sys.executable,
        str(WORKER_SCRIPT),
        "--host",
        worker_host,
        "--port",
        str(worker_port),
        "--dev-reload-path",
        "/dev/reload",
    ]


def find_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


class BattlemapDevWatchHandler(FileSystemEventHandler):
    def __init__(
        self,
        restart_callback: Callable[[], None],
        cooldown_seconds: float = 0.35,
    ) -> None:
        self.restart_callback = restart_callback
        self.cooldown_seconds = cooldown_seconds
        self._last_restart_at = -cooldown_seconds

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle_event(event)

    def on_created(self, event: FileSystemEvent) -> None:
        self._handle_event(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        self._handle_path(str(getattr(event, "dest_path", "")))

    def _handle_event(self, event: FileSystemEvent) -> None:
        if getattr(event, "is_directory", False):
            return
        self._handle_path(str(getattr(event, "src_path", "")))

    def _handle_path(self, path: str) -> None:
        if not should_reload_path(path):
            return
        now = time.monotonic()
        if now - self._last_restart_at < self.cooldown_seconds:
            return
        self._last_restart_at = now
        self.restart_callback()


class BattlemapWorkerManager:
    def __init__(self, *, worker_host: str = "127.0.0.1") -> None:
        self.worker_host = worker_host
        self.worker_port: int | None = None
        self.process: subprocess.Popen[str] | None = None

    def start(self) -> int:
        self.stop()
        self.worker_port = find_free_port(self.worker_host)
        command = build_worker_command(
            worker_port=self.worker_port,
            worker_host=self.worker_host,
        )
        self.process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._wait_until_ready()
        return self.worker_port

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.process = None
        self.worker_port = None

    def base_url(self) -> str:
        if self.worker_port is None:
            raise RuntimeError("worker not running")
        return f"http://{self.worker_host}:{self.worker_port}"

    def _wait_until_ready(self) -> None:
        deadline = time.time() + 5
        last_error = "worker did not become ready"
        while time.time() < deadline:
            if self.process is None:
                raise RuntimeError("worker process missing")
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate(timeout=1)
                message = stderr.strip() or stdout.strip() or "worker exited unexpectedly"
                raise RuntimeError(message)
            try:
                with urlopen(self.base_url() + "/", timeout=0.5) as response:
                    if response.status == 200:
                        return
            except URLError as error:
                last_error = str(error)
                time.sleep(0.1)
        raise RuntimeError(last_error)


class BattlemapDevSupervisor:
    def __init__(self, *, worker_host: str = "127.0.0.1") -> None:
        self.reload_state = ReloadState()
        self.worker_manager = BattlemapWorkerManager(worker_host=worker_host)
        self._lock = threading.Lock()
        self._observer: Observer | None = None

    def start(self) -> None:
        self.restart_worker()
        self._observer = create_observer(self.restart_worker)
        self._observer.start()

    def close(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=3)
            self._observer = None
        self.worker_manager.stop()

    def restart_worker(self) -> None:
        with self._lock:
            worker_port = self.worker_manager.start()
            self.reload_state.mark_restarted(worker_port)

    def proxy_get(self, path: str) -> tuple[int, dict[str, str], bytes]:
        target_url = self.worker_manager.base_url() + path
        request = Request(target_url, method="GET")
        try:
            with urlopen(request, timeout=5) as response:
                headers = {
                    key: value
                    for key, value in response.headers.items()
                    if key.lower() not in {"transfer-encoding", "connection"}
                }
                return response.status, headers, response.read()
        except HTTPError as error:
            body = error.read()
            headers = {
                key: value
                for key, value in error.headers.items()
                if key.lower() not in {"transfer-encoding", "connection"}
            }
            return error.code, headers, body
        except Exception as error:  # pragma: no cover - 手工运行时兜底
            payload = json.dumps(
                {"error": "worker_unavailable", "detail": str(error)},
                ensure_ascii=False,
            ).encode("utf-8")
            return 503, {"Content-Type": "application/json; charset=utf-8"}, payload


def create_observer(restart_callback: Callable[[], None]) -> Observer:
    if Observer is None:
        raise RuntimeError(
            "开发模式需要安装 watchdog：python3 -m pip install watchdog"
        )
    observer = Observer()
    handler = BattlemapDevWatchHandler(restart_callback=restart_callback)
    for watched_dir in WATCHED_DIRECTORIES:
        observer.schedule(handler, str(watched_dir), recursive=True)
    return observer


class BattlemapDevHandler(BaseHTTPRequestHandler):
    supervisor: BattlemapDevSupervisor | None = None

    def do_GET(self) -> None:
        if self.path == "/dev/reload":
            self._serve_reload_state()
            return
        self._proxy_to_worker()

    def log_message(self, format: str, *args: object) -> None:
        return

    def _serve_reload_state(self) -> None:
        if self.supervisor is None:
            self.send_error(500, "Supervisor not configured")
            return
        payload = json.dumps(
            build_reload_payload(self.supervisor.reload_state),
            ensure_ascii=False,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _proxy_to_worker(self) -> None:
        if self.supervisor is None:
            self.send_error(500, "Supervisor not configured")
            return
        status, headers, body = self.supervisor.proxy_get(self.path)
        self.send_response(status)
        for key, value in headers.items():
            if key.lower() == "content-length":
                continue
            self.send_header(key, value)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run battlemap dev server with hot reload")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8769, type=int)
    args = parser.parse_args()

    supervisor = BattlemapDevSupervisor(worker_host=args.host)
    supervisor.start()
    BattlemapDevHandler.supervisor = supervisor
    server = ThreadingHTTPServer((args.host, args.port), BattlemapDevHandler)
    try:
        print(f"http://{args.host}:{args.port}")
        server.serve_forever()
    finally:
        server.server_close()
        supervisor.close()


if __name__ == "__main__":
    main()
