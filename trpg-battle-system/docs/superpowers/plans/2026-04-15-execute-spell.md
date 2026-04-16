# ExecuteSpell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为战斗中的法术施放补齐统一入口 `ExecuteSpell`，覆盖合法性校验、升环处理、攻击/豁免/condition 三类最小结算，并把结果投影回 `encounter_state`。

**Architecture:** 继续复用现有 `SpellDefinitionRepository`、`EncounterCastSpell`、`ResolveSavingThrow`、`UpdateHp` 和 `GetEncounterState`。新入口拆成 `SpellRequest` 与 `ExecuteSpell` 两层：前者只做合法性校验和标准化，后者只消费标准化结果并分发到攻击型、豁免伤害型、豁免 + condition 型三条结算链。

**Tech Stack:** Python service layer, dataclass-style runtime models, TinyDB repositories, `unittest`

---

## File Structure

- Create: `tools/services/spells/spell_request.py`
  - 统一法术合法性校验和升环标准化输出。
- Create: `tools/services/spells/execute_spell.py`
  - 统一法术战斗入口，调度攻击型 / 豁免伤害型 / 豁免 + condition 型结算。
- Modify: `tools/services/spells/encounter_cast_spell.py`
  - 下沉为资源消耗 / spell instance 辅助，不再承担完整战斗入口。
- Modify: `tools/services/spells/__init__.py`
  - 导出 `SpellRequest` 与 `ExecuteSpell`。
- Modify: `tools/services/__init__.py`
  - 导出 `SpellRequest` 与 `ExecuteSpell` 供统一 service 包使用。
- Modify: `tools/repositories/spell_definition_repository.py`
  - 增加对新法术模板字段的读取兼容，不改变旧接口签名。
- Modify: `data/knowledge/spell_definitions.json`
  - 补齐 `eldritch_blast`、`fireball`、`hold_person`、`hex` 的最小模板字段。
- Test: `test/test_spell_request.py`
  - 新增 `SpellRequest` 单测。
- Test: `test/test_execute_spell.py`
  - 新增 `ExecuteSpell` 单测。
- Modify: `test/test_spell_definition_repository.py`
  - 覆盖新模板字段解析。
- Modify: `test/test_encounter_cast_spell.py`
  - 调整旧行为预期，确保辅助层仍可复用。

## Task 1: 建立 SpellRequest 合法性校验骨架

**Files:**
- Create: `tools/services/spells/spell_request.py`
- Create: `test/test_spell_request.py`

- [ ] **Step 1: Write the failing test**

```python
def test_execute_rejects_unknown_spell_on_actor(self) -> None:
    encounter = build_spell_encounter()
    repo.save(encounter)

    service = SpellRequest(repo, SpellDefinitionRepository(knowledge_path))

    result = service.execute(
        encounter_id="enc_spell_test",
        actor_id="ent_ally_wizard_001",
        spell_id="fireball",
        cast_level=3,
        target_entity_ids=[],
        target_point={"x": 4, "y": 4},
    )

    self.assertEqual(
        result,
        {
            "ok": False,
            "error_code": "spell_not_known",
            "message": "施法者未掌握 fireball",
        },
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_spell_request.SpellRequestTests.test_execute_rejects_unknown_spell_on_actor`

Expected: FAIL with `ModuleNotFoundError: No module named 'tools.services.spells.spell_request'`

- [ ] **Step 3: Write minimal implementation**

```python
class SpellRequest:
    def __init__(self, encounter_repository, spell_definition_repository=None):
        self.encounter_repository = encounter_repository
        self.spell_definition_repository = spell_definition_repository or SpellDefinitionRepository()

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        spell_id: str,
        cast_level: int,
        target_entity_ids: list[str] | None = None,
        target_point: dict[str, int] | None = None,
        declared_action_cost: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        actor = encounter.entities.get(actor_id)
        if actor is None:
            raise ValueError(f"actor '{actor_id}' not found in encounter")
        spell_definition = self._find_actor_spell_definition(actor, spell_id)
        if spell_definition is None:
            return {
                "ok": False,
                "error_code": "spell_not_known",
                "message": f"施法者未掌握 {spell_id}",
            }
        return {"ok": True, "spell_definition": spell_definition}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest test.test_spell_request.SpellRequestTests.test_execute_rejects_unknown_spell_on_actor`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_spell_request.py tools/services/spells/spell_request.py
