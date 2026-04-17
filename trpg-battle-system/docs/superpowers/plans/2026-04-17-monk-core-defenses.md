# Monk Core Defenses Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把武僧的无甲防御、无甲移动、运转周天、拨挡攻击/能量、反射闪避接入现有战斗 runtime，并让它们通过真实规则链结算。

**Architecture:** 这次不新增一条武僧专属总线，而是把五项能力分别挂到既有主链：护甲解析器、回合资源刷新、先攻开始、反应框架、豁免伤害结算。所有主动选择都由 LLM 显式声明，后端负责掷骰、资源消耗、状态写回和事件结果。

**Tech Stack:** Python 3、unittest、现有 encounter/combat runtime services、TinyDB 仓储

---

## File Structure

**Modify**

- `trpg-battle-system/tools/services/combat/defense/armor_profile_resolver.py`
  - 接入 `Unarmored Defense` 基础 AC 方案
- `trpg-battle-system/tools/services/encounter/turns/turn_engine.py`
  - 接入 `Unarmored Movement` 对真实回合速度的刷新
- `trpg-battle-system/tools/services/encounter/roll_initiative_and_start_encounter.py`
  - 接入 `Uncanny Metabolism` 的先攻期显式触发
- `trpg-battle-system/tools/services/combat/rules/reactions/reaction_definitions.py`
  - 注册武僧拨挡反应
- `trpg-battle-system/tools/services/combat/rules/reactions/collect_reaction_candidates.py`
  - 命中后为满足条件的武僧开 `deflect_attacks` 窗口
- `trpg-battle-system/tools/services/combat/rules/reactions/resolve_reaction_option.py`
  - 接入武僧拨挡反应的 resolver
- `trpg-battle-system/tools/services/combat/attack/attack_roll_result.py`
  - 如有必要，把命中后上下文透传给反应窗口
- `trpg-battle-system/tools/services/combat/attack/execute_attack.py`
  - 让拨挡反应在 HP 结算前改写伤害，必要时处理反打结果
- `trpg-battle-system/tools/services/combat/save_spell/saving_throw_result.py`
  - 接入 `Evasion` 对 DEX 半伤类效果的伤害改写
- `trpg-battle-system/tools/services/spells/execute_spell.py`
  - 确保批量目标法术同样走 `Evasion` 改写后的伤害链
- `trpg-battle-system/tools/services/encounter/get_encounter_state.py`
  - 如有必要，只投影必要的武僧资源摘要，不暴露内部判定细节

**Create**

- `trpg-battle-system/tools/services/combat/rules/reactions/definitions/deflect_attacks.py`
  - 武僧拨挡反应专属 resolver

**Test**

- `trpg-battle-system/test/test_armor_profile_resolver.py`
- `trpg-battle-system/test/test_turn_engine.py`
- `trpg-battle-system/test/test_roll_initiative_and_start_encounter.py`
- `trpg-battle-system/test/test_attack_reaction_window.py`
- `trpg-battle-system/test/test_resolve_reaction_option.py`
- `trpg-battle-system/test/test_execute_attack.py`
- `trpg-battle-system/test/test_saving_throw_result.py`
- `trpg-battle-system/test/test_execute_spell.py`

### Task 1: Unarmored Defense And Unarmored Movement

**Files:**
- Modify: `trpg-battle-system/tools/services/combat/defense/armor_profile_resolver.py`
- Modify: `trpg-battle-system/tools/services/encounter/turns/turn_engine.py`
- Test: `trpg-battle-system/test/test_armor_profile_resolver.py`
- Test: `trpg-battle-system/test/test_turn_engine.py`

- [ ] **Step 1: Write the failing armor test**

```python
def test_resolve_unarmored_defense_for_monk_without_armor_or_shield(self) -> None:
    actor = build_entity()
    actor.ac = 12
    actor.ability_mods["dex"] = 3
    actor.ability_mods["wis"] = 2
    actor.class_features = {"monk": {"level": 3}}

    profile = ArmorProfileResolver().resolve(actor)

    self.assertEqual(profile["base_ac"], 15)
    self.assertEqual(profile["current_ac"], 15)
```

- [ ] **Step 2: Write the failing guard tests**

