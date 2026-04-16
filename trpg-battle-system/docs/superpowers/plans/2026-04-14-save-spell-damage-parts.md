# Save Spell Damage Parts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把单目标豁免型法术从 `hp_change_on_failed_save / hp_change_on_success` 旧模式迁移到基于法术模板 outcome 与 `ResolveDamageParts` 的结构化即时结算链路，并支持 condition 字符串结果、戏法成长、高环成长。

**Architecture:** 建立全局法术模板知识库，模板中定义 `failed_save_outcome` / `successful_save_outcome` 与 `scaling`。`ExecuteSaveSpell` 保留完整入口角色，但新主路径改为接收 `damage_rolls`。`SavingThrowResult` 负责根据豁免结果选择 outcome、应用成长、生成 `damage_parts`、调用 `ResolveDamageParts`，然后统一触发 `UpdateHp`、`UpdateConditions` 与 `UpdateEncounterNotes`。旧的整数伤害输入先保留兼容，但不再作为新主路径事实源。

**Tech Stack:** Python 3.9, unittest

---

### File Structure

- Modify: `tools/services/spells/encounter_cast_spell.py`
  - 若当前只从实体侧法术列表读取，需要补上从全局法术模板读取的最小能力
- Modify: `tools/services/combat/save_spell/execute_save_spell.py`
  - 新增 `damage_rolls` 主路径
  - 不再把新主路径的伤害继续手传到 `SavingThrowResult` 旧整数接口
- Modify: `tools/services/combat/save_spell/saving_throw_result.py`
  - 新增法术模板 outcome 结算主链路
  - 接入 `ResolveDamageParts`
  - 应用 outcome condition / note
  - 兼容旧 `hp_change_on_failed_save / hp_change_on_success`
- Possibly Create: `tools/services/combat/save_spell/spell_outcome_resolver.py`
  - 如果 `saving_throw_result.py` 体积明显膨胀，则把 outcome 解析、成长应用、`damage_parts` 生成拆出去
- Modify: `tools/services/encounter/get_encounter_state.py`
  - 如需把法术轻冗余列表按 `spell_id + name` 投影给 LLM，可在此补最小展示逻辑
- Modify: `test/test_execute_save_spell.py`
  - 将 happy-path 迁移到 `damage_rolls + outcome` 新主路径
  - 新增成功半伤、成功无伤、失败附状态、成长规则等测试
- Modify: `test/test_saving_throw_result.py`
  - 补 `SavingThrowResult` 的结构化结算细粒度测试

### Task 1: 先把豁免型法术的新契约写成红灯测试

**Files:**
- Modify: `test/test_execute_save_spell.py`
- Modify: `test/test_saving_throw_result.py`
- Test: `test/test_execute_save_spell.py`
- Test: `test/test_saving_throw_result.py`

- [ ] **Step 1: Rewrite ExecuteSaveSpell happy-path test to use `damage_rolls`**

In `test/test_execute_save_spell.py`, replace the old success-damage happy path with:

```python
    def test_execute_runs_full_success_flow_with_structured_damage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteSaveSpell(
                EncounterCastSpell(encounter_repo, append_event),
                SavingThrowRequest(encounter_repo),
                ResolveSavingThrow(encounter_repo),
                SavingThrowResult(
                    encounter_repo,
                    append_event,
                    update_hp=UpdateHp(encounter_repo, append_event),
                    update_conditions=UpdateConditions(encounter_repo, append_event),
                    update_encounter_notes=UpdateEncounterNotes(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_save_spell_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="burning_hands",
                base_roll=15,
                damage_rolls=[
                    {"source": "spell:burning_hands:failed:part_0", "rolls": [6, 5, 4]},
                ],
            )

            updated = encounter_repo.get("enc_execute_save_spell_test")
            self.assertIsNotNone(updated)
            self.assertTrue(result["resolution"]["success"])
            self.assertEqual(result["resolution"]["selected_outcome"], "successful_save")
            self.assertEqual(result["resolution"]["damage_resolution"]["total_damage"], 7)
            self.assertEqual(updated.entities["ent_enemy_iron_duster_001"].hp["current"], 11)
```

- [ ] **Step 2: Add a failing test for failed-save condition-only spell**

Add:

```python
    def test_execute_runs_failed_save_condition_only_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteSaveSpell(
                EncounterCastSpell(encounter_repo, append_event),
                SavingThrowRequest(encounter_repo),
                ResolveSavingThrow(encounter_repo),
                SavingThrowResult(
                    encounter_repo,
                    append_event,
                    update_conditions=UpdateConditions(encounter_repo, append_event),
                    update_encounter_notes=UpdateEncounterNotes(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_save_spell_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="blindness_deafness",
                base_roll=6,
            )

            updated = encounter_repo.get("enc_execute_save_spell_test")
            self.assertIsNotNone(updated)
            self.assertFalse(result["resolution"]["success"])
            self.assertEqual(result["resolution"]["selected_outcome"], "failed_save")
            self.assertNotIn("damage_resolution", result["resolution"])
            self.assertEqual(updated.entities["ent_enemy_iron_duster_001"].conditions, ["blinded"])
```

- [ ] **Step 3: Add a failing test for cantrip scaling**

Add:

```python
    def test_execute_applies_cantrip_scaling_before_damage_resolution(self) -> None:
        encounter = build_encounter()
        caster = encounter.entities["ent_ally_eric_001"]
        caster.level = 5
        caster.spells.append(
            {
                "spell_id": "sacred_flame",
                "name": "Sacred Flame",
                "level": 0,
                "save_ability": "dex",
                "requires_attack_roll": False,
            }
        )
```

```python
            result = service.execute(
                encounter_id="enc_execute_save_spell_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="sacred_flame",
                base_roll=4,
                damage_rolls=[
                    {"source": "spell:sacred_flame:failed:part_0", "rolls": [6, 7]},
                ],
            )

            self.assertEqual(
                result["resolution"]["damage_resolution"]["parts"][0]["resolved_formula"],
                "2d8",
            )
            self.assertEqual(result["resolution"]["damage_resolution"]["total_damage"], 13)
```

- [ ] **Step 4: Add a failing test for upcast scaling**

Add:

```python
    def test_execute_applies_slot_level_bonus_damage_parts(self) -> None:
        result = service.execute(
            encounter_id="enc_execute_save_spell_test",
            target_id="ent_enemy_iron_duster_001",
            spell_id="fireball",
            cast_level=4,
            base_roll=5,
            damage_rolls=[
                {"source": "spell:fireball:failed:part_0", "rolls": [6, 5, 4, 3, 2, 1, 6, 5]},
                {"source": "spell:fireball:slot_scaling", "rolls": [4]},
            ],
        )

        self.assertEqual(len(result["resolution"]["damage_resolution"]["parts"]), 2)
        self.assertEqual(result["resolution"]["damage_resolution"]["total_damage"], 36)
```

- [ ] **Step 5: Add a failing test proving successful no-damage outcomes ignore invalid `damage_rolls`**

Add:

```python
    def test_execute_ignores_invalid_damage_rolls_when_successful_outcome_has_no_damage(self) -> None:
        result = service.execute(
            encounter_id="enc_execute_save_spell_test",
            target_id="ent_enemy_iron_duster_001",
            spell_id="sacred_flame",
            base_roll=15,
            damage_rolls=[
                {"source": "spell:sacred_flame:failed:part_9", "rolls": [4]},
            ],
        )

        self.assertTrue(result["resolution"]["success"])
        self.assertEqual(result["resolution"]["selected_outcome"], "successful_save")
        self.assertNotIn("damage_resolution", result["resolution"])
        self.assertNotIn("hp_update", result["resolution"])
```

- [ ] **Step 6: Add SavingThrowResult-focused failing tests for outcome execution**

In `test/test_saving_throw_result.py`, add targeted tests like:

```python
    def test_execute_resolves_failed_outcome_damage_parts(self) -> None:
        result = service.execute(
            encounter_id="enc_save_spell_test",
            roll_request=roll_request,
            roll_result=roll_result,
            spell_definition={
                "failed_save_outcome": {
                    "damage_parts": [
                        {"source": "spell:test:failed:part_0", "formula": "3d6", "damage_type": "fire"}
                    ],
                    "conditions": [],
                    "note": None,
                },
                "successful_save_outcome": {
                    "damage_parts": [],
                    "conditions": [],
                    "note": None,
                },
                "scaling": {"cantrip_by_level": None, "slot_level_bonus": None},
            },
            damage_rolls=[{"source": "spell:test:failed:part_0", "rolls": [6, 5, 4]}],
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["damage_resolution"]["total_damage"], 15)
```