git commit -m "feat: add spell request validation scaffold"
```

## Task 2: 补齐 SpellRequest 的升环与动作/目标校验

**Files:**
- Modify: `tools/services/spells/spell_request.py`
- Modify: `test/test_spell_request.py`
- Modify: `test/test_spell_definition_repository.py`
- Modify: `data/knowledge/spell_definitions.json`

- [ ] **Step 1: Write the failing tests**

```python
def test_execute_resolves_slot_upcast_damage_scaling(self) -> None:
    encounter = build_spell_encounter_with_fireball()
    repo.save(encounter)

    result = service.execute(
        encounter_id="enc_spell_test",
        actor_id="ent_ally_wizard_001",
        spell_id="fireball",
        cast_level=5,
        target_entity_ids=[],
        target_point={"x": 6, "y": 6},
        declared_action_cost="action",
    )

    self.assertTrue(result["ok"])
    self.assertEqual(result["base_level"], 3)
    self.assertEqual(result["upcast_delta"], 2)
    self.assertEqual(
        result["resolved_scaling"]["extra_damage_parts"],
        [{"formula": "2d6", "damage_type": "fire"}],
    )


def test_execute_rejects_wrong_action_cost(self) -> None:
    encounter = build_spell_encounter_with_fireball()
    repo.save(encounter)

    result = service.execute(
        encounter_id="enc_spell_test",
        actor_id="ent_ally_wizard_001",
        spell_id="fireball",
        cast_level=3,
        target_entity_ids=[],
        target_point={"x": 6, "y": 6},
        declared_action_cost="bonus_action",
    )

    self.assertEqual(result["error_code"], "invalid_action_cost")


def test_execute_rejects_hold_person_non_humanoid_target(self) -> None:
    encounter = build_spell_encounter_with_hold_person()
    repo.save(encounter)

    result = service.execute(
        encounter_id="enc_spell_test",
        actor_id="ent_ally_wizard_001",
        spell_id="hold_person",
        cast_level=2,
        target_entity_ids=["ent_enemy_wolf_001"],
        target_point=None,
        declared_action_cost="action",
    )

    self.assertEqual(result["error_code"], "invalid_target_type")


