# Death Saves And Knockout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `pc / npc` 补齐 `HP=0` 濒死、自动死亡豁免、真正死亡、以及“击晕不杀”近战分支，并把这些状态正确投影到 battlemap。

**Architecture:** 继续以 `UpdateHp` 作为所有 `HP` 变动的唯一入口，负责 `0 HP` 分流、再次受伤和专注终止；以 `StartTurn` 作为死亡豁免的自动触发入口；以 `ExecuteAttack` 只负责把 LLM 理解出的 `zero_hp_intent="knockout"` 传给底层结算。显示层不新增前端状态，只读取实体 `conditions / combat_flags / hp` 渲染。

**Tech Stack:** Python dataclasses, service-layer rules, unittest, HTML string rendering in `RenderBattlemapView`

---

## File Structure

- Modify: `tools/services/combat/shared/update_hp.py`
  - 处理 `pc / npc` 掉到 `0 HP` 的濒死初始化、`0 HP` 再次受伤、`is_dead=True`、以及“击晕不杀保护态”。
- Modify: `tools/services/combat/attack/execute_attack.py`
  - 接收 `zero_hp_intent="knockout"` 并只在近战攻击里透传到 HP 结算。
- Create: `tools/services/combat/rules/death_saves/__init__.py`
  - 聚合死亡豁免相关服务。
- Create: `tools/services/combat/rules/death_saves/resolve_death_save.py`
  - 解析一次死亡豁免的骰值，并更新成功/失败计数。
- Modify: `tools/services/encounter/turns/start_turn.py`
  - 在现有回合开始逻辑后追加“若当前单位需要死亡豁免则自动结算”。
- Modify: `tools/services/map/render_battlemap_view.py`
  - 区分 `0 HP 未死` 与 `is_dead=True` 的玩家/NPC 外框和角色卡文案。
- Modify: `tools/services/encounter/get_encounter_state.py`
  - 把死亡豁免计数和死亡状态投影给 LLM。
- Modify: `tools/models/encounter_entity.py`
  - 不改 schema 结构，只依赖现有 `combat_flags` 字典，测试里需要补 roundtrip 覆盖。
- Test: `test/test_update_hp.py`
- Test: `test/test_start_turn.py`
- Test: `test/test_execute_attack.py`
- Test: `test/test_render_battlemap_view.py`
- Test: `test/test_get_encounter_state.py`

### Task 1: 锁定 `UpdateHp` 的濒死与死亡分流

**Files:**
- Modify: `test/test_update_hp.py`
- Modify: `tools/services/combat/shared/update_hp.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_execute_sets_unconscious_and_death_saves_when_pc_drops_to_zero(self) -> None:
    player = build_player_target()
    encounter = build_single_entity_encounter(player)
    encounter_repo.save(encounter)

    result = service.execute(
        encounter_id="enc_hp_test",
        target_id=player.entity_id,
        hp_change=99,
        reason="player dropped",
        include_encounter_state=True,
    )

    updated = encounter_repo.get("enc_hp_test")
    assert updated is not None
    self.assertEqual(updated.entities[player.entity_id].hp["current"], 0)
    self.assertIn("unconscious", updated.entities[player.entity_id].conditions)
    self.assertEqual(updated.entities[player.entity_id].combat_flags["death_saves"], {"successes": 0, "failures": 0})
    self.assertFalse(updated.entities[player.entity_id].combat_flags.get("is_dead", False))
    self.assertEqual(result["zero_hp_outcome"]["outcome"], "entity_dying")


def test_execute_adds_one_failed_death_save_when_zero_hp_pc_takes_damage(self) -> None:
    player = build_player_target()
    player.hp["current"] = 0
    player.conditions = ["unconscious"]
    player.combat_flags = {"death_saves": {"successes": 0, "failures": 0}, "is_dead": False}
    encounter_repo.save(build_single_entity_encounter(player))

    result = service.execute(
        encounter_id="enc_hp_test",
        target_id=player.entity_id,
        hp_change=4,
        reason="ongoing damage",
    )

    updated = encounter_repo.get("enc_hp_test")
    assert updated is not None
    self.assertEqual(updated.entities[player.entity_id].combat_flags["death_saves"]["failures"], 1)
    self.assertFalse(updated.entities[player.entity_id].combat_flags["is_dead"])
    self.assertEqual(result["zero_hp_followup"]["outcome"], "death_save_failure")


def test_execute_double_counts_failed_death_save_when_zero_hp_pc_takes_critical_damage(self) -> None:
    ...
    result = service.execute(
        encounter_id="enc_hp_test",
        target_id=player.entity_id,
        hp_change=4,
        reason="critical hit",
        from_critical_hit=True,
    )
    self.assertEqual(updated.entities[player.entity_id].combat_flags["death_saves"]["failures"], 2)


def test_execute_marks_pc_dead_when_zero_hp_damage_reaches_three_failures(self) -> None:
    ...
    player.combat_flags = {"death_saves": {"successes": 1, "failures": 2}, "is_dead": False}
    result = service.execute(...)
    self.assertTrue(updated.entities[player.entity_id].combat_flags["is_dead"])
    self.assertEqual(result["zero_hp_followup"]["outcome"], "dead")


def test_execute_marks_pc_dead_when_zero_hp_damage_exceeds_max_hp(self) -> None:
    ...
    result = service.execute(encounter_id="enc_hp_test", target_id=player.entity_id, hp_change=10, reason="massive damage")
    self.assertTrue(updated.entities[player.entity_id].combat_flags["is_dead"])
    self.assertEqual(result["zero_hp_followup"]["outcome"], "dead")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_update_hp`