Also add:
- success half damage
- failed outcome with conditions
- success outcome no damage
- invalid source on damage outcome raises

- [ ] **Step 7: Run focused tests to verify red state**

Run: `python3 -m unittest test.test_execute_save_spell test.test_saving_throw_result`
Expected: FAIL because `ExecuteSaveSpell` / `SavingThrowResult` 还不支持 `damage_rolls` outcome 主路径、成长规则、或 `spell_definition` 驱动

- [ ] **Step 8: Commit the red tests**

```bash
git add test/test_execute_save_spell.py test/test_saving_throw_result.py
git commit -m "test: cover save spell damage parts outcomes"
```

### Task 2: 建立最小法术模板知识库与读取路径

**Files:**
- Modify: `test/test_execute_save_spell.py`
- Modify: `tools/services/spells/encounter_cast_spell.py`
- Modify: `tools/services/combat/save_spell/saving_throw_request.py`
- Test: `test/test_execute_save_spell.py`

- [ ] **Step 1: Extend test fixture spell data to include global spell definitions**

In `test/test_execute_save_spell.py`, update `build_encounter()` so the encounter contains top-level spell definitions in metadata or a repository-backed field your codebase already uses. Use this exact minimum fixture shape:

```python
    encounter.metadata = {
        "spell_definitions": {
            "blindness_deafness": {
                "id": "blindness_deafness",
                "name": "Blindness/Deafness",
                "level": 2,
                "requires_attack_roll": False,
                "save_ability": "con",
                "failed_save_outcome": {
                    "damage_parts": [],
                    "conditions": ["blinded"],
                    "note": "Iron Duster 现在被致盲了！",
                },
                "successful_save_outcome": {
                    "damage_parts": [],
                    "conditions": [],
                    "note": None,
                },
                "scaling": {"cantrip_by_level": None, "slot_level_bonus": None},
            },
            "burning_hands": {
                "id": "burning_hands",
                "name": "Burning Hands",
                "level": 1,
                "requires_attack_roll": False,
                "save_ability": "dex",
                "failed_save_outcome": {
                    "damage_parts": [
                        {"source": "spell:burning_hands:failed:part_0", "formula": "3d6", "damage_type": "fire"}
                    ],
                    "conditions": [],
                    "note": None,
                },
                "successful_save_outcome": {
                    "damage_parts_mode": "same_as_failed",
                    "damage_multiplier": 0.5,
                    "conditions": [],
                    "note": None,
                },
                "scaling": {"cantrip_by_level": None, "slot_level_bonus": None},
            },
        }
    }
```

- [ ] **Step 2: Run focused tests to verify red state remains meaningful**

Run: `python3 -m unittest test.test_execute_save_spell`
Expected: FAIL because runtime still does not read or use `spell_definitions`

- [ ] **Step 3: Implement minimal spell-definition lookup**

In `tools/services/spells/encounter_cast_spell.py`, add a helper like:

```python
    def _get_spell_definition(self, encounter, actor, spell_id: str) -> dict[str, Any]:
        spell_definitions = getattr(encounter, "metadata", {}).get("spell_definitions", {})
        spell_definition = spell_definitions.get(spell_id)
        if spell_definition is not None:
            return spell_definition

        for spell in actor.spells:
            if spell.get("spell_id") == spell_id:
                return spell
        raise ValueError(f"spell '{spell_id}' not found for actor '{actor.entity_id}'")
```

Use it where spell metadata is currently resolved, but do not yet implement outcome logic in this task.

- [ ] **Step 4: Ensure SavingThrowRequest carries enough spell context**

In `tools/services/combat/save_spell/saving_throw_request.py`, make sure request context includes:

```python
{
    "spell_id": spell_definition.get("id"),
    "spell_name": spell_definition.get("name"),
    "save_ability": spell_definition.get("save_ability"),
    "spell_definition": spell_definition,
}
```

This keeps `SavingThrowResult` pure on the next task.

- [ ] **Step 5: Run focused tests**

