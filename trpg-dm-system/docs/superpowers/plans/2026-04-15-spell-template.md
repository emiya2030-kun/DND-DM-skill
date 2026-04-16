# Spell Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为项目建立独立的静态法术模板知识库，并把即时法术结算与持续效果挂载统一迁移到这套模板上。

**Architecture:** 新增 `data/knowledge/spell_definitions.json` 作为唯一静态法术模板事实源，并通过 `SpellDefinitionRepository` 读取。战斗服务层继续保留 `EncounterCastSpell`、`ExecuteSaveSpell`、`SavingThrowResult` 等入口，但它们不再依赖实体内嵌整份模板，而是基于 `spell_id` 查模板；若法术需要持续效果，则由模板的 `effect_templates` 在运行时实例化为目标实体的 `turn_effects`。

**Tech Stack:** Python 3.9, JSON knowledge file, unittest

---

### Task 1: 建立静态法术知识库文件与最小读取仓储

**Files:**
- Create: `data/knowledge/spell_definitions.json`
- Create: `tools/repositories/spell_definition_repository.py`
- Modify: `tools/repositories/__init__.py`
- Test: `test/test_spell_definition_repository.py`

- [ ] **Step 1: 写失败测试，锁定 JSON 模板仓储能按 `spell_id` 读取**

```python
def test_get_returns_spell_definition_by_id():
    repo = SpellDefinitionRepository(Path("data/knowledge/spell_definitions.json"))
    spell = repo.get("fireball")
    assert spell["id"] == "fireball"
    assert spell["on_cast"]["on_failed_save"]["damage_parts"][0]["formula"] == "8d6"
```

- [ ] **Step 2: 写失败测试，锁定未知 `spell_id` 返回 `None`**

```python
def test_get_returns_none_for_unknown_spell():
    repo = SpellDefinitionRepository(Path("data/knowledge/spell_definitions.json"))
    assert repo.get("missing_spell") is None
```

- [ ] **Step 3: 创建最小知识库样本**

首批只放：

- `fireball`
- `hold_person`
- `hex`

结构必须包含：

- `base`
- `targeting`
- `resolution`
- `on_cast`
- `effect_templates`
- `scaling`

- [ ] **Step 4: 实现最小读取仓储**

```python
class SpellDefinitionRepository:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load_all(self) -> dict[str, dict[str, object]]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return dict(data.get("spell_definitions") or {})

    def get(self, spell_id: str) -> dict[str, object] | None:
        return self.load_all().get(spell_id)
```

- [ ] **Step 5: 运行定向测试**

Run: `python3 -m unittest test.test_spell_definition_repository -v`
Expected: PASS

### Task 2: 让 `EncounterCastSpell` 优先从静态知识库取模板

**Files:**
- Modify: `tools/services/spells/encounter_cast_spell.py`
- Modify: `tools/services/__init__.py`
- Test: `test/test_encounter_cast_spell.py`

- [ ] **Step 1: 写失败测试，锁定 `spell_id` 可通过静态知识库解析**

```python
def test_execute_reads_spell_definition_from_global_repository():
    result = service.execute(
        encounter_id="enc_cast_spell_test",
        spell_id="fireball",
        target_ids=["ent_enemy_iron_duster_001"],
    )
    self.assertEqual(result["spell_id"], "fireball")
    self.assertEqual(result["spell_name"], "Fireball")
```

- [ ] **Step 2: 保留兼容顺序，但把全局仓储提到前面**

推荐顺序：

1. `SpellDefinitionRepository`
2. `encounter.metadata.spell_definitions`
3. `caster.source_ref.spell_definitions`
4. `caster.spells`

- [ ] **Step 3: 运行定向测试**

Run: `python3 -m unittest test.test_encounter_cast_spell -v`
Expected: PASS

### Task 3: 把豁免法术即时结算切到 `on_cast`

**Files:**
- Modify: `tools/services/combat/save_spell/execute_save_spell.py`
- Modify: `tools/services/combat/save_spell/saving_throw_result.py`
- Test: `test/test_execute_save_spell.py`
- Test: `test/test_saving_throw_result.py`

- [ ] **Step 1: 写失败测试，锁定 `on_cast.on_failed_save` / `on_cast.on_successful_save` 新主路径**

测试要覆盖：

- 失败全伤
- 成功半伤
- 失败附状态
- 成功无伤无状态

- [ ] **Step 2: 兼容旧字段，但新主路径优先读 `on_cast`**

优先级：

1. `on_cast`
2. 旧 `failed_save_outcome / successful_save_outcome`
3. 旧手传 `hp_change_on_failed_save`

- [ ] **Step 3: 把 `apply_conditions` 映射到现有 `UpdateConditions`**

- [ ] **Step 4: 继续复用现有 `damage_parts + ResolveDamageParts`**

- [ ] **Step 5: 运行定向测试**

Run: `python3 -m unittest test.test_execute_save_spell test.test_saving_throw_result -v`
Expected: PASS

### Task 4: 新增 `effect_templates -> turn_effects` 实例化

**Files:**
- Create: `tools/services/spells/build_turn_effect_instance.py`
- Modify: `tools/services/combat/save_spell/saving_throw_result.py`
- Test: `test/test_build_turn_effect_instance.py`
- Modify: `test/test_execute_save_spell.py`

- [ ] **Step 1: 写失败测试，锁定模板会被实例化成目标实体的 `turn_effects`**

```python
def test_failed_save_can_attach_turn_effect_from_template():
    result = service.execute(
        encounter_id="enc_execute_save_spell_test",
        target_id="ent_enemy_iron_duster_001",
        spell_id="hold_person",
        base_roll=4,
    )
    updated = encounter_repo.get("enc_execute_save_spell_test")
    target = updated.entities["ent_enemy_iron_duster_001"]
    self.assertEqual(len(target.turn_effects), 1)
    self.assertEqual(target.turn_effects[0]["trigger"], "end_of_turn")
    self.assertEqual(target.turn_effects[0]["save"]["dc"], 13)
```

- [ ] **Step 2: 实现模板实例化 helper**

它至少负责补：

- `effect_id`
- `name`
- `source_entity_id`
- `source_name`
- `source_type`
- `source_ref`
- `save.dc`

- [ ] **Step 3: 在即时 outcome 执行完成后，按 `apply_turn_effects` 挂到目标实体**

- [ ] **Step 4: 运行定向测试**

Run: `python3 -m unittest test.test_build_turn_effect_instance test.test_execute_save_spell -v`
Expected: PASS

### Task 5: 补回归与运行手册

**Files:**
- Modify: `docs/llm-runtime-tool-guide.md`
- Modify: `test/test_turn_effects.py`
- Modify: `test/test_encounter_service.py`

- [ ] **Step 1: 更新运行手册**

补充：

- 法术模板来自 `data/knowledge/spell_definitions.json`
- `spell_id` 是静态模板入口
- `turn_effects` 是运行时实例，不是静态模板本体

- [ ] **Step 2: 回归 `turn_effects` 现有测试**

确认：

- `StartTurn` / `EndTurn` 仍然只处理运行时实例
- 不直接依赖静态模板对象

- [ ] **Step 3: 跑全量测试**

Run: `python3 -m unittest discover -s test -p 'test_*.py'`
Expected: PASS

- [ ] **Step 4: 检查最终差异**

Run: `git diff -- data/knowledge tools/repositories tools/services/spells tools/services/combat/save_spell tools/services/encounter/turns test docs/llm-runtime-tool-guide.md`
Expected: only spell template knowledge base, repository, save spell integration, turn effect instantiation, tests, and runtime docs changes
