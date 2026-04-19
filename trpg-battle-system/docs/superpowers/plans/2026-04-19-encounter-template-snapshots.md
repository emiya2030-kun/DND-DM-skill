# Encounter Template Snapshots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 localhost battlemap 开发流程加入多份命名样板快照的保存、列出、恢复和复制能力，保证 UI/地图/角色卡联调可以随时回退。

**Architecture:** 新增独立的样板快照仓储，专门保存完整 `Encounter` 快照及少量元数据；在 localhost handler 上暴露最小 JSON API，并在页面里加一个轻量样板工具区触发保存与恢复。正式遭遇继续走现有 `EncounterRepository`，样板不混入正式遭遇列表。

**Tech Stack:** Python 3、TinyDB、`unittest`、现有 localhost HTML/CSS/JS 拼接模式。

---

### Task 1: 样板仓储与模型契约

**Files:**
- Create: `tools/repositories/encounter_template_repository.py`
- Modify: `tools/repositories/__init__.py`
- Test: `test/test_encounter_template_repository.py`

- [ ] **Step 1: 写失败测试，定义最小仓储行为**

```python
def test_save_and_get_template(self) -> None:
    repo = EncounterTemplateRepository(Path(tmp_dir) / "encounter_templates.json")
    template = {
        "template_id": "tpl_chapel_v1",
        "name": "礼拜堂稳定版",
        "source_encounter_id": "enc_preview_demo",
        "snapshot": build_encounter().to_dict(),
        "created_at": "2026-04-19T00:00:00Z",
        "updated_at": "2026-04-19T00:00:00Z",
    }
    repo.save(template)
    loaded = repo.get("tpl_chapel_v1")
    self.assertEqual(loaded["name"], "礼拜堂稳定版")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m unittest test.test_encounter_template_repository -v`
Expected: `ModuleNotFoundError` 或 `AttributeError`，因为新仓储还不存在。

- [ ] **Step 3: 写最小实现**

```python
class EncounterTemplateRepository:
    def save(self, template_record: dict[str, Any]) -> dict[str, Any]:
        ...

    def get(self, template_id: str) -> dict[str, Any] | None:
        ...

    def delete(self, template_id: str) -> int:
        ...

    def list_templates(self) -> list[dict[str, Any]]:
        ...
```

- [ ] **Step 4: 运行仓储测试确认通过**

Run: `python3 -m unittest test.test_encounter_template_repository -v`
Expected: PASS，覆盖保存、读取、列出排序和删除。

- [ ] **Step 5: 提交本任务**

```bash
git add test/test_encounter_template_repository.py tools/repositories/encounter_template_repository.py tools/repositories/__init__.py
git commit -m "feat: add encounter template repository"
```

### Task 2: 样板服务主链

**Files:**
- Create: `tools/services/encounter/save_encounter_template.py`
- Create: `tools/services/encounter/list_encounter_templates.py`
- Create: `tools/services/encounter/restore_encounter_from_template.py`
- Create: `tools/services/encounter/create_encounter_from_template.py`
- Modify: `tools/services/__init__.py`
- Test: `test/test_encounter_template_services.py`

- [ ] **Step 1: 写失败测试，锁定保存/恢复/复制行为**

```python
def test_save_template_rejects_duplicate_name(self) -> None:
    service.execute(encounter_id="enc_preview_demo", template_name="礼拜堂稳定版")
    with self.assertRaisesRegex(ValueError, "already exists"):
        service.execute(encounter_id="enc_preview_demo", template_name="礼拜堂稳定版")

def test_restore_template_overwrites_target_encounter(self) -> None:
    restored = restore_service.execute(template_id="tpl_chapel_v1", target_encounter_id="enc_preview_demo")
    self.assertEqual(restored.encounter_id, "enc_preview_demo")

def test_create_encounter_from_template_clones_snapshot_with_new_id(self) -> None:
    created = create_service.execute(template_id="tpl_chapel_v1", encounter_id="enc_clone_001", encounter_name="新副本")
    self.assertEqual(created.encounter_id, "enc_clone_001")
    self.assertEqual(created.name, "新副本")
```

- [ ] **Step 2: 运行服务测试确认失败**

Run: `python3 -m unittest test.test_encounter_template_services -v`
Expected: FAIL，因为服务模块和导出尚未实现。

- [ ] **Step 3: 写最小服务实现**

```python
class SaveEncounterTemplate:
    def execute(self, *, encounter_id: str, template_name: str) -> dict[str, Any]:
        encounter = self._encounter_repository.get(encounter_id)
        ...

class RestoreEncounterFromTemplate:
    def execute(self, *, template_id: str, target_encounter_id: str) -> Encounter:
        ...
```

