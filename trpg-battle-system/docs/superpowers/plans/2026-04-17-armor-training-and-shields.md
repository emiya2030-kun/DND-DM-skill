# Armor Training And Shields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把护甲受训与盾牌像武器一样接入战斗运行时，并在攻击、豁免、施法、状态投影中生效。

**Architecture:** 新增护甲知识库与集中解析器，负责把运行时装备、职业受训和模板规则合并成统一防御快照。攻击/豁免/施法链只读取这份快照，不各自实现护甲规则；`GetEncounterState` 复用同一结果做前端投影。

**Tech Stack:** Python 3、unittest、TinyDB、现有 `tools.services` / `tools.repositories` 结构

---

### Task 1: 护甲知识库与仓库

**Files:**
- Create: `data/knowledge/armor_definitions.json`
- Create: `tools/repositories/armor_definition_repository.py`
- Modify: `tools/core/config.py`
- Modify: `tools/repositories/__init__.py`
- Test: `test/test_armor_definition_repository.py`

- [ ] **Step 1: 写失败测试**

```python
class ArmorDefinitionRepositoryTests(unittest.TestCase):
    def test_get_returns_armor_definition(self) -> None:
        repo = ArmorDefinitionRepository(self.knowledge_path)
        definition = repo.get("chain_mail")
        self.assertEqual(definition["category"], "heavy")
        self.assertEqual(definition["ac"]["base"], 16)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest test.test_armor_definition_repository -v`
Expected: FAIL，提示 `ArmorDefinitionRepository` 不存在或导入失败。

- [ ] **Step 3: 写最小实现**

```python
ARMOR_DEFINITIONS_PATH = KNOWLEDGE_DIR / "armor_definitions.json"


class ArmorDefinitionRepository:
    def load_all(self) -> dict[str, dict[str, Any]]:
        ...

    def get(self, armor_id: str) -> dict[str, Any] | None:
        ...
```

- [ ] **Step 4: 再跑测试确认通过**

Run: `python3 -m unittest test.test_armor_definition_repository -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add data/knowledge/armor_definitions.json tools/core/config.py tools/repositories/__init__.py tools/repositories/armor_definition_repository.py test/test_armor_definition_repository.py
git commit -m "feat: add armor definitions repository"
```

### Task 2: entity 字段与护甲解析器

**Files:**
- Modify: `tools/models/encounter_entity.py`
- Create: `tools/services/combat/defense/armor_profile_resolver.py`
- Create: `tools/services/combat/defense/__init__.py`
- Test: `test/test_armor_profile_resolver.py`
- Test: `test/test_models.py`

- [ ] **Step 1: 写失败测试**

```python
def test_resolve_chain_mail_and_shield_for_fighter(self) -> None:
    actor = EncounterEntity(
        ...,
        ac=10,
        equipped_armor={"armor_id": "chain_mail"},
        equipped_shield={"armor_id": "shield"},
        class_features={"fighter": {"level": 1}},
    )
    profile = ArmorProfileResolver(ArmorDefinitionRepository(self.knowledge_path)).resolve(actor)
    self.assertEqual(profile["base_ac"], 18)
    self.assertFalse(profile["wearing_untrained_armor"])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest test.test_armor_profile_resolver test.test_models -v`
Expected: FAIL，提示 `EncounterEntity` 不接受新字段或 `ArmorProfileResolver` 不存在。

- [ ] **Step 3: 写最小实现**

```python
@dataclass
class EncounterEntity:
    equipped_armor: dict[str, Any] | None = None
    equipped_shield: dict[str, Any] | None = None


class ArmorProfileResolver:
    def resolve(self, actor: EncounterEntity) -> dict[str, Any]:
        return {
            "base_ac": ...,
            "armor_training": ...,
            "speed_penalty_feet": ...,
            "wearing_untrained_armor": ...,
        }
```

- [ ] **Step 4: 再跑测试确认通过**

Run: `python3 -m unittest test.test_armor_profile_resolver test.test_models -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tools/models/encounter_entity.py tools/services/combat/defense/__init__.py tools/services/combat/defense/armor_profile_resolver.py test/test_armor_profile_resolver.py test/test_models.py
git commit -m "feat: resolve runtime armor training profiles"
```

### Task 3: 接入攻击、豁免与施法限制

**Files:**
- Modify: `tools/services/combat/attack/attack_roll_request.py`
- Modify: `tools/services/combat/save_spell/saving_throw_request.py`
- Modify: `tools/services/spells/encounter_cast_spell.py`
- Test: `test/test_attack_roll_request.py`
- Test: `test/test_saving_throw_request.py`
- Test: `test/test_encounter_cast_spell.py`

