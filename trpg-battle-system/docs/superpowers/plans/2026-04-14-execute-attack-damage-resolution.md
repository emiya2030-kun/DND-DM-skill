# Execute Attack Damage Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `execute_attack` 从手传 `hp_change` 的旧主路径迁移到“系统内部生成武器伤害段、按 `source` 校验 `damage_rolls`、调用 `ResolveDamageParts`、再统一调用 `UpdateHp`”的新主路径，并把结构化 `damage_resolution` 返回给 LLM。

**Architecture:** 保留 `AttackRollRequest` 和 `AttackRollResult` 现有职责，不让它们承担多段伤害规则。`ExecuteAttack` 在命中后读取武器定义，内部生成 `damage_parts`，严格校验外部传入的 `damage_rolls`，再调用已完成的 `ResolveDamageParts` 结算结构化伤害。`UpdateHp` 继续只负责应用最终生命值变化，因此在新主路径里不再传入 `damage_type`，避免抗性 / 免疫 / 易伤被重复计算。

**Tech Stack:** Python 3.9, unittest

---

### File Structure

- Modify: `tools/services/combat/attack/execute_attack.py`
  - 新增 `damage_rolls` 主路径
  - 注入并调用 `ResolveDamageParts`
  - 内部生成武器 `damage_parts`
  - 严格校验 `damage_rolls.source`
  - 命中后直接调 `UpdateHp`
- Modify: `test/test_execute_attack.py`
  - 用新接口替换旧的 `hp_change` 主路径测试
  - 覆盖单段、多段、暴击、抗性、严格校验、未命中忽略伤害输入
- Optional Modify: `tools/services/__init__.py`
  - 仅当 `ExecuteAttack` 构造签名变更后需要同步导出注释或导入顺序时修改

### Task 1: 先把 `execute_attack` 的新契约写成红灯测试

**Files:**
- Modify: `test/test_execute_attack.py`
- Test: `test/test_execute_attack.py`

- [ ] **Step 1: Write the failing test for single-part weapon damage resolution**

```python
    def test_execute_resolves_weapon_damage_and_returns_breakdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(encounter_repo, append_event),
                UpdateHp(encounter_repo, append_event),
                ResolveDamageParts(),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[
                    {"source": "weapon:rapier:part_0", "rolls": [4]},
                ],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            assert updated is not None

            self.assertTrue(result["resolution"]["hit"])
            self.assertEqual(result["resolution"]["damage_resolution"]["total_damage"], 7)
            self.assertEqual(result["resolution"]["damage_resolution"]["parts"][0]["source"], "weapon:rapier:part_0")
            self.assertEqual(result["resolution"]["damage_resolution"]["parts"][0]["adjusted_total"], 7)
            self.assertEqual(result["resolution"]["hp_update"]["adjusted_hp_change"], 7)
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 2)
```

- [ ] **Step 2: Write the failing test for critical hit multi-part damage**

```python
    def test_execute_resolves_multi_part_damage_on_critical_hit(self) -> None:
        actor = build_actor()
        actor.weapons = [
            {
                "weapon_id": "infernal_rapier",
                "name": "Infernal Rapier",
                "attack_bonus": 5,
                "damage": [
                    {"formula": "1d8+3", "type": "piercing"},
                    {"formula": "1d8", "type": "fire"},
                ],
                "properties": ["finesse"],
                "range": {"normal": 5, "long": 5},
            }
        ]
```

```python
            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="infernal_rapier",
                final_total=25,
                dice_rolls={"base_rolls": [20], "modifier": 5},
                damage_rolls=[
                    {"source": "weapon:infernal_rapier:part_0", "rolls": [6, 2]},
                    {"source": "weapon:infernal_rapier:part_1", "rolls": [5, 1]},
                ],
            )

            self.assertTrue(result["resolution"]["is_critical_hit"])
            self.assertEqual(result["resolution"]["damage_resolution"]["parts"][0]["resolved_formula"], "2d8+3")
            self.assertEqual(result["resolution"]["damage_resolution"]["parts"][1]["resolved_formula"], "2d8")
            self.assertEqual(result["resolution"]["damage_resolution"]["total_damage"], 17)
```

- [ ] **Step 3: Write the failing test for target resistance**

