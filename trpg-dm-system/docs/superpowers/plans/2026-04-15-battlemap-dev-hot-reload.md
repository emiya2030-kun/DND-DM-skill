# Battlemap Dev Hot Reload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 battlemap 本地预览增加开发模式热重载，让 Python/HTML/CSS 相关改动能自动刷新浏览器并加载新 worker 代码。

**Architecture:** 保留现有 `run_battlemap_localhost.py` 作为普通 worker 服务，新建 `run_battlemap_dev.py` 作为稳定 supervisor。supervisor 监听文件变化并重启 worker，同时提供 `/dev/reload` 给浏览器轮询；dev 页面额外注入 reload polling 脚本，普通页面不受影响。

**Tech Stack:** Python 3、unittest、http.server、subprocess、watchdog

---

### Task 1: 给页面注入可选 dev reload 脚本

**Files:**
- Modify: `scripts/run_battlemap_localhost.py`
- Modify: `test/test_run_battlemap_localhost.py`

- [ ] **Step 1: Write the failing test**

```python
def test_render_localhost_page_can_inject_dev_reload_runtime(self) -> None:
    html = render_localhost_battlemap_page(
        encounter=encounter,
        page_title="Battlemap Dev",
        dev_reload_path="/dev/reload",
    )
    self.assertIn("/dev/reload", html)
    self.assertIn("window.__BATTLEMAP_DEV__", html)
    self.assertIn("window.location.reload()", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_run_battlemap_localhost.RunBattlemapLocalhostTests.test_render_localhost_page_can_inject_dev_reload_runtime`

Expected: FAIL，当前页面只注入 encounter state 轮询脚本

- [ ] **Step 3: Write minimal implementation**

```python
def render_localhost_battlemap_page(*, encounter, page_title, dev_reload_path=None):
    ...
    if dev_reload_path:
        polling_script += _build_dev_reload_script(dev_reload_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_run_battlemap_localhost.RunBattlemapLocalhostTests.test_render_localhost_page_can_inject_dev_reload_runtime`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system add \
  scripts/run_battlemap_localhost.py \
  test/test_run_battlemap_localhost.py
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system commit -m "feat: add optional dev reload script injection"
```

### Task 2: 新增 dev supervisor 的最小可测核心

**Files:**
- Create: `scripts/run_battlemap_dev.py`
- Create: `test/test_run_battlemap_dev.py`

- [ ] **Step 1: Write the failing test**

```python
def test_reload_state_bumps_token_when_mark_restarted(self) -> None:
    state = ReloadState()
    before = state.current_token
    state.mark_restarted(worker_port=8871)
    self.assertNotEqual(before, state.current_token)
    self.assertEqual(state.worker_port, 8871)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_run_battlemap_dev.RunBattlemapDevTests.test_reload_state_bumps_token_when_mark_restarted`

Expected: FAIL，文件不存在或类未定义

- [ ] **Step 3: Write minimal implementation**

```python
class ReloadState:
    def __init__(self) -> None:
        self.current_token = _new_reload_token()
        self.worker_port = None

    def mark_restarted(self, worker_port: int) -> None:
        self.worker_port = worker_port
        self.current_token = _new_reload_token()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_run_battlemap_dev.RunBattlemapDevTests.test_reload_state_bumps_token_when_mark_restarted`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system add \
  scripts/run_battlemap_dev.py \
  test/test_run_battlemap_dev.py
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system commit -m "feat: add dev reload state core"
```

### Task 3: 暴露 `/dev/reload` 并返回当前 token

**Files:**
- Modify: `scripts/run_battlemap_dev.py`
- Modify: `test/test_run_battlemap_dev.py`

- [ ] **Step 1: Write the failing test**

```python
def test_reload_payload_contains_current_token_and_worker_port(self) -> None:
    state = ReloadState()
    state.mark_restarted(worker_port=8871)
    payload = build_reload_payload(state)
    self.assertEqual(payload["worker_port"], 8871)
    self.assertEqual(payload["reload_token"], state.current_token)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_run_battlemap_dev.RunBattlemapDevTests.test_reload_payload_contains_current_token_and_worker_port`

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
def build_reload_payload(state: ReloadState) -> dict[str, object]:
    return {
        "reload_token": state.current_token,
        "worker_port": state.worker_port,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_run_battlemap_dev.RunBattlemapDevTests.test_reload_payload_contains_current_token_and_worker_port`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system add \
  scripts/run_battlemap_dev.py \
  test/test_run_battlemap_dev.py
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system commit -m "feat: expose dev reload payload"
```

### Task 4: 接入 watchdog 文件监听与 token 刷新

**Files:**
- Modify: `scripts/run_battlemap_dev.py`
- Modify: `test/test_run_battlemap_dev.py`

- [ ] **Step 1: Write the failing test**

```python
def test_watch_handler_marks_reload_on_python_file_change(self) -> None:
    state = ReloadState()
    handler = BattlemapDevWatchHandler(restart_callback=lambda: state.mark_restarted(worker_port=8872))
    before = state.current_token
    handler._handle_path("/tmp/demo.py")
    self.assertNotEqual(before, state.current_token)
    self.assertEqual(state.worker_port, 8872)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_run_battlemap_dev.RunBattlemapDevTests.test_watch_handler_marks_reload_on_python_file_change`

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
class BattlemapDevWatchHandler(FileSystemEventHandler):
    def __init__(self, restart_callback):
        self.restart_callback = restart_callback

    def _handle_path(self, path: str) -> None:
        if _should_reload_path(path):
            self.restart_callback()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_run_battlemap_dev.RunBattlemapDevTests.test_watch_handler_marks_reload_on_python_file_change`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system add \
  scripts/run_battlemap_dev.py \
  test/test_run_battlemap_dev.py
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system commit -m "feat: watch project files for dev reload"
```

### Task 5: 组装 dev supervisor 并做回归验证

**Files:**
- Modify: `scripts/run_battlemap_dev.py`
- Modify: `scripts/run_battlemap_localhost.py`
- Modify: `test/test_run_battlemap_dev.py`
- Modify: `test/test_run_battlemap_localhost.py`

- [ ] **Step 1: Run focused tests**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_run_battlemap_localhost test.test_run_battlemap_dev`

Expected: PASS

- [ ] **Step 2: Run full regression**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest discover -s test -p 'test_*.py'`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system add \
  scripts/run_battlemap_dev.py \
  scripts/run_battlemap_localhost.py \
  test/test_run_battlemap_dev.py \
  test/test_run_battlemap_localhost.py
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system commit -m "feat: add battlemap dev hot reload supervisor"
```