Run: `python3 -m unittest test.test_execute_save_spell`
Expected: Still FAIL, but failures should move from “spell definition missing” to “outcome execution not implemented”

- [ ] **Step 6: Commit**

```bash
git add tools/services/spells/encounter_cast_spell.py tools/services/combat/save_spell/saving_throw_request.py test/test_execute_save_spell.py
git commit -m "feat: load save spell definitions"
```

### Task 3: 让 SavingThrowResult 接入 outcome、condition 和结构化伤害

**Files:**
- Modify: `tools/services/combat/save_spell/saving_throw_result.py`
- Test: `test/test_saving_throw_result.py`
- Test: `test/test_execute_save_spell.py`

- [ ] **Step 1: Extend SavingThrowResult constructor for ResolveDamageParts**

Add:

```python
from tools.services.combat.damage import ResolveDamageParts


class SavingThrowResult:
    def __init__(
        self,
        encounter_repository: EncounterRepository,
        append_event: AppendEvent,
        update_hp: UpdateHp | None = None,
        update_conditions: UpdateConditions | None = None,
        update_encounter_notes: UpdateEncounterNotes | None = None,
        resolve_damage_parts: ResolveDamageParts | None = None,
    ):
        ...
        self.resolve_damage_parts = resolve_damage_parts or ResolveDamageParts()
```

- [ ] **Step 2: Extend execute signature with spell-definition-driven inputs**

Add:

```python
        spell_definition: dict[str, Any] | None = None,
        damage_rolls: list[dict[str, Any]] | None = None,
        cast_level: int | None = None,
```

Keep old integer inputs for temporary compatibility.

- [ ] **Step 3: Add outcome selection helper**

Implement:

```python
    def _select_outcome(self, *, success: bool, spell_definition: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        key = "successful_save_outcome" if success else "failed_save_outcome"
        outcome = spell_definition.get(key, {})
        if not isinstance(outcome, dict):
            raise ValueError(f"{key} must be a dict")
        return ("successful_save" if success else "failed_save"), outcome
```

Write result fields:

```python
        result["selected_outcome"] = selected_outcome
```

- [ ] **Step 4: Add scaling helpers**

Implement helpers:

```python
    def _apply_cantrip_scaling(self, damage_parts, scaling, caster_level): ...
    def _apply_slot_level_scaling(self, damage_parts, scaling, cast_level): ...
```

Use these exact semantics:
- `cantrip_by_level`: replace the base formula when caster level reaches threshold
- `slot_level_bonus`: append extra parts once per slot above `base_slot_level`

- [ ] **Step 5: Add structured damage resolution helper**

Implement:

```python
    def _maybe_resolve_outcome_damage(
        self,
        *,
        roll_request: RollRequest,
        roll_result: RollResult,
        outcome: dict[str, Any],
        spell_definition: dict[str, Any],
        damage_rolls: list[dict[str, Any]] | None,
        cast_level: int | None,
        target,
    ) -> dict[str, Any] | None:
```

Behavior:
- if selected outcome has no damage, return `None`
- if outcome uses `damage_parts_mode == "same_as_failed"`, start from failed outcome parts
- apply cantrip/slot scaling
- if selected outcome has no damage, ignore `damage_rolls` entirely
- if selected outcome has damage, strictly validate `damage_rolls`
- call `ResolveDamageParts`
- apply `damage_multiplier` after structured resolution:

```python
        if damage_multiplier == 0.5:
            for part in resolved["parts"]:
                part["adjusted_total"] //= 2
            resolved["total_damage"] = sum(part["adjusted_total"] for part in resolved["parts"])
```

Return the adjusted resolution dict.

- [ ] **Step 6: Wire HP / condition / note execution to selected outcome**

Replace old `_maybe_apply_hp(...)` branch for the new path with:

```python
        damage_resolution = self._maybe_resolve_outcome_damage(...)
        if damage_resolution is not None:
            result["damage_resolution"] = damage_resolution
            result["hp_update"] = self.update_hp.execute(
                encounter_id=encounter_id,
                target_id=target_id,
                hp_change=damage_resolution["total_damage"],
                reason=spell_definition.get("name") or str(roll_request.reason),
                damage_type=None,
                source_entity_id=caster_entity_id,
                concentration_vantage=concentration_vantage,
            )
        else:
            result["hp_update"] = None
```

And for conditions:

```python
        result["condition_updates"] = self._maybe_apply_conditions(
            encounter_id=encounter_id,
            target_id=target_id,
            caster_entity_id=caster_entity_id,
            success=success,
            conditions_on_failed_save=outcome.get("conditions", []) if not success else [],
            conditions_on_success=outcome.get("conditions", []) if success else [],
        )
```

For notes:

```python
        result["note_update"] = self._maybe_apply_note(
            encounter_id=encounter_id,
            target_id=target_id,
            caster_entity_id=caster_entity_id,
            success=success,
            note_on_failed_save=outcome.get("note") if not success else None,
            note_on_success=outcome.get("note") if success else None,
        )
```

- [ ] **Step 7: Run focused tests**

Run: `python3 -m unittest test.test_saving_throw_result test.test_execute_save_spell`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add tools/services/combat/save_spell/saving_throw_result.py test/test_saving_throw_result.py test/test_execute_save_spell.py
git commit -m "feat: resolve save spell outcomes with damage parts"
```

### Task 4: 让 ExecuteSaveSpell 走新主路径并保留过渡兼容

**Files:**
- Modify: `tools/services/combat/save_spell/execute_save_spell.py`
- Test: `test/test_execute_save_spell.py`

- [ ] **Step 1: Extend ExecuteSaveSpell signature**

Add:

```python
        damage_rolls: list[dict[str, Any]] | None = None,
```

Keep old integer damage inputs for compatibility during migration.

- [ ] **Step 2: Pass spell_definition, cast_level, and damage_rolls into SavingThrowResult**

Change:

```python
        spell_definition = request.context.get("spell_definition")
        resolution = self.saving_throw_result.execute(
            encounter_id=encounter_id,
            roll_request=request,
            roll_result=roll_result,
            spell_definition=spell_definition,
            damage_rolls=damage_rolls,
            cast_level=cast_level,
            hp_change_on_failed_save=hp_change_on_failed_save,
            hp_change_on_success=hp_change_on_success,
            damage_reason=damage_reason,
            damage_type=damage_type,
            concentration_vantage=concentration_vantage,
            conditions_on_failed_save=conditions_on_failed_save,
            conditions_on_success=conditions_on_success,
            note_on_failed_save=note_on_failed_save,
            note_on_success=note_on_success,
        )
```

- [ ] **Step 3: Run ExecuteSaveSpell-focused tests**

Run: `python3 -m unittest test.test_execute_save_spell`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tools/services/combat/save_spell/execute_save_spell.py test/test_execute_save_spell.py
git commit -m "feat: pass structured damage into save spell flow"
```

### Task 5: 全量回归并锁定迁移边界

**Files:**
- Test: `test/test_execute_save_spell.py`
- Test: `test/test_saving_throw_result.py`
- Test: `test/test_execute_attack.py`
- Test: `test/test_attack_roll_result.py`
- Test: `test/test_resolve_damage_parts.py`
- Test: `test/test_update_conditions.py`

- [ ] **Step 1: Run targeted combat regression**

Run:

```bash
python3 -m unittest \
  test.test_execute_save_spell \
  test.test_saving_throw_result \
  test.test_execute_attack \
  test.test_attack_roll_result \
  test.test_resolve_damage_parts
```

Expected: PASS

- [ ] **Step 2: Run full suite**

Run: `python3 -m unittest discover -s test -p 'test_*.py'`
Expected: PASS

- [ ] **Step 3: Inspect diff for migration boundary**

Run: `git diff -- tools/services/combat/save_spell/execute_save_spell.py tools/services/combat/save_spell/saving_throw_result.py test/test_execute_save_spell.py test/test_saving_throw_result.py`
Expected: diff shows save-spell chain now has `damage_rolls`/`damage_resolution` outcome logic, while old integer hp_change path remains only as compatibility input

- [ ] **Step 4: Commit final verified state**

```bash
git add \
  tools/services/combat/save_spell/execute_save_spell.py \
  tools/services/combat/save_spell/saving_throw_result.py \
  tools/services/spells/encounter_cast_spell.py \
  tools/services/combat/save_spell/saving_throw_request.py \
  test/test_execute_save_spell.py \
  test/test_saving_throw_result.py
git commit -m "feat: unify save spell damage resolution"
```