```python
    def test_execute_applies_target_resistance_inside_damage_resolution(self) -> None:
        encounter = build_encounter()
        encounter.entities["ent_enemy_goblin_001"].resistances = ["fire"]
        encounter.entities["ent_ally_eric_001"].weapons = [
            {
                "weapon_id": "infernal_rapier",
                "name": "Infernal Rapier",
                "attack_bonus": 5,
                "damage": [
                    {"formula": "1d8+3", "type": "piercing"},
                    {"formula": "1d8", "type": "fire"},
                ],
                "properties": ["finesse"],
                "range": {"normal": 5, "long": 5},
            }
        ]
```

```python
            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="infernal_rapier",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[
                    {"source": "weapon:infernal_rapier:part_0", "rolls": [4]},
                    {"source": "weapon:infernal_rapier:part_1", "rolls": [6]},
                ],
            )

            fire_part = result["resolution"]["damage_resolution"]["parts"][1]
            self.assertEqual(fire_part["adjustment_rule"], "resistance")
            self.assertEqual(fire_part["adjusted_total"], 3)
            self.assertEqual(result["resolution"]["damage_resolution"]["total_damage"], 10)
            self.assertEqual(result["resolution"]["hp_update"]["damage_type"], None)
```

- [ ] **Step 4: Write the failing tests for strict `source` validation**

```python
    def test_execute_rejects_missing_damage_roll_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing_damage_roll_sources: weapon:rapier:part_0"):
            service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[],
            )

    def test_execute_rejects_unknown_damage_roll_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown_damage_roll_sources: weapon:rapier:part_9"):
            service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[
                    {"source": "weapon:rapier:part_0", "rolls": [4]},
                    {"source": "weapon:rapier:part_9", "rolls": [5]},
                ],
            )

    def test_execute_rejects_duplicate_damage_roll_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate_damage_roll_source: weapon:rapier:part_0"):
            service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[
                    {"source": "weapon:rapier:part_0", "rolls": [4]},
                    {"source": "weapon:rapier:part_0", "rolls": [5]},
                ],
            )
```

- [ ] **Step 5: Write the failing test proving misses ignore `damage_rolls`**

```python
    def test_execute_ignores_damage_rolls_when_attack_misses(self) -> None:
        result = service.execute(
            encounter_id="enc_execute_attack_test",
            target_id="ent_enemy_goblin_001",
            weapon_id="rapier",
            final_total=8,
            dice_rolls={"base_rolls": [3], "modifier": 5},
            damage_rolls=[
                {"source": "weapon:rapier:part_0", "rolls": [4]},
            ],
        )

        updated = encounter_repo.get("enc_execute_attack_test")
        assert updated is not None
        self.assertFalse(result["resolution"]["hit"])
        self.assertNotIn("damage_resolution", result["resolution"])
        self.assertNotIn("hp_update", result["resolution"])
        self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 9)
```

- [ ] **Step 6: Run the targeted test file to verify it fails**

Run: `python3 -m unittest test.test_execute_attack`
Expected: FAIL because `ExecuteAttack` 还没有 `damage_rolls` 主路径，也没有 `ResolveDamageParts` 注入和 `damage_resolution` 返回结构

- [ ] **Step 7: Commit the red tests**

```bash
git add test/test_execute_attack.py
git commit -m "test: cover execute attack damage resolution flow"
```

### Task 2: 在 `ExecuteAttack` 里接上结构化伤害结算主链路

**Files:**
- Modify: `tools/services/combat/attack/execute_attack.py`
- Test: `test/test_execute_attack.py`

- [ ] **Step 1: Extend the constructor and method signature minimally**

```python
from tools.services.combat.damage import ResolveDamageParts
from tools.services.combat.shared.update_hp import UpdateHp


class ExecuteAttack:
    def __init__(
        self,
        attack_roll_request: AttackRollRequest,
        attack_roll_result: AttackRollResult,
        update_hp: UpdateHp | None = None,
        resolve_damage_parts: ResolveDamageParts | None = None,
    ):
        self.attack_roll_request = attack_roll_request
        self.attack_roll_result = attack_roll_result
        self.update_hp = update_hp
        self.resolve_damage_parts = resolve_damage_parts or ResolveDamageParts()
```