- [ ] **Step 4: 运行服务测试确认通过**

Run: `python3 -m unittest test.test_encounter_template_services -v`
Expected: PASS，覆盖重复名冲突、恢复、复制和列表。

- [ ] **Step 5: 提交本任务**

```bash
git add test/test_encounter_template_services.py tools/services/__init__.py tools/services/encounter/save_encounter_template.py tools/services/encounter/list_encounter_templates.py tools/services/encounter/restore_encounter_from_template.py tools/services/encounter/create_encounter_from_template.py
git commit -m "feat: add encounter template snapshot services"
```

### Task 3: localhost API

**Files:**
- Modify: `scripts/run_battlemap_localhost.py`
- Modify: `test/test_run_battlemap_localhost.py`

- [ ] **Step 1: 写失败测试，锁定 API 路由与状态码**

```python
def test_api_encounter_templates_lists_templates(self) -> None:
    status, payload = self._request_json(base_url, "/api/encounter-templates")
    self.assertEqual(status, 200)
    self.assertIn("templates", payload)

def test_api_encounter_templates_create_returns_201(self) -> None:
    request = Request(..., method="POST", data=b'{"encounter_id":"enc_preview_demo","name":"礼拜堂稳定版"}')
    ...
    self.assertEqual(status, 201)
```

- [ ] **Step 2: 运行定向测试确认失败**

Run: `python3 -m unittest test.test_run_battlemap_localhost.RunBattlemapLocalhostTests.test_api_encounter_templates_lists_templates -v`
Expected: FAIL with `404` or missing handler.

- [ ] **Step 3: 实现最小 API**

```python
def do_POST(self) -> None:
    if parsed.path == "/api/encounter-templates":
        self._create_encounter_template()
        return
    if parsed.path == "/api/encounter-templates/restore":
        self._restore_encounter_template()
        return
```

- [ ] **Step 4: 运行 localhost 测试确认通过**

Run: `python3 -m unittest test.test_run_battlemap_localhost -v`
Expected: PASS，覆盖新旧接口。

- [ ] **Step 5: 提交本任务**

```bash
git add scripts/run_battlemap_localhost.py test/test_run_battlemap_localhost.py
git commit -m "feat: add localhost encounter template APIs"
```

### Task 4: localhost 页面样板工具区

**Files:**
- Modify: `scripts/run_battlemap_localhost.py`
- Modify: `test/test_run_battlemap_localhost.py`

- [ ] **Step 1: 写失败测试，锁定页面工具区壳子**

```python
def test_render_localhost_page_includes_template_controls(self) -> None:
    html = render_localhost_battlemap_page(...)
    self.assertIn('data-role="template-tools"', html)
    self.assertIn('data-action="save-template"', html)
    self.assertIn('data-action="restore-template"', html)
    self.assertIn('data-action="clone-template"', html)
```

- [ ] **Step 2: 运行定向测试确认失败**

Run: `python3 -m unittest test.test_run_battlemap_localhost.RunBattlemapLocalhostTests.test_render_localhost_page_includes_template_controls -v`
Expected: FAIL，因为页面尚未插入工具区。

- [ ] **Step 3: 实现最小工具区和脚本**

```javascript
window.loadEncounterTemplates = async function(){...}
window.saveEncounterTemplate = async function(){...}
window.restoreEncounterTemplate = async function(){...}
window.cloneEncounterFromTemplate = async function(){...}
```

- [ ] **Step 4: 运行 localhost 测试确认通过**

Run: `python3 -m unittest test.test_run_battlemap_localhost -v`
Expected: PASS，页面壳子和脚本字符串都存在。

- [ ] **Step 5: 提交本任务**

```bash
git add scripts/run_battlemap_localhost.py test/test_run_battlemap_localhost.py
git commit -m "feat: add localhost template snapshot controls"
```

### Task 5: 集成验证

**Files:**
- Modify: `data/db/encounter_templates.json`（若运行本地手动保存样板）

- [ ] **Step 1: 运行仓储、服务、localhost 相关测试**

Run: `python3 -m unittest test.test_encounter_template_repository test.test_encounter_template_services test.test_run_battlemap_localhost test.test_render_battlemap_view -v`
Expected: PASS

- [ ] **Step 2: 重启 localhost 预览**

Run: `python3 scripts/run_battlemap_localhost.py --runtime-base-url '' --port 8766`
Expected: 输出 `http://127.0.0.1:8766`

- [ ] **Step 3: 手动验证主链**

1. 页面输入样板名并保存
2. 列表出现新样板
3. 修改当前遭遇后执行恢复
4. 页面轮询后回到样板状态

- [ ] **Step 4: 提交最终集成改动**

```bash
git add .
git commit -m "feat: add named encounter template snapshots"
```