```python
def test_resolve_unarmored_defense_does_not_apply_when_wearing_armor(self) -> None:
    actor = build_entity()
    actor.ability_mods["dex"] = 3
    actor.ability_mods["wis"] = 2
    actor.class_features = {"monk": {"level": 3}}
    actor.equipped_armor = {"armor_id": "leather_armor"}

    profile = ArmorProfileResolver().resolve(actor)

    self.assertNotEqual(profile["base_ac"], 15)


def test_resolve_unarmored_defense_does_not_apply_when_using_shield(self) -> None:
    actor = build_entity()
    actor.ability_mods["dex"] = 3
    actor.ability_mods["wis"] = 2
    actor.class_features = {"monk": {"level": 3}}
    actor.equipped_shield = {"armor_id": "shield"}

    profile = ArmorProfileResolver().resolve(actor)

    self.assertNotEqual(profile["base_ac"], 15)
```

- [ ] **Step 3: Write the failing movement tests**

```python
def test_start_turn_applies_monk_unarmored_movement_bonus(self) -> None:
    entity = build_entity("ent_ally_eric_001", name="Eric", initiative=15)
    entity.class_features = {
        "monk": {
            "level": 6,
            "unarmored_movement_bonus_feet": 15,
        }
    }
    entity.speed["remaining"] = 0
    encounter = build_encounter(entity)

    updated = start_turn(encounter)

    self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 45)


def test_start_turn_does_not_apply_monk_unarmored_movement_when_armored(self) -> None:
    entity = build_entity("ent_ally_eric_001", name="Eric", initiative=15)
    entity.class_features = {
        "monk": {
            "level": 6,
            "unarmored_movement_bonus_feet": 15,
        }
    }
    entity.equipped_armor = {"armor_id": "leather_armor"}
    encounter = build_encounter(entity)

    updated = start_turn(encounter)

    self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 30)
```

- [ ] **Step 4: Run the focused tests to verify RED**

Run:

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
python3 -m unittest -v \
  test.test_armor_profile_resolver \
  test.test_turn_engine
```

Expected:

- New tests fail because monk AC / speed bonus is not implemented yet
- Existing unrelated tests stay green

- [ ] **Step 5: Write the minimal implementation**

```python
# armor_profile_resolver.py
from tools.services.class_features.shared import get_class_runtime, resolve_entity_proficiencies

def _resolve_unarmored_defense_base_ac(self, actor: EncounterEntity) -> int | None:
    monk_runtime = get_class_runtime(actor, "monk")
    if not isinstance(monk_runtime, dict):
        return None
    if actor.equipped_armor is not None or actor.equipped_shield is not None:
        return None
    return 10 + self._ability_mod(actor, "dex") + self._ability_mod(actor, "wis")


unarmored_base_ac = self._resolve_unarmored_defense_base_ac(actor)
if armor is None:
    base_armor_ac = unarmored_base_ac if isinstance(unarmored_base_ac, int) else 10 + dex_mod
```

```python
# turn_engine.py
from tools.services.class_features.shared import get_class_runtime

def _get_monk_unarmored_movement_bonus(entity: EncounterEntity) -> int:
    monk = get_class_runtime(entity, "monk")
    if not isinstance(monk, dict):
        return 0
    if entity.equipped_armor is not None or entity.equipped_shield is not None:
        return 0
    bonus = monk.get("unarmored_movement_bonus_feet", 0)
    return bonus if isinstance(bonus, int) and bonus > 0 else 0


speed_bonus = _get_monk_unarmored_movement_bonus(entity)
entity.speed["remaining"] = max(0, entity.speed["walk"] + speed_bonus - speed_penalty)
```

- [ ] **Step 6: Run the focused tests to verify GREEN**

Run:

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
python3 -m unittest -v \
  test.test_armor_profile_resolver \
  test.test_turn_engine
```

Expected:

- All tests pass

- [ ] **Step 7: Commit**

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
git add \
  tools/services/combat/defense/armor_profile_resolver.py \
  tools/services/encounter/turns/turn_engine.py \
  test/test_armor_profile_resolver.py \
  test/test_turn_engine.py