```python
    def execute(
        self,
        *,
        encounter_id: str,
        target_id: str,
        weapon_id: str,
        final_total: int,
        dice_rolls: dict[str, Any],
        damage_rolls: list[dict[str, Any]] | None = None,
        vantage: str = "normal",
        description: str | None = None,
        concentration_vantage: str = "normal",
        include_encounter_state: bool = False,
        metadata: dict[str, Any] | None = None,
        rolled_at: str | None = None,
    ) -> dict[str, Any]:
```

- [ ] **Step 2: Stop using `AttackRollResult` as the HP application point in the new path**

```python
        resolution = self.attack_roll_result.execute(
            encounter_id=encounter_id,
            roll_result=roll_result,
            attack_name=request.context.get("attack_name"),
            attack_kind=request.context.get("attack_kind"),
            concentration_vantage=concentration_vantage,
        )
```

Add this immediate short-circuit:

```python
        if resolution["hit"]:
            damage_resolution = self._resolve_weapon_damage(
                encounter_id=encounter_id,
                actor_entity_id=request.actor_entity_id,
                target_id=target_id,
                weapon_id=weapon_id,
                is_critical_hit=resolution["is_critical_hit"],
                damage_rolls=damage_rolls,
            )
            resolution["damage_resolution"] = damage_resolution
            resolution["hp_update"] = self._apply_resolved_damage(
                encounter_id=encounter_id,
                target_id=target_id,
                source_entity_id=request.actor_entity_id,
                attack_name=request.context.get("attack_name") or "Attack",
                damage_resolution=damage_resolution,
                is_critical_hit=resolution["is_critical_hit"],
                concentration_vantage=concentration_vantage,
            )
```

- [ ] **Step 3: Add private helpers for weapon parts and strict `source` validation**

```python
    def _build_weapon_damage_parts(self, weapon_id: str, weapon: dict[str, Any]) -> list[dict[str, Any]]:
        raw_parts = weapon.get("damage", [])
        if not isinstance(raw_parts, list) or not raw_parts:
            raise ValueError(f"weapon '{weapon_id}' has no damage parts")

        damage_parts: list[dict[str, Any]] = []
        for index, part in enumerate(raw_parts):
            formula = part.get("formula")
            damage_type = part.get("type")
            if not isinstance(formula, str) or not formula.strip():
                raise ValueError(f"weapon '{weapon_id}' has invalid damage formula at part {index}")
            damage_parts.append(
                {
                    "source": f"weapon:{weapon_id}:part_{index}",
                    "formula": formula,
                    "damage_type": damage_type,
                }
            )
        return damage_parts
```

```python
    def _index_damage_rolls(self, damage_rolls: list[dict[str, Any]] | None) -> dict[str, list[int]]:
        indexed: dict[str, list[int]] = {}
        for item in damage_rolls or []:
            source = item.get("source")
            if source in indexed:
                raise ValueError(f"duplicate_damage_roll_source: {source}")
            indexed[source] = item.get("rolls", [])
        return indexed
```

```python
    def _validate_damage_roll_sources(
        self,
        *,
        expected_sources: list[str],
        actual_sources: list[str],
    ) -> None:
        missing = sorted(set(expected_sources) - set(actual_sources))
        unknown = sorted(set(actual_sources) - set(expected_sources))
        if missing:
            raise ValueError(f"missing_damage_roll_sources: {', '.join(missing)}")
        if unknown:
            raise ValueError(f"unknown_damage_roll_sources: {', '.join(unknown)}")
```

- [ ] **Step 4: Call `ResolveDamageParts` with target traits and avoid double trait application**

```python
    def _resolve_weapon_damage(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        target_id: str,
        weapon_id: str,
        is_critical_hit: bool,
        damage_rolls: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        encounter = self.attack_roll_request.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")

        actor = encounter.entities.get(actor_entity_id)
        target = encounter.entities.get(target_id)
        if actor is None or target is None:
            raise ValueError("actor or target not found in encounter")

        weapon = next((item for item in actor.weapons if item.get("weapon_id") == weapon_id), None)
        if weapon is None:
            raise ValueError(f"weapon '{weapon_id}' not found for actor '{actor_entity_id}'")

        damage_parts = self._build_weapon_damage_parts(weapon_id, weapon)
        indexed_rolls = self._index_damage_rolls(damage_rolls)
        expected_sources = [part["source"] for part in damage_parts]
        self._validate_damage_roll_sources(
            expected_sources=expected_sources,
            actual_sources=list(indexed_rolls.keys()),
        )

        return self.resolve_damage_parts.execute(
            damage_parts=damage_parts,
            is_critical_hit=is_critical_hit,
            rolled_values=[indexed_rolls[source] for source in expected_sources],
            resistances=target.resistances,
            immunities=target.immunities,
            vulnerabilities=target.vulnerabilities,
        )
```