- [ ] **Step 1: 写失败测试**

```python
def test_execute_adds_disadvantage_for_untrained_armor_dex_attack(self) -> None:
    request = AttackRollRequest(repo, weapon_definition_repository=weapon_repo).execute(...)
    self.assertEqual(request.context["vantage"], "disadvantage")
    self.assertIn("armor_untrained", request.context["vantage_sources"]["disadvantage"])

def test_execute_marks_disadvantage_for_untrained_armor_dex_save(self) -> None:
    request = SavingThrowRequest(repo).execute(...)
    self.assertEqual(request.context["vantage"], "disadvantage")
    self.assertIn("armor_untrained", request.context["vantage_sources"]["disadvantage"])

def test_execute_rejects_spellcasting_in_untrained_armor(self) -> None:
    with self.assertRaisesRegex(ValueError, "armor_training_required_for_spellcasting"):
        EncounterCastSpell(repo, AppendEvent(event_repo)).execute(...)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest test.test_attack_roll_request test.test_saving_throw_request test.test_encounter_cast_spell -v`
Expected: FAIL，对应断言不成立或缺少新字段。

- [ ] **Step 3: 写最小实现**

```python
armor_profile = self.armor_profile_resolver.resolve(actor)
if armor_profile["wearing_untrained_armor"] and modifier in {"str", "dex"}:
    vantage_sources["disadvantage"].append("armor_untrained")

if armor_profile["wearing_untrained_armor"]:
    raise ValueError("armor_training_required_for_spellcasting")
```

- [ ] **Step 4: 再跑测试确认通过**

Run: `python3 -m unittest test.test_attack_roll_request test.test_saving_throw_request test.test_encounter_cast_spell -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tools/services/combat/attack/attack_roll_request.py tools/services/combat/save_spell/saving_throw_request.py tools/services/spells/encounter_cast_spell.py test/test_attack_roll_request.py test/test_saving_throw_request.py test/test_encounter_cast_spell.py
git commit -m "feat: apply armor training penalties in combat resolution"
```

### Task 4: 状态投影与最终回归

**Files:**
- Modify: `tools/services/encounter/get_encounter_state.py`
- Test: `test/test_get_encounter_state.py`
- Test: `test/test_start_turn.py`

- [ ] **Step 1: 写失败测试**

```python
def test_execute_projects_armor_breakdown_and_speed_penalty(self) -> None:
    state = GetEncounterState(repo, event_repo).execute("enc_state_test")
    current = state["current_turn_entity"]
    self.assertEqual(current["ac"], 18)
    self.assertEqual(current["ac_breakdown"]["base_armor_ac"], 16)
    self.assertEqual(current["ac_breakdown"]["shield_bonus"], 2)
    self.assertEqual(current["speed_penalty_feet"], 10)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest test.test_get_encounter_state -v`
Expected: FAIL，状态里没有新投影字段。

- [ ] **Step 3: 写最小实现**

```python
armor_profile = self.armor_profile_resolver.resolve(entity)
return {
    ...,
    "armor": armor_profile["armor"],
    "shield": armor_profile["shield"],
    "armor_training": armor_profile["armor_training"],
    "ac_breakdown": armor_profile["ac_breakdown"],
    "speed_penalty_feet": armor_profile["speed_penalty_feet"],
}
```

- [ ] **Step 4: 运行聚焦回归**

Run: `python3 -m unittest test.test_armor_definition_repository test.test_armor_profile_resolver test.test_attack_roll_request test.test_saving_throw_request test.test_encounter_cast_spell test.test_get_encounter_state -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tools/services/encounter/get_encounter_state.py test/test_get_encounter_state.py test/test_start_turn.py
git commit -m "feat: project armor training and shield state"
```

### Task 5: 最终验证

**Files:**
- Modify: 无
- Test: `test/`

- [ ] **Step 1: 运行最终回归**

Run: `python3 -m unittest test.test_armor_definition_repository test.test_armor_profile_resolver test.test_attack_roll_request test.test_saving_throw_request test.test_encounter_cast_spell test.test_execute_attack test.test_resolve_saving_throw test.test_get_encounter_state -v`
Expected: PASS

- [ ] **Step 2: 检查工作区**

Run: `git status --short`
Expected: 只包含本轮预期文件改动。

- [ ] **Step 3: 提交**

```bash
git add .
git commit -m "feat: add armor training and shield combat rules"
```