git commit -m "feat: add monk unarmored defense and movement"
```

### Task 2: Uncanny Metabolism On Initiative

**Files:**
- Modify: `trpg-battle-system/tools/services/encounter/roll_initiative_and_start_encounter.py`
- Test: `trpg-battle-system/test/test_roll_initiative_and_start_encounter.py`

- [ ] **Step 1: Write the failing initiative recovery tests**

```python
def test_execute_applies_uncanny_metabolism_when_declared(self) -> None:
    encounter = build_encounter_with_single_monk()
    monk = encounter.entities["ent_monk_001"]
    monk.current_hp = 9
    monk.max_hp = 20
    monk.class_features = {
        "monk": {
            "level": 5,
            "martial_arts_die": "1d8",
            "focus_points": {"max": 5, "remaining": 1},
            "uncanny_metabolism": {"available": True},
        }
    }
    self.repository.save(encounter)

    with patch("tools.services.encounter.roll_initiative_and_start_encounter.randint", side_effect=[12, 6]):
        with patch("tools.services.encounter.roll_initiative_and_start_encounter.random", return_value=0.11):
            result = RollInitiativeAndStartEncounter(self.repository).execute(
                "enc_test",
                initiative_options={"ent_monk_001": {"use_uncanny_metabolism": True}},
            )

    updated = self.repository.get("enc_test")
    monk = updated.entities["ent_monk_001"]
    self.assertEqual(monk.class_features["monk"]["focus_points"]["remaining"], 5)
    self.assertEqual(monk.current_hp, 20)
    self.assertFalse(monk.class_features["monk"]["uncanny_metabolism"]["available"])
```

```python
def test_execute_rejects_uncanny_metabolism_when_already_spent(self) -> None:
    encounter = build_encounter_with_single_monk()
    encounter.entities["ent_monk_001"].class_features = {
        "monk": {
            "level": 5,
            "martial_arts_die": "1d8",
            "focus_points": {"max": 5, "remaining": 1},
            "uncanny_metabolism": {"available": False},
        }
    }
    self.repository.save(encounter)

    with self.assertRaisesRegex(ValueError, "uncanny_metabolism_unavailable"):
        RollInitiativeAndStartEncounter(self.repository).execute(
            "enc_test",
            initiative_options={"ent_monk_001": {"use_uncanny_metabolism": True}},
        )
```

- [ ] **Step 2: Run the focused tests to verify RED**

Run:

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
python3 -m unittest -v test.test_roll_initiative_and_start_encounter
```

Expected:

- New tests fail because `initiative_options` and monk recovery are unsupported

- [ ] **Step 3: Write the minimal implementation**

```python
def execute(
    self,
    encounter_id: str,
    initiative_options: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ...
    for entity_id, entity in encounter.entities.items():
        ...
        option = (initiative_options or {}).get(entity_id, {})
        metabolism = self._apply_uncanny_metabolism_if_requested(entity, option)
        if metabolism is not None:
            metabolism_results.append(metabolism)
```

```python
def _apply_uncanny_metabolism_if_requested(self, entity: Any, option: dict[str, Any]) -> dict[str, Any] | None:
    if not bool(option.get("use_uncanny_metabolism")):
        return None
    monk = get_class_runtime(entity, "monk")
    if not isinstance(monk, dict):
        raise ValueError("uncanny_metabolism_requires_monk_runtime")
    runtime = monk.get("uncanny_metabolism")
    if not isinstance(runtime, dict) or not runtime.get("available", False):
        raise ValueError("uncanny_metabolism_unavailable")
    focus = monk.get("focus_points")
    ...
    focus["remaining"] = focus["max"]
    heal_total = roll_die(monk["martial_arts_die"]) + int(monk.get("level", 0))
    entity.current_hp = min(entity.max_hp, entity.current_hp + heal_total)
    runtime["available"] = False
    return {"entity_id": entity.entity_id, "healing": heal_total, "focus_restored": True}
```

- [ ] **Step 4: Run the focused tests to verify GREEN**

Run:

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
python3 -m unittest -v test.test_roll_initiative_and_start_encounter
```

Expected:

- All tests pass

- [ ] **Step 5: Commit**

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
git add \
  tools/services/encounter/roll_initiative_and_start_encounter.py \
  test/test_roll_initiative_and_start_encounter.py
git commit -m "feat: add monk uncanny metabolism on initiative"
```