Expected: FAIL because `UpdateHp` currently only adds `unconscious` for `pc/npc` and has no `death_saves / zero_hp_followup / is_dead` flow.

- [ ] **Step 3: Write minimal implementation**

```python
def _resolve_zero_hp_outcome(...):
    if target.category in {"pc", "npc"}:
        if "unconscious" not in target.conditions:
            target.conditions.append("unconscious")
        flags = target.combat_flags if isinstance(target.combat_flags, dict) else {}
        flags["is_dead"] = False
        flags["death_saves"] = {"successes": 0, "failures": 0}
        target.combat_flags = flags
        self._end_concentration_if_needed(encounter, target)
        return {"outcome": "entity_dying", "position": dict(target.position)}


def _handle_zero_hp_followup_damage(...):
    if target.category not in {"pc", "npc"}:
        return None
    if target.hp["current"] != 0 or bool(target.combat_flags.get("is_dead")):
        return None
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest test.test_update_hp`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_update_hp.py tools/services/combat/shared/update_hp.py
git commit -m "feat: add dying and dead states for zero hp pcs"
```

### Task 2: 接入“击晕不杀”近战分支

**Files:**
- Modify: `test/test_execute_attack.py`
- Modify: `test/test_update_hp.py`
- Modify: `tools/services/combat/attack/execute_attack.py`
- Modify: `tools/services/combat/shared/update_hp.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_execute_melee_knockout_sets_zero_hp_unconscious_and_knockout_protection(self) -> None:
    result = service.execute(
        encounter_id="enc_execute_attack_test",
        target_id="ent_enemy_goblin_001",
        weapon_id="rapier",
        final_total=17,
        dice_rolls={"base_rolls": [12], "modifier": 5},
        damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [20]}],
        zero_hp_intent="knockout",
    )

    updated = encounter_repo.get("enc_execute_attack_test")
    assert updated is not None
    target = updated.entities["ent_enemy_goblin_001"]
    self.assertEqual(target.hp["current"], 0)
    self.assertIn("unconscious", target.conditions)
    self.assertEqual(target.turn_effects[0]["effect_type"], "knockout_protection")


def test_execute_knockout_intent_is_ignored_for_ranged_attack(self) -> None:
    ...
    self.assertEqual(result["resolution"]["hp_update"]["zero_hp_outcome"]["outcome"], "monster_removed_with_remains")