def test_execute_rejects_nonzero_cast_level_for_cantrip(self) -> None:
    encounter = build_spell_encounter_with_eldritch_blast()
    repo.save(encounter)

    result = service.execute(
        encounter_id="enc_spell_test",
        actor_id="ent_ally_wizard_001",
        spell_id="eldritch_blast",
        cast_level=1,
        target_entity_ids=["ent_enemy_bandit_001"],
        target_point=None,
        declared_action_cost="action",
    )

    self.assertEqual(result["error_code"], "invalid_cantrip_cast_level")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_spell_request test.test_spell_definition_repository`

Expected: FAIL because `SpellRequest` does not yet implement scaling / action / target validation and `spell_definitions.json` lacks the new fields.

- [ ] **Step 3: Write minimal implementation**

```python
def _resolve_scaling(self, spell_definition: dict[str, Any], cast_level: int, actor_level: int | None) -> dict[str, Any]:
    base_level = int(spell_definition.get("base_level", spell_definition.get("level", 0)))
    if base_level == 0:
        if cast_level != 0:
            return {"ok": False, "error_code": "invalid_cantrip_cast_level", "message": "戏法不能消耗法术位"}
        beam_count = 1
        if isinstance(actor_level, int) and actor_level >= 17:
            beam_count = 4
        elif isinstance(actor_level, int) and actor_level >= 11:
            beam_count = 3
        elif isinstance(actor_level, int) and actor_level >= 5:
            beam_count = 2
        return {"ok": True, "base_level": 0, "upcast_delta": 0, "resolved_scaling": {"beam_count": beam_count}}

    if cast_level < base_level:
        return {"ok": False, "error_code": "invalid_cast_level", "message": "施法环阶不能低于法术基础环阶"}

    scaling = spell_definition.get("scaling", {})
    upcast_delta = cast_level - base_level
    resolved_scaling = {}
    if scaling.get("mode") == "slot":
        per_slot = scaling.get("per_slot_above_base", {})
        if "extra_damage_parts" in per_slot:
            part = per_slot["extra_damage_parts"][0]
            resolved_scaling["extra_damage_parts"] = [
                {"formula": f"{upcast_delta}d6", "damage_type": part["damage_type"]}
            ] if upcast_delta > 0 else []
        if "extra_targets" in per_slot:
            resolved_scaling["extra_targets"] = per_slot["extra_targets"] * upcast_delta
    return {
        "ok": True,
        "base_level": base_level,
        "upcast_delta": upcast_delta,
        "resolved_scaling": resolved_scaling,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest test.test_spell_request test.test_spell_definition_repository`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add data/knowledge/spell_definitions.json test/test_spell_request.py test/test_spell_definition_repository.py tools/services/spells/spell_request.py
git commit -m "feat: validate spell requests with upcast scaling"
```

## Task 3: 建立 ExecuteSpell 骨架并接上资源消耗

**Files:**
- Create: `tools/services/spells/execute_spell.py`
- Modify: `tools/services/spells/__init__.py`
- Modify: `tools/services/__init__.py`
- Modify: `tools/services/spells/encounter_cast_spell.py`
- Create: `test/test_execute_spell.py`

- [ ] **Step 1: Write the failing test**

```python
def test_execute_declares_spell_and_returns_encounter_state(self) -> None:
    encounter = build_spell_encounter_with_fireball()
    repo.save(encounter)

    result = ExecuteSpell(
        encounter_repository=repo,
        append_event=AppendEvent(event_repo),
        spell_request=SpellRequest(repo, spell_repo),
    ).execute(
        encounter_id="enc_spell_test",
        actor_id="ent_ally_wizard_001",
        spell_id="fireball",
        cast_level=3,
        target_entity_ids=[],
        target_point={"x": 6, "y": 6},
    )

    self.assertEqual(result["spell_id"], "fireball")
    self.assertEqual(result["resource_update"]["slot_level"], 3)
    self.assertIn("encounter_state", result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_execute_spell.ExecuteSpellTests.test_execute_declares_spell_and_returns_encounter_state`

Expected: FAIL with `ModuleNotFoundError: No module named 'tools.services.spells.execute_spell'`

- [ ] **Step 3: Write minimal implementation**

```python
class ExecuteSpell:
    def __init__(self, encounter_repository, append_event, spell_request, encounter_cast_spell=None):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.spell_request = spell_request
        self.encounter_cast_spell = encounter_cast_spell or EncounterCastSpell(encounter_repository, append_event)

    def execute(self, **kwargs) -> dict[str, Any]:
        request = self.spell_request.execute(**kwargs)
        if not request.get("ok"):
            return request

        declared = self.encounter_cast_spell.execute(
            encounter_id=kwargs["encounter_id"],
            spell_id=kwargs["spell_id"],
            target_ids=kwargs.get("target_entity_ids"),
            cast_level=kwargs["cast_level"],
            include_encounter_state=True,
        )
        return {
            "encounter_id": kwargs["encounter_id"],
            "actor_id": kwargs["actor_id"],
            "spell_id": kwargs["spell_id"],
            "cast_level": kwargs["cast_level"],
            "resource_update": declared.get("slot_consumed"),
            "spell_resolution": {"mode": "declared_only"},
            "encounter_state": declared["encounter_state"],
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest test.test_execute_spell.ExecuteSpellTests.test_execute_declares_spell_and_returns_encounter_state`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_execute_spell.py tools/services/__init__.py tools/services/spells/__init__.py tools/services/spells/encounter_cast_spell.py tools/services/spells/execute_spell.py
git commit -m "feat: add execute spell service scaffold"
```

## Task 4: 接通 Fireball 的区域 + 豁免 + 升环伤害

**Files:**
- Modify: `tools/services/spells/execute_spell.py`
- Modify: `test/test_execute_spell.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_execute_fireball_deals_failed_save_full_damage_and_success_half_damage(self) -> None:
    encounter = build_spell_encounter_with_fireball_targets()
    repo.save(encounter)

    result = service.execute(
        encounter_id="enc_spell_test",
        actor_id="ent_ally_wizard_001",
        spell_id="fireball",
        cast_level=4,
        target_entity_ids=[],
        target_point={"x": 6, "y": 6},
        save_rolls={
            "ent_enemy_bandit_001": {"base_roll": 4},
            "ent_enemy_guard_001": {"base_roll": 16},
        },
        damage_rolls=[6, 6, 6, 6, 6, 6, 6, 6, 6],
    )

    updated = repo.get("enc_spell_test")
    self.assertEqual(updated.entities["ent_enemy_bandit_001"].hp["current"], 0)
    self.assertEqual(updated.entities["ent_enemy_guard_001"].hp["current"], 5)
    self.assertEqual(result["spell_resolution"]["resolution_mode"], "save_damage")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_execute_spell.ExecuteSpellTests.test_execute_fireball_deals_failed_save_full_damage_and_success_half_damage`

Expected: FAIL because `ExecuteSpell` does not yet compute area targets, saving throws, or damage resolution.

- [ ] **Step 3: Write minimal implementation**

```python
def _resolve_save_damage_spell(self, *, encounter, request, save_rolls, damage_rolls):
    targets = self._entities_in_area(encounter, request["target_point"], request["spell_definition"]["targeting"])
    total_formula = self._merge_damage_parts(
        request["spell_definition"]["damage_parts"],
        request["resolved_scaling"].get("extra_damage_parts", []),
    )
    damage_total = self._sum_damage_rolls(damage_rolls)
    updates = []
    for target in targets:
        save_result = self._resolve_spell_save(encounter.encounter_id, target.entity_id, request, save_rolls[target.entity_id])
        hp_change = damage_total if not save_result["success"] else damage_total // 2
        hp_update = self.update_hp.execute(
            encounter_id=encounter.encounter_id,
            target_id=target.entity_id,
            hp_change=hp_change,
            reason=f"{request['spell_definition']['name']} damage",
            damage_type="fire",
        )
        updates.append({"target_id": target.entity_id, "save_result": save_result, "hp_update": hp_update})
    return {"resolution_mode": "save_damage", "targets": updates}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest test.test_execute_spell.ExecuteSpellTests.test_execute_fireball_deals_failed_save_full_damage_and_success_half_damage`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_execute_spell.py tools/services/spells/execute_spell.py
git commit -m "feat: resolve fireball save damage spells"
```

## Task 5: 接通 Hold Person 的目标类型 + 豁免 + condition + 升环目标数

**Files:**
- Modify: `tools/services/spells/execute_spell.py`
- Modify: `test/test_execute_spell.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_execute_hold_person_applies_paralyzed_and_spell_instance(self) -> None:
    encounter = build_spell_encounter_with_hold_person()
    repo.save(encounter)

    result = service.execute(
        encounter_id="enc_spell_test",
        actor_id="ent_ally_wizard_001",
        spell_id="hold_person",
        cast_level=3,
        target_entity_ids=["ent_enemy_bandit_001", "ent_enemy_cultist_001"],
        target_point=None,
        save_rolls={
            "ent_enemy_bandit_001": {"base_roll": 3},
            "ent_enemy_cultist_001": {"base_roll": 4},
        },
    )

    updated = repo.get("enc_spell_test")
    self.assertIn("paralyzed", updated.entities["ent_enemy_bandit_001"].conditions)
    self.assertIn("paralyzed", updated.entities["ent_enemy_cultist_001"].conditions)
    self.assertEqual(len(updated.spell_instances), 1)
    self.assertEqual(result["spell_resolution"]["resolution_mode"], "save_condition")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_execute_spell.ExecuteSpellTests.test_execute_hold_person_applies_paralyzed_and_spell_instance`

Expected: FAIL because `ExecuteSpell` does not yet apply save-based conditions or build concentration-backed spell instances.

- [ ] **Step 3: Write minimal implementation**

```python
def _resolve_save_condition_spell(self, *, encounter, request, save_rolls):
    applied_targets = []
    for target_id in request["target_entity_ids"]:
        save_result = self._resolve_spell_save(encounter.encounter_id, target_id, request, save_rolls[target_id])
        if save_result["success"]:
            applied_targets.append({"target_id": target_id, "save_result": save_result, "conditions_applied": []})
            continue
        target = encounter.entities[target_id]
        for condition in request["spell_definition"]["on_failed_save"]["apply_conditions"]:
            if condition not in target.conditions:
                target.conditions.append(condition)
        applied_targets.append({"target_id": target_id, "save_result": save_result, "conditions_applied": ["paralyzed"]})
    spell_instance = build_spell_instance(
        encounter=encounter,
        caster=encounter.entities[request["actor_id"]],
        spell_definition=request["spell_definition"],
        cast_level=request["cast_level"],
        target_ids=request["target_entity_ids"],
        turn_effect_updates=[],
    )
    return {"resolution_mode": "save_condition", "targets": applied_targets, "spell_instance": spell_instance}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest test.test_execute_spell.ExecuteSpellTests.test_execute_hold_person_applies_paralyzed_and_spell_instance`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_execute_spell.py tools/services/spells/execute_spell.py
git commit -m "feat: resolve hold person save condition spells"
```

## Task 6: 接通 Eldritch Blast 的攻击型法术与戏法成长

**Files:**
- Modify: `tools/services/spells/execute_spell.py`
- Modify: `test/test_execute_spell.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_execute_eldritch_blast_uses_cantrip_scaling_for_beam_count(self) -> None:
    encounter = build_spell_encounter_with_eldritch_blast(actor_level=5)
    repo.save(encounter)

    result = service.execute(
        encounter_id="enc_spell_test",
        actor_id="ent_ally_wizard_001",
        spell_id="eldritch_blast",
        cast_level=0,
        target_entity_ids=["ent_enemy_bandit_001", "ent_enemy_guard_001"],
        target_point=None,
        attack_rolls={
            "ent_enemy_bandit_001": {"final_total": 17, "dice_rolls": {"base_rolls": [12], "modifier": 5}},
            "ent_enemy_guard_001": {"final_total": 15, "dice_rolls": {"base_rolls": [10], "modifier": 5}},
        },
        damage_rolls={
            "ent_enemy_bandit_001": [8],
            "ent_enemy_guard_001": [6],
        },
    )

    updated = repo.get("enc_spell_test")
    self.assertEqual(updated.entities["ent_enemy_bandit_001"].hp["current"], 2)
    self.assertEqual(updated.entities["ent_enemy_guard_001"].hp["current"], 4)
    self.assertEqual(result["spell_resolution"]["beam_count"], 2)
    self.assertEqual(result["spell_resolution"]["resolution_mode"], "attack")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_execute_spell.ExecuteSpellTests.test_execute_eldritch_blast_uses_cantrip_scaling_for_beam_count`

Expected: FAIL because `ExecuteSpell` does not yet dispatch attack-type spells through the attack resolution path.

- [ ] **Step 3: Write minimal implementation**

```python
def _resolve_attack_spell(self, *, encounter, request, attack_rolls, damage_rolls):
    beam_count = request["resolved_scaling"].get("beam_count", 1)
    targets = request["target_entity_ids"]
    if len(targets) != beam_count:
        raise ValueError("attack spell targets must match beam count")
    updates = []
    for target_id in targets:
        roll_payload = attack_rolls[target_id]
        target = encounter.entities[target_id]
        hit = roll_payload["final_total"] >= target.ac
        hp_update = None
        if hit:
            hp_update = self.update_hp.execute(
                encounter_id=encounter.encounter_id,
                target_id=target_id,
                hp_change=damage_rolls[target_id][0],
                reason=f"{request['spell_definition']['name']} damage",
                damage_type="force",
            )
        updates.append({"target_id": target_id, "hit": hit, "hp_update": hp_update})
    return {"resolution_mode": "attack", "beam_count": beam_count, "targets": updates}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest test.test_execute_spell.ExecuteSpellTests.test_execute_eldritch_blast_uses_cantrip_scaling_for_beam_count`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_execute_spell.py tools/services/spells/execute_spell.py
git commit -m "feat: resolve attack type spells via execute spell"
```

## Task 7: 全链路回归

**Files:**
- No code changes required

- [ ] **Step 1: Run focused regression**

Run: `python3 -m unittest test.test_spell_request test.test_execute_spell test.test_spell_definition_repository test.test_encounter_cast_spell test.test_resolve_saving_throw`

Expected: PASS

- [ ] **Step 2: Run broader combat regression**

Run: `python3 -m unittest test.test_update_hp test.test_execute_attack test.test_execute_save_spell test.test_start_turn test.test_get_encounter_state`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-04-15-execute-spell-design.md docs/superpowers/plans/2026-04-15-execute-spell.md
git commit -m "docs: add execute spell implementation plan"
```