### Task 3: Deflect Attacks / Deflect Energy Reaction

**Files:**
- Create: `trpg-battle-system/tools/services/combat/rules/reactions/definitions/deflect_attacks.py`
- Modify: `trpg-battle-system/tools/services/combat/rules/reactions/reaction_definitions.py`
- Modify: `trpg-battle-system/tools/services/combat/rules/reactions/collect_reaction_candidates.py`
- Modify: `trpg-battle-system/tools/services/combat/rules/reactions/resolve_reaction_option.py`
- Modify: `trpg-battle-system/tools/services/combat/attack/execute_attack.py`
- Test: `trpg-battle-system/test/test_attack_reaction_window.py`
- Test: `trpg-battle-system/test/test_resolve_reaction_option.py`
- Test: `trpg-battle-system/test/test_execute_attack.py`

- [ ] **Step 1: Write the failing reaction-window tests**

```python
def test_execute_attack_returns_waiting_reaction_when_target_can_deflect_attacks(self) -> None:
    target.class_features = {
        "monk": {
            "level": 5,
            "deflect_attacks": {"enabled": True},
            "focus_points": {"max": 5, "remaining": 3},
        }
    }
    result = self.service.execute(...)
    self.assertEqual(result["status"], "waiting_reaction")
    self.assertEqual(result["pending_reaction_window"]["groups"][0]["options"][0]["reaction_type"], "deflect_attacks")
```

```python
def test_execute_attack_does_not_open_deflect_window_for_non_bps_damage(self) -> None:
    result = self.service.execute(
        ...,
        damage_rolls=[{"source": "weapon", "formula": "1d8", "type": "fire", "rolls": [6]}],
    )
    self.assertEqual(result["status"], "ok")
```

- [ ] **Step 2: Write the failing resolver tests**

```python
def test_execute_resolves_deflect_attacks_and_reduces_damage_before_hp_update(self) -> None:
    reaction_result = self.service.execute(
        encounter_id="enc_test",
        reaction_request_id="req_001",
        selected_option_id="opt_deflect",
        option_payload={"reduction_roll": 7},
    )
    self.assertEqual(reaction_result["status"], "deflect_damage_reduced")
    self.assertEqual(reaction_result["damage_prevented"], 15)
```

```python
def test_execute_resolves_deflect_attacks_zero_damage_and_counter_redirect(self) -> None:
    reaction_result = self.service.execute(
        encounter_id="enc_test",
        reaction_request_id="req_001",
        selected_option_id="opt_deflect",
        option_payload={
            "reduction_roll": 9,
            "redirect_enabled": True,
            "redirect_target_id": "ent_enemy_002",
            "redirect_save_roll": 7,
            "redirect_damage_rolls": [5, 4],
        },
    )
    self.assertEqual(reaction_result["status"], "deflect_redirect_resolved")
    self.assertEqual(reaction_result["redirect_resolution"]["total_damage"], 12)
```

- [ ] **Step 3: Run the focused tests to verify RED**

Run:

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
python3 -m unittest -v \
  test.test_attack_reaction_window \
  test.test_resolve_reaction_option \
  test.test_execute_attack
```

Expected:

- New tests fail because monk deflect reaction is not registered

- [ ] **Step 4: Write the minimal implementation**

```python
# reaction_definitions.py
"deflect_attacks": {
    "reaction_type": "deflect_attacks",
    "trigger_type": "on_attack_hit",
    "resolver": {"service": "resolve_deflect_attacks_reaction"},
}
```

```python
# collect_reaction_candidates.py
if trigger_type == "on_attack_hit":
    if self._eligible_for_deflect_attacks(target, payload):
        options.append(self._build_deflect_attacks_option(target, payload))

def _eligible_for_deflect_attacks(self, entity: Any, payload: dict[str, Any]) -> bool:
    monk = get_class_runtime(entity, "monk")
    if not isinstance(monk, dict):
        return False
    if not self._reaction_available(entity):
        return False
    if not self._attack_payload_contains_deflectable_damage(payload, monk):
        return False
    return bool(monk.get("deflect_attacks", {}).get("enabled"))