```python
    def _apply_resolved_damage(
        self,
        *,
        encounter_id: str,
        target_id: str,
        source_entity_id: str,
        attack_name: str,
        damage_resolution: dict[str, Any],
        is_critical_hit: bool,
        concentration_vantage: str,
    ) -> dict[str, Any]:
        if self.update_hp is None:
            raise ValueError("update_hp service is required when resolving attack damage")
        return self.update_hp.execute(
            encounter_id=encounter_id,
            target_id=target_id,
            hp_change=damage_resolution["total_damage"],
            reason=f"{attack_name} damage",
            damage_type=None,
            from_critical_hit=is_critical_hit,
            source_entity_id=source_entity_id,
            concentration_vantage=concentration_vantage,
        )
```

- [ ] **Step 5: Run the targeted test file to verify the new path passes**

Run: `python3 -m unittest test.test_execute_attack`
Expected: PASS

- [ ] **Step 6: Commit the implementation**

```bash
git add tools/services/combat/attack/execute_attack.py test/test_execute_attack.py
git commit -m "feat: resolve execute attack damage internally"
```

### Task 3: 清理旧主路径依赖并补兼容边界

**Files:**
- Modify: `test/test_execute_attack.py`
- Test: `test/test_execute_attack.py`

- [ ] **Step 1: Replace old `hp_change`-style happy-path tests with the new API everywhere**

Update existing calls like this:

```python
            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [4]}],
                include_encounter_state=True,
            )
```

And update assertions:

```python
            self.assertEqual(result["encounter_state"]["turn_order"][1]["hp"], "2/9 HP (22%) [BLOODIED]")
            self.assertEqual(
                result["resolution"]["damage_resolution"]["parts"][0]["resolved_formula"],
                "1d8+3",
            )
```

- [ ] **Step 2: Add a regression test proving `AttackRollResult` old behavior still works independently**

Do **not** remove `test/test_attack_roll_result.py` coverage. Keep this test green:

```python
    def test_execute_can_auto_apply_damage_after_hit(self) -> None:
        ...
        result = service.execute(
            encounter_id="enc_attack_test",
            attack_name="Rapier",
            hp_change=4,
            damage_reason="Rapier damage",
            damage_type="piercing",
            roll_result=RollResult(...),
        )
```

This locks in the boundary:
- `AttackRollResult` 旧接口继续兼容
- `ExecuteAttack` 新主路径不再依赖它自动扣血

- [ ] **Step 3: Run focused regression tests**

Run: `python3 -m unittest test.test_execute_attack test.test_attack_roll_result test.test_resolve_damage_parts`
Expected: PASS

- [ ] **Step 4: Commit the migration cleanup**

```bash
git add test/test_execute_attack.py test/test_attack_roll_result.py
git commit -m "test: migrate execute attack to damage resolution flow"
```

### Task 4: 全量验证并确认没有打破现有战斗链

**Files:**
- Test: `test/test_execute_attack.py`
- Test: `test/test_attack_roll_result.py`
- Test: `test/test_resolve_damage_parts.py`
- Test: `test/test_update_hp.py`
- Test: `test/test_execute_save_spell.py`
- Test: `test/test_saving_throw_result.py`

- [ ] **Step 1: Run the full suite**

Run: `python3 -m unittest discover -s test -p 'test_*.py'`
Expected: PASS with all combat, save spell, HP, and damage resolution tests green

- [ ] **Step 2: Inspect the changed files and capture the migration boundary**

Run: `git diff -- tools/services/combat/attack/execute_attack.py test/test_execute_attack.py`
Expected: diff shows `hp_change` removed from `ExecuteAttack` 主路径 and `damage_rolls` / `damage_resolution` added

- [ ] **Step 3: Commit the final verified state**

```bash
git add tools/services/combat/attack/execute_attack.py test/test_execute_attack.py
git commit -m "feat: return structured attack damage breakdown"
```