def test_execute_zero_hp_knockout_protection_breaks_on_next_damage(self) -> None:
    player = build_player_target()
    player.hp["current"] = 0
    player.conditions = ["unconscious"]
    player.turn_effects = [{"effect_id": "effect_knockout_001", "effect_type": "knockout_protection", "duration_seconds": 3600}]
    player.combat_flags = {"death_saves": {"successes": 0, "failures": 0}, "is_dead": False}
    encounter_repo.save(build_single_entity_encounter(player))

    service.execute(encounter_id="enc_hp_test", target_id=player.entity_id, hp_change=2, reason="damage while knocked out")

    updated = encounter_repo.get("enc_hp_test")
    assert updated is not None
    self.assertEqual(updated.entities[player.entity_id].combat_flags["death_saves"]["failures"], 1)
    self.assertEqual(updated.entities[player.entity_id].turn_effects, [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_execute_attack test.test_update_hp`

Expected: FAIL because `ExecuteAttack` has no `zero_hp_intent` parameter and `UpdateHp` has no `knockout_protection`.

- [ ] **Step 3: Write minimal implementation**

```python
# tools/services/combat/attack/execute_attack.py
def execute(..., zero_hp_intent: str | None = None, ...):
    ...
    attack_context["zero_hp_intent"] = zero_hp_intent


# tools/services/combat/shared/update_hp.py
def execute(..., zero_hp_intent: str | None = None, ...):
    ...

if target.category in {"pc", "npc"} and zero_hp_intent == "knockout" and self._is_melee_zero_hp_hit(...):
    target.turn_effects.append(
        {
            "effect_id": f"effect_knockout_{uuid4().hex[:12]}",
            "effect_type": "knockout_protection",
            "name": "Knocked Out",
            "duration_seconds": 3600,
        }
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest test.test_execute_attack test.test_update_hp`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_execute_attack.py test/test_update_hp.py tools/services/combat/attack/execute_attack.py tools/services/combat/shared/update_hp.py
git commit -m "feat: support nonlethal knockout on melee zero hp hits"
```

### Task 3: 让 `StartTurn` 自动结算死亡豁免

**Files:**
- Create: `tools/services/combat/rules/death_saves/__init__.py`
- Create: `tools/services/combat/rules/death_saves/resolve_death_save.py`
- Modify: `tools/services/encounter/turns/start_turn.py`
- Modify: `test/test_start_turn.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_execute_rolls_death_save_at_start_of_turn_for_zero_hp_pc(self) -> None:
    encounter = build_encounter()
    current = encounter.entities["ent_ally_eric_001"]
    current.hp["current"] = 0
    current.conditions = ["unconscious"]
    current.combat_flags["death_saves"] = {"successes": 0, "failures": 0}
    repo.save(encounter)

    with patch("tools.services.combat.rules.death_saves.resolve_death_save.random.randint", return_value=12):
        updated = StartTurn(repo).execute("enc_start_turn_test")

    self.assertEqual(updated.entities["ent_ally_eric_001"].combat_flags["death_saves"]["successes"], 1)


def test_execute_recovers_one_hp_after_third_success(self) -> None:
    ...
    current.combat_flags["death_saves"] = {"successes": 2, "failures": 0}
    with patch(..., return_value=12):
        updated = StartTurn(repo).execute("enc_start_turn_test")
    self.assertEqual(updated.entities["ent_ally_eric_001"].hp["current"], 1)
    self.assertNotIn("unconscious", updated.entities["ent_ally_eric_001"].conditions)


def test_execute_marks_dead_after_third_failure(self) -> None:
    ...
    current.combat_flags["death_saves"] = {"successes": 0, "failures": 2}
    with patch(..., return_value=2):
        updated = StartTurn(repo).execute("enc_start_turn_test")
    self.assertTrue(updated.entities["ent_ally_eric_001"].combat_flags["is_dead"])


def test_execute_skips_death_save_for_knockout_protection(self) -> None:
    ...
    current.turn_effects = [{"effect_id": "effect_knockout_001", "effect_type": "knockout_protection", "duration_seconds": 3600}]
    with patch(..., return_value=12):
        updated = StartTurn(repo).execute("enc_start_turn_test")
    self.assertEqual(updated.entities["ent_ally_eric_001"].combat_flags["death_saves"]["successes"], 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_start_turn`

Expected: FAIL because `StartTurn` currently only resets resources and resolves `start_of_turn` turn effects.

- [ ] **Step 3: Write minimal implementation**

```python
# tools/services/combat/rules/death_saves/resolve_death_save.py
class ResolveDeathSave:
    def execute(self, *, entity: EncounterEntity) -> dict[str, object]:
        roll = random.randint(1, 20)
        ...


# tools/services/encounter/turns/start_turn.py
death_save_resolution = self._maybe_resolve_death_save(updated)
if death_save_resolution is not None:
    resolutions.append(death_save_resolution)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest test.test_start_turn`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_start_turn.py tools/services/combat/rules/death_saves/__init__.py tools/services/combat/rules/death_saves/resolve_death_save.py tools/services/encounter/turns/start_turn.py
git commit -m "feat: resolve death saves at start of turn"
```

### Task 4: 让专注在 `unconscious / dead` 时直接终止

**Files:**
- Modify: `test/test_update_hp.py`
- Modify: `tools/services/combat/shared/update_hp.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_execute_breaks_concentration_when_pc_drops_to_zero_hp(self) -> None:
    player = build_player_target()
    player.combat_flags = {"is_concentrating": True, "death_saves": {"successes": 0, "failures": 0}, "is_dead": False}
    encounter = build_concentrating_player_encounter(player)
    encounter_repo.save(encounter)

    service.execute(encounter_id="enc_hp_test", target_id=player.entity_id, hp_change=99, reason="drop to zero")

    updated = encounter_repo.get("enc_hp_test")
    assert updated is not None
    self.assertFalse(updated.entities[player.entity_id].combat_flags["is_concentrating"])


def test_execute_breaks_concentration_when_zero_hp_followup_damage_kills_pc(self) -> None:
    ...
    self.assertFalse(updated.entities[player.entity_id].combat_flags["is_concentrating"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_update_hp`

Expected: FAIL because current direct `unconscious / dead` path does not forcibly reuse concentration cleanup in all zero-HP branches.

- [ ] **Step 3: Write minimal implementation**

```python
def _end_concentration_if_needed(self, encounter: Encounter, target: EncounterEntity) -> dict[str, Any] | None:
    if not bool(target.combat_flags.get("is_concentrating")):
        return None
    target.combat_flags["is_concentrating"] = False
    return end_concentration_spell_instances(encounter=encounter, caster_entity_id=target.entity_id, reason="incapacitated_or_dead")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest test.test_update_hp`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_update_hp.py tools/services/combat/shared/update_hp.py
git commit -m "feat: break concentration on unconscious or dead states"
```

### Task 5: 投影给 LLM 与前端

**Files:**
- Modify: `tools/services/encounter/get_encounter_state.py`
- Modify: `tools/services/map/render_battlemap_view.py`
- Modify: `test/test_get_encounter_state.py`
- Modify: `test/test_render_battlemap_view.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_get_encounter_state_exposes_death_save_summary_for_current_turn_entity(self) -> None:
    current.combat_flags["death_saves"] = {"successes": 2, "failures": 1}
    state = GetEncounterState(repo).execute("enc_view_test")
    self.assertEqual(state["current_turn_entity"]["resources"]["death_saves"], "2 成功 / 1 失败")


def test_render_battlemap_view_marks_dead_player_with_deeper_red_outline(self) -> None:
    player.combat_flags["is_dead"] = True
    payload = RenderBattlemapView().execute(encounter)
    self.assertIn("token--dead", payload["html"])
    self.assertIn("character-card__status\">死亡<", payload["html"])


def test_render_battlemap_view_marks_zero_hp_player_without_dead_flag_as_downed(self) -> None:
    player.hp["current"] = 0
    player.conditions = ["unconscious"]
    payload = RenderBattlemapView().execute(encounter)
    self.assertIn("token--downed", payload["html"])
    self.assertNotIn("token--dead", payload["html"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_get_encounter_state test.test_render_battlemap_view`

Expected: FAIL because the current state projection and renderer know nothing about `death_saves / is_dead`.

- [ ] **Step 3: Write minimal implementation**

```python
# tools/services/encounter/get_encounter_state.py
def _format_resources(self, entity: EncounterEntity) -> dict[str, Any]:
    resources = ...
    death_saves = entity.combat_flags.get("death_saves")
    if isinstance(death_saves, dict):
        resources["death_saves"] = f"{death_saves.get('successes', 0)} 成功 / {death_saves.get('failures', 0)} 失败"
    return resources


# tools/services/map/render_battlemap_view.py
def _is_dead_entity(self, entity: EncounterEntity) -> bool:
    return bool(entity.combat_flags.get("is_dead"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest test.test_get_encounter_state test.test_render_battlemap_view`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_get_encounter_state.py test/test_render_battlemap_view.py tools/services/encounter/get_encounter_state.py tools/services/map/render_battlemap_view.py
git commit -m "feat: project dying and dead states to ui and llm view"
```

### Task 6: 全量验证

**Files:**
- No code changes required

- [ ] **Step 1: Run focused regression**

Run: `python3 -m unittest test.test_update_hp test.test_start_turn test.test_execute_attack test.test_get_encounter_state test.test_render_battlemap_view`

Expected: PASS

- [ ] **Step 2: Run full regression**

Run: `python3 -m unittest discover -s test -p 'test_*.py'`

Expected: PASS

- [ ] **Step 3: Review diff**

Run: `git diff -- test/test_update_hp.py test/test_start_turn.py test/test_execute_attack.py test/test_get_encounter_state.py test/test_render_battlemap_view.py tools/services/combat/shared/update_hp.py tools/services/combat/attack/execute_attack.py tools/services/combat/rules/death_saves/__init__.py tools/services/combat/rules/death_saves/resolve_death_save.py tools/services/encounter/turns/start_turn.py tools/services/encounter/get_encounter_state.py tools/services/map/render_battlemap_view.py`

Expected: only death-save, knockout, concentration, and render changes

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-04-15-death-saves-and-knockout-design.md docs/superpowers/plans/2026-04-15-death-saves-and-knockout.md test/test_update_hp.py test/test_start_turn.py test/test_execute_attack.py test/test_get_encounter_state.py test/test_render_battlemap_view.py tools/services/combat/shared/update_hp.py tools/services/combat/attack/execute_attack.py tools/services/combat/rules/death_saves/__init__.py tools/services/combat/rules/death_saves/resolve_death_save.py tools/services/encounter/turns/start_turn.py tools/services/encounter/get_encounter_state.py tools/services/map/render_battlemap_view.py
git commit -m "feat: add death saves and nonlethal knockout flow"
```