```

```python
# definitions/deflect_attacks.py
class ResolveDeflectAttacksReaction:
    def execute(...):
        reduction = reduction_roll + dex_mod + monk_level
        prevented = min(incoming_damage, reduction)
        actor.action_economy["reaction_used"] = True
        remaining_damage = max(0, incoming_damage - prevented)
        if remaining_damage > 0:
            return {"status": "deflect_damage_reduced", "remaining_damage": remaining_damage}
        if redirect_enabled:
            focus["remaining"] -= 1
            return {"status": "deflect_redirect_resolved", ...}
        return {"status": "deflect_damage_reduced", "remaining_damage": 0}
```

```python
# resolve_reaction_option.py
if reaction_type == "deflect_attacks":
    return self.deflect_attacks_resolver.execute(...)
```

```python
# execute_attack.py
if reaction_result.get("status") in {"deflect_damage_reduced", "deflect_redirect_resolved"}:
    damage_resolution["total_damage"] = reaction_result["remaining_damage"]
    if damage_resolution["total_damage"] == 0:
        hp_update = None
```

- [ ] **Step 5: Run the focused tests to verify GREEN**

Run:

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
python3 -m unittest -v \
  test.test_attack_reaction_window \
  test.test_resolve_reaction_option \
  test.test_execute_attack
```

Expected:

- All tests pass

- [ ] **Step 6: Commit**

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
git add \
  tools/services/combat/rules/reactions/definitions/deflect_attacks.py \
  tools/services/combat/rules/reactions/reaction_definitions.py \
  tools/services/combat/rules/reactions/collect_reaction_candidates.py \
  tools/services/combat/rules/reactions/resolve_reaction_option.py \
  tools/services/combat/attack/execute_attack.py \
  test/test_attack_reaction_window.py \
  test/test_resolve_reaction_option.py \
  test/test_execute_attack.py
git commit -m "feat: add monk deflect attacks reaction"
```

### Task 4: Evasion On Dexterity Save Damage

**Files:**
- Modify: `trpg-battle-system/tools/services/combat/save_spell/saving_throw_result.py`
- Modify: `trpg-battle-system/tools/services/spells/execute_spell.py`
- Test: `trpg-battle-system/test/test_saving_throw_result.py`
- Test: `trpg-battle-system/test/test_execute_spell.py`

- [ ] **Step 1: Write the failing evasion tests**

```python
def test_execute_fireball_evasion_success_takes_zero_damage(self) -> None:
    target.class_features = {"monk": {"level": 7, "evasion": {"enabled": True}}}
    result = self.service.execute(... fireball ..., save_rolls=[{"target_id": target.entity_id, "roll": 18}])
    self.assertEqual(result["target_results"][0]["damage_resolution"]["total_damage"], 0)
```

```python
def test_execute_fireball_evasion_failure_takes_half_damage(self) -> None:
    target.class_features = {"monk": {"level": 7, "evasion": {"enabled": True}}}
    result = self.service.execute(... fireball ..., save_rolls=[{"target_id": target.entity_id, "roll": 5}])
    self.assertEqual(result["target_results"][0]["damage_resolution"]["total_damage"], 14)
```

```python
def test_execute_fireball_evasion_does_not_apply_when_incapacitated(self) -> None:
    target.class_features = {"monk": {"level": 7, "evasion": {"enabled": True}}}
    target.conditions = ["incapacitated"]
    result = self.service.execute(... fireball ..., save_rolls=[{"target_id": target.entity_id, "roll": 18}])
    self.assertGreater(result["target_results"][0]["damage_resolution"]["total_damage"], 0)
```

- [ ] **Step 2: Run the focused tests to verify RED**

Run:

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
python3 -m unittest -v \
  test.test_saving_throw_result \
  test.test_execute_spell
```

Expected:

- New tests fail because monk evasion is not applied

- [ ] **Step 3: Write the minimal implementation**

```python
def _apply_evasion_if_eligible(
    self,
    *,
    target: Any,
    roll_request: RollRequest,
    success: bool,
    damage_resolution: dict[str, Any] | None,
    outcome_key: str,
) -> dict[str, Any] | None:
    monk = get_class_runtime(target, "monk")
    if not isinstance(monk, dict):
        return damage_resolution
    if not monk.get("evasion", {}).get("enabled"):
        return damage_resolution
    if "incapacitated" in normalize_conditions(target.conditions):
        return damage_resolution
    if roll_request.context.get("save_ability") != "dex":
        return damage_resolution
    if outcome_key not in {"failed_save", "successful_save"}:
        return damage_resolution
    if success:
        damage_resolution["total_damage"] = 0
        for part in damage_resolution.get("parts", []):
            part["adjusted_total"] = 0
    else:
        damage_resolution["total_damage"] //= 2
    return damage_resolution
```

