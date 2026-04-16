# Action Economy Attack Consumption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让武器攻击在完整结算后消费当前行动者的 `action_economy.action_used`,并把变化通过 `encounter_state` 暴露给前端.

**Architecture:** 保持 `EncounterEntity.action_economy` 作为每回合资源容器,`AttackRollRequest` 只负责前置校验,`ExecuteAttack` 负责完整流程副作用,在攻击流程结束后更新当前行动者的 `action_used`.`GetEncounterState` 继续作为前端唯一读模型输出,不新增宿主概念或额外状态通道.

**Tech Stack:** Python 3.9, TinyDB repository, unittest

---

### Task 1: 补攻击消费 action 的行为测试

**Files:**
- Modify: `test/test_execute_attack.py`
- Test: `test/test_execute_attack.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_execute_marks_action_used_after_attack_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                hp_change=4,
                damage_reason="Rapier damage",
                damage_type="piercing",
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            assert updated is not None
            self.assertTrue(updated.entities["ent_ally_eric_001"].action_economy["action_used"])
            encounter_repo.close()
            event_repo.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_execute_attack.ExecuteAttackTests.test_execute_marks_action_used_after_attack_resolves`
Expected: FAIL because `action_used` is still missing or false

- [ ] **Step 3: Write minimal implementation**

```python
        resolution = self.attack_roll_result.execute(...)
        self._mark_action_used(encounter_id)

    def _mark_action_used(self, encounter_id: str) -> None:
        encounter = self.attack_roll_request.encounter_repository.get(encounter_id)
        if encounter is None or encounter.current_entity_id is None:
            return
        actor = encounter.entities.get(encounter.current_entity_id)
        if actor is None:
            return
        actor.action_economy["action_used"] = True
        self.attack_roll_request.encounter_repository.save(encounter)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest test.test_execute_attack.ExecuteAttackTests.test_execute_marks_action_used_after_attack_resolves`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_execute_attack.py tools/services/combat/attack/execute_attack.py
git commit -m "feat: consume action on weapon attack"
```

### Task 2: 补前端读模型可见性测试

**Files:**
- Modify: `test/test_execute_attack.py`
- Test: `test/test_execute_attack.py`

- [ ] **Step 1: Write the failing test**

```python
            self.assertTrue(
                result["encounter_state"]["current_turn_entity"]["actions"]["action_used"]
            )
```

把上面断言加进现有 `test_execute_can_include_latest_encounter_state`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_execute_attack.ExecuteAttackTests.test_execute_can_include_latest_encounter_state`
Expected: FAIL because returned state still shows `action_used` as false

- [ ] **Step 3: Write minimal implementation**

```python
        if include_encounter_state:
            result["encounter_state"] = GetEncounterState(
                self.attack_roll_request.encounter_repository
            ).execute(encounter_id)
```

确保这段读取发生在 `_mark_action_used(encounter_id)` 之后.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest test.test_execute_attack.ExecuteAttackTests.test_execute_can_include_latest_encounter_state`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_execute_attack.py tools/services/combat/attack/execute_attack.py
git commit -m "test: expose action economy in attack encounter state"
```

### Task 3: 做回归验证

**Files:**
- Modify: `tools/services/combat/attack/execute_attack.py`
- Test: `test/test_execute_attack.py`
- Test: `test/test_attack_roll_request.py`

- [ ] **Step 1: Run focused attack tests**

Run: `python3 -m unittest test/test_attack_roll_request.py test/test_execute_attack.py`
Expected: PASS

- [ ] **Step 2: Run full suite**

Run: `python3 -m unittest discover -s test -p 'test_*.py'`
Expected: PASS with all tests green

- [ ] **Step 3: Review final diff**

Run: `git diff -- tools/services/combat/attack/execute_attack.py test/test_execute_attack.py`
Expected: only action economy consumption and related assertions changed

- [ ] **Step 4: Commit**

```bash
git add tools/services/combat/attack/execute_attack.py test/test_execute_attack.py
git commit -m "feat: surface action economy after attacks"
```