- [ ] **Step 4: Run the focused tests to verify GREEN**

Run:

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
python3 -m unittest -v \
  test.test_saving_throw_result \
  test.test_execute_spell
```

Expected:

- All tests pass

- [ ] **Step 5: Commit**

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
git add \
  tools/services/combat/save_spell/saving_throw_result.py \
  tools/services/spells/execute_spell.py \
  test/test_saving_throw_result.py \
  test/test_execute_spell.py
git commit -m "feat: add monk evasion damage rewrite"
```

### Task 5: Regression Sweep And Summary Projection Check

**Files:**
- Modify: `trpg-battle-system/tools/services/encounter/get_encounter_state.py`
- Test: `trpg-battle-system/test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing projection test if new fields are needed**

```python
def test_execute_projects_monk_core_runtime_resources(self) -> None:
    entity.class_features = {
        "monk": {
            "level": 7,
            "focus_points": {"max": 7, "remaining": 4},
            "unarmored_movement_bonus_feet": 15,
            "uncanny_metabolism": {"available": False},
            "evasion": {"enabled": True},
        }
    }
    state = GetEncounterState(repo).execute("enc_test")
    monk = state["entities"][0]["class_features"]["monk"]
    self.assertEqual(monk["focus_points"]["remaining"], 4)
```

- [ ] **Step 2: Run the focused test to verify RED if projection changed**

Run:

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
python3 -m unittest -v test.test_get_encounter_state
```

Expected:

- Only fails if the new summary field is intentionally added
- If no projection change is needed, skip directly to Step 5 and note that this task was N/A

- [ ] **Step 3: Write the minimal implementation if projection changed**

```python
monk_summary["uncanny_metabolism_available"] = bool(
    monk_runtime.get("uncanny_metabolism", {}).get("available", False)
)
monk_summary["evasion_enabled"] = bool(
    monk_runtime.get("evasion", {}).get("enabled", False)
)
```

- [ ] **Step 4: Run the focused test to verify GREEN**

Run:

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
python3 -m unittest -v test.test_get_encounter_state
```

Expected:

- Projection tests pass

- [ ] **Step 5: Run full monk-related regression**

Run:

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
python3 -m unittest -v \
  test.test_armor_profile_resolver \
  test.test_turn_engine \
  test.test_roll_initiative_and_start_encounter \
  test.test_attack_reaction_window \
  test.test_resolve_reaction_option \
  test.test_execute_attack \
  test.test_saving_throw_result \
  test.test_execute_spell \
  test.test_get_encounter_state
```

Expected:

- All targeted tests pass

- [ ] **Step 6: Run full repository regression**

Run:

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
python3 -m unittest discover -s test -v
```

Expected:

- Full suite passes

- [ ] **Step 7: Commit the final integration if Task 5 changed code**

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
git add \
  tools/services/encounter/get_encounter_state.py \
  test/test_get_encounter_state.py
git commit -m "feat: project monk core defense runtime summaries"
```

## Self-Review

### Spec coverage

- `Unarmored Defense`: Task 1
- `Unarmored Movement`: Task 1
- `Uncanny Metabolism`: Task 2
- `Deflect Attacks / Deflect Energy`: Task 3
- `Evasion`: Task 4
- 状态摘要与回归确认：Task 5

没有发现 spec 要求但计划未覆盖的空白项。

### Placeholder scan

- 没有使用 `TODO`、`TBD`、`implement later`
- 每个任务都给了文件、测试、命令和预期结果

### Type consistency

- `initiative_options` 统一用 `dict[str, dict[str, Any]] | None`
- 武僧 runtime 统一从 `class_features["monk"]` 读取
- 反应类型统一命名为 `deflect_attacks`
- `uncanny_metabolism.available`、`evasion.enabled`、`deflect_attacks.enabled` 命名保持一致
