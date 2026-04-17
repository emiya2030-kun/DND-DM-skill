# Martial Class Features Round 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Monk / Rogue / Fighter 接入第二轮战斗内职业特性，包括 `Patient Defense`、`Step of the Wind`、`Slow Fall`、补齐 `Cunning Strike`、以及 `Tactical Mind` 与第一批 `Fighting Style`。

**Architecture:** 主动职业能力新增独立 service 并复用现有动作经济与 turn effect 结构；被动能力挂回攻击、检定、AC、伤害等主链；新能力继续通过 `GetEncounterState` 与 playbook 以摘要方式暴露给 LLM 与前端。

**Tech Stack:** Python 3、unittest/pytest、TinyDB repository、现有 combat runtime services

---

## File Map

- Modify: `tools/services/class_features/shared/runtime.py`
  - 补共享 runtime 读取/写入辅助，增加 monk runtime 读取能力。
- Modify: `tools/services/class_features/shared/__init__.py`
  - 导出新增共享 helper。
- Create: `tools/services/class_features/monk/__init__.py`
  - 导出 `UsePatientDefense`、`UseStepOfTheWind`。
- Create: `tools/services/class_features/monk/use_patient_defense.py`
  - 武僧 `Patient Defense` 主动 service。
- Create: `tools/services/class_features/monk/use_step_of_the_wind.py`
  - 武僧 `Step of the Wind` 主动 service。
- Create: `tools/services/combat/damage/resolve_fall_damage.py`
  - 最小坠落伤害结算入口，挂 `Slow Fall`。
- Modify: `tools/services/combat/shared/update_conditions.py`
  - 让 `dazed`、`blinded`、`unconscious` 这类由 `Cunning Strike` 产生的效果可稳定挂入/清除。
- Modify: `tools/services/combat/attack/attack_roll_request.py`
  - 继续负责 `Cunning Strike` 声明合法性与等级门槛。
- Modify: `tools/services/combat/attack/execute_attack.py`
  - 补齐 `poison / daze / knock_out / obscure` 的效果结算，并接入 `Dueling` 伤害加值。
- Modify: `tools/services/checks/execute_ability_check.py`
  - 新增 `class_feature_options` 入口，支持 `Tactical Mind`。
- Modify: `tools/services/checks/resolve_ability_check.py`
  - 真正执行 `Tactical Mind` 的失败后补骰与 `Second Wind` 消耗规则。
- Modify: `tools/services/combat/defense/armor_profile_resolver.py`
  - 接入 `Defense` fighting style 的 AC +1。
- Modify: `tools/services/encounter/get_encounter_state.py`
  - 投影新增 Monk / Rogue / Fighter 能力摘要。
- Modify: `docs/skill-playbooks/monk.md`
- Modify: `docs/skill-playbooks/rogue.md`
- Modify: `docs/skill-playbooks/fighter.md`
  - 更新 LLM 调用协议。

### Task 1: Monk 主动能力服务

**Files:**
- Create: `tools/services/class_features/monk/use_patient_defense.py`
- Create: `tools/services/class_features/monk/use_step_of_the_wind.py`
- Create: `tools/services/class_features/monk/__init__.py`
- Modify: `tools/services/class_features/shared/runtime.py`
- Modify: `tools/services/class_features/shared/__init__.py`
- Test: `test/test_use_patient_defense.py`
- Test: `test/test_use_step_of_the_wind.py`

- [ ] **Step 1: 写失败测试，锁定 Patient Defense 基础版与强化版**

```python
def test_use_patient_defense_base_applies_disengage_and_spends_bonus_action() -> None:
    result = UsePatientDefense(repo).execute(
        encounter_id="enc_monk_test",
        actor_id="ent_monk_001",
        spend_focus=False,
    )
    updated = repo.get("enc_monk_test")
    monk = updated.entities["ent_monk_001"]
    assert monk.action_economy["bonus_action_used"] is True
    assert any(effect.get("effect_type") == "disengage" for effect in monk.turn_effects)
    assert not any(effect.get("effect_type") == "dodge" for effect in monk.turn_effects)
    assert result["class_feature_result"]["patient_defense"]["spent_focus"] is False


def test_use_patient_defense_focus_mode_adds_dodge_and_spends_focus_point() -> None:
    UsePatientDefense(repo).execute(
        encounter_id="enc_monk_test",
        actor_id="ent_monk_001",
        spend_focus=True,
    )
    updated = repo.get("enc_monk_test")
    monk = updated.entities["ent_monk_001"]
    assert any(effect.get("effect_type") == "disengage" for effect in monk.turn_effects)
    assert any(effect.get("effect_type") == "dodge" for effect in monk.turn_effects)
    assert monk.class_features["monk"]["focus_points"]["remaining"] == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run:

```bash
python3 -m pytest /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_use_patient_defense.py -q
```

Expected:

- `ModuleNotFoundError` 或 `AttributeError`

- [ ] **Step 3: 写最小实现**

```python
class UsePatientDefense:
    def execute(self, *, encounter_id: str, actor_id: str, spend_focus: bool = False) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_bonus_action_available(actor)

        monk = get_monk_runtime(actor)
        focus_points = monk.get("focus_points") or {}
        if spend_focus:
            remaining = int(focus_points.get("remaining", 0))
            if remaining <= 0:
                raise ValueError("patient_defense_requires_focus_points")
            focus_points["remaining"] = remaining - 1

        actor.action_economy["bonus_action_used"] = True
        add_or_replace_turn_effect(actor, {... "effect_type": "disengage" ...})
        if spend_focus:
            add_or_replace_turn_effect(actor, {... "effect_type": "dodge" ...})
        self.encounter_repository.save(encounter)
        return {...}
```

- [ ] **Step 4: 写 Step of the Wind 的失败测试**

```python
def test_use_step_of_the_wind_base_grants_dash_and_spends_bonus_action() -> None:
    result = UseStepOfTheWind(repo).execute(
        encounter_id="enc_monk_test",
        actor_id="ent_monk_001",
        spend_focus=False,
    )
    updated = repo.get("enc_monk_test")
    monk = updated.entities["ent_monk_001"]
    assert monk.action_economy["bonus_action_used"] is True
    assert result["class_feature_result"]["step_of_the_wind"]["grants_dash"] is True


def test_use_step_of_the_wind_focus_mode_adds_disengage_and_jump_multiplier() -> None:
    result = UseStepOfTheWind(repo).execute(
        encounter_id="enc_monk_test",
        actor_id="ent_monk_001",
        spend_focus=True,
    )
    updated = repo.get("enc_monk_test")
    monk = updated.entities["ent_monk_001"]
    assert monk.class_features["monk"]["focus_points"]["remaining"] == 1
    assert any(effect.get("effect_type") == "disengage" for effect in monk.turn_effects)
    assert any(effect.get("effect_type") == "jump_distance_multiplier" for effect in monk.turn_effects)
    assert result["class_feature_result"]["step_of_the_wind"]["jump_distance_multiplier"] == 2
```

- [ ] **Step 5: 跑 Step of the Wind 测试确认失败**

Run:

```bash
python3 -m pytest /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_use_step_of_the_wind.py -q
```

Expected:

- `ModuleNotFoundError` 或断言失败

- [ ] **Step 6: 写最小实现并导出**

```python
class UseStepOfTheWind:
    def execute(self, *, encounter_id: str, actor_id: str, spend_focus: bool = False) -> dict[str, Any]:
        ...
        actor.action_economy["bonus_action_used"] = True
        actor.action_economy["dash_available"] = int(actor.action_economy.get("dash_available", 0)) + 1
        if spend_focus:
            add_or_replace_turn_effect(actor, {... "effect_type": "disengage" ...})
            add_or_replace_turn_effect(actor, {... "effect_type": "jump_distance_multiplier", "multiplier": 2 ...})
        ...
```

- [ ] **Step 7: 跑两组测试确认通过**

Run:

```bash
python3 -m pytest \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_use_patient_defense.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_use_step_of_the_wind.py -q
```

Expected:

- `4 passed`

- [ ] **Step 8: Commit**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  test/test_use_patient_defense.py \
  test/test_use_step_of_the_wind.py \
  tools/services/class_features/monk/__init__.py \
  tools/services/class_features/monk/use_patient_defense.py \
  tools/services/class_features/monk/use_step_of_the_wind.py \
  tools/services/class_features/shared/runtime.py \
  tools/services/class_features/shared/__init__.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: add monk defensive movement actions"
```

### Task 2: Slow Fall 与最小坠落伤害链

**Files:**
- Create: `tools/services/combat/damage/resolve_fall_damage.py`
- Modify: `tools/services/combat/rules/reactions/reaction_definitions.py`
- Modify: `tools/repositories/reaction_definition_repository.py`
- Test: `test/test_resolve_fall_damage.py`

- [ ] **Step 1: 写失败测试，覆盖普通坠落与 Slow Fall**

```python
def test_resolve_fall_damage_applies_raw_fall_damage_without_slow_fall() -> None:
    result = ResolveFallDamage(repo).execute(
        encounter_id="enc_fall_test",
        actor_id="ent_monk_001",
        damage=12,
        use_slow_fall=False,
    )
    updated = repo.get("enc_fall_test")
    assert updated.entities["ent_monk_001"].hp["current"] == 8
    assert result["fall_resolution"]["final_damage"] == 12


def test_resolve_fall_damage_reduces_damage_by_five_times_monk_level_and_spends_reaction() -> None:
    result = ResolveFallDamage(repo).execute(
        encounter_id="enc_fall_test",
        actor_id="ent_monk_001",
        damage=18,
        use_slow_fall=True,
    )
    updated = repo.get("enc_fall_test")
    monk = updated.entities["ent_monk_001"]
    assert monk.action_economy["reaction_used"] is True
    assert result["fall_resolution"]["reduction"] == 20
    assert result["fall_resolution"]["final_damage"] == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run:

```bash
python3 -m pytest /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_resolve_fall_damage.py -q
```

Expected:

- `ModuleNotFoundError`

- [ ] **Step 3: 写最小实现**

```python
class ResolveFallDamage:
    def execute(self, *, encounter_id: str, actor_id: str, damage: int, use_slow_fall: bool = False) -> dict[str, Any]:
        encounter = self.encounter_repository.get(encounter_id)
        actor = encounter.entities[actor_id]
        monk = get_monk_runtime(actor)
        reduction = 0
        if use_slow_fall:
            level = int(monk.get("level", 0))
            if bool(actor.action_economy.get("reaction_used")):
                raise ValueError("reaction_already_used")
            reduction = max(0, 5 * level)
            actor.action_economy["reaction_used"] = True
        final_damage = max(0, damage - reduction)
        actor.hp["current"] = max(0, actor.hp["current"] - final_damage)
        self.encounter_repository.save(encounter)
        return {"fall_resolution": {"base_damage": damage, "reduction": reduction, "final_damage": final_damage}}
```

- [ ] **Step 4: 跑测试确认通过**

Run:

```bash
python3 -m pytest /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_resolve_fall_damage.py -q
```

Expected:

- `2 passed`

- [ ] **Step 5: Commit**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  test/test_resolve_fall_damage.py \
  tools/services/combat/damage/resolve_fall_damage.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: add monk slow fall damage resolution"
```

### Task 3: Rogue Cunning Strike 全效果补齐

**Files:**
- Modify: `tools/services/combat/attack/attack_roll_request.py`
- Modify: `tools/services/combat/attack/execute_attack.py`
- Modify: `tools/services/combat/shared/update_conditions.py`
- Test: `test/test_attack_roll_request.py`
- Test: `test/test_execute_attack.py`

- [ ] **Step 1: 写失败测试，锁定高阶诡诈打击效果**

```python
def test_execute_cunning_strike_poison_applies_poisoned_with_repeat_save() -> None:
    result = service.execute(
        encounter_id="enc_attack_test",
        actor_id="ent_rogue_001",
        target_id="ent_target_001",
        weapon_id="rapier",
        class_feature_options={"sneak_attack": True, "cunning_strike": {"effects": ["poison"]}},
        final_total=19,
        dice_rolls={"base_rolls": [14], "chosen_roll": 14},
    )
    effect = result["resolution"]["class_features"]["rogue"]["cunning_strike"]["effects"][0]
    assert effect["effect"] == "poison"
    assert effect["applied"] is True


def test_execute_cunning_strike_knock_out_applies_unconscious_until_damage_or_save_end() -> None:
    ...
    assert "unconscious" in updated.entities["ent_target_001"].conditions
```

- [ ] **Step 2: 跑定点测试确认失败**

Run:

```bash
python3 -m pytest \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_attack_roll_request.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_execute_attack.py -q -k "cunning_strike or poison or daze or knock_out or obscure"
```

Expected:

- 至少 1 个失败，显示未实现效果或返回结构不匹配

- [ ] **Step 3: 在请求层补齐等级门槛与效果白名单**

```python
allowed = {"poison", "trip", "withdraw"} if level >= 5 else set()
if level >= 14:
    allowed.update({"daze", "knock_out", "obscure"})
```

- [ ] **Step 4: 在结算层补齐效果实现**

```python
elif effect_name == "poison":
    result = self._resolve_cunning_strike_save_effect(
        save_ability="con",
        effect_name="poison",
        applied_condition="poisoned",
        repeat_save={"timing": "end_of_turn", "ability": "con"},
    )
elif effect_name == "knock_out":
    result = self._resolve_cunning_strike_save_effect(
        save_ability="con",
        effect_name="knock_out",
        applied_condition="unconscious",
        ends_on_damage=True,
        repeat_save={"timing": "end_of_turn", "ability": "con"},
    )
```

- [ ] **Step 5: 跑定点测试确认通过**

Run:

```bash
python3 -m pytest \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_attack_roll_request.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_execute_attack.py -q -k "cunning_strike or poison or daze or knock_out or obscure"
```

Expected:

- 相关用例全部通过

- [ ] **Step 6: Commit**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  test/test_attack_roll_request.py \
  test/test_execute_attack.py \
  tools/services/combat/attack/attack_roll_request.py \
  tools/services/combat/attack/execute_attack.py \
  tools/services/combat/shared/update_conditions.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: complete rogue cunning strike effects"
```

### Task 4: Fighter Tactical Mind

**Files:**
- Modify: `tools/services/checks/execute_ability_check.py`
- Modify: `tools/services/checks/resolve_ability_check.py`
- Test: `test/test_execute_ability_check.py`
- Test: `test/test_resolve_ability_check.py`

- [ ] **Step 1: 写失败测试，覆盖 Tactical Mind 成功与失败两条路径**

```python
def test_execute_tactical_mind_turns_failed_check_into_success_and_spends_second_wind() -> None:
    with patch("tools.services.checks.execute_ability_check.random.randint", side_effect=[6, 8]):
        result = service.execute(
            encounter_id="enc_ability_check_test",
            actor_id="ent_fighter_001",
            check_type="ability",
            check="str",
            dc=15,
            class_feature_options={"tactical_mind": True},
        )
    assert result["success"] is True
    assert result["class_feature_result"]["tactical_mind"]["consumed_second_wind"] is True


def test_execute_tactical_mind_keeps_second_wind_when_bonus_still_fails() -> None:
    ...
    assert result["success"] is False
    assert result["class_feature_result"]["tactical_mind"]["consumed_second_wind"] is False
```

- [ ] **Step 2: 跑测试确认失败**

Run:

```bash
python3 -m pytest \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_execute_ability_check.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_resolve_ability_check.py -q -k "tactical_mind"
```

Expected:

- 参数不识别或结果字段缺失

- [ ] **Step 3: 在入口层新增 `class_feature_options` 参数并传入 resolve**

```python
def execute(..., class_feature_options: dict[str, Any] | None = None, ...):
    ...
    roll_result = self.resolve_service.execute(
        encounter_id=encounter_id,
        roll_request=request,
        base_rolls=base_rolls,
        additional_bonus=additional_bonus,
        metadata={"class_feature_options": class_feature_options or {}},
    )
```

- [ ] **Step 4: 在 resolve 层实现 Tactical Mind**

```python
if tactical_mind_requested and final_total < dc:
    bonus_roll = random.randint(1, 10)
    retry_total = final_total + bonus_roll
    consumed = retry_total >= dc
    if consumed:
        fighter["second_wind"]["remaining_uses"] -= 1
    result_metadata["tactical_mind"] = {
        "used": True,
        "bonus_roll": bonus_roll,
        "consumed_second_wind": consumed,
        "retry_total": retry_total,
    }
    final_total = retry_total
```

- [ ] **Step 5: 跑测试确认通过**

Run:

```bash
python3 -m pytest \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_execute_ability_check.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_resolve_ability_check.py -q -k "tactical_mind"
```

Expected:

- `tactical_mind` 相关用例通过

- [ ] **Step 6: Commit**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  test/test_execute_ability_check.py \
  test/test_resolve_ability_check.py \
  tools/services/checks/execute_ability_check.py \
  tools/services/checks/resolve_ability_check.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: add fighter tactical mind"
```

### Task 5: Fighter Fighting Style 第一批

**Files:**
- Modify: `tools/services/combat/defense/armor_profile_resolver.py`
- Modify: `tools/services/combat/attack/attack_roll_request.py`
- Modify: `tools/services/combat/attack/execute_attack.py`
- Test: `test/test_armor_profile_resolver.py`
- Test: `test/test_attack_roll_request.py`
- Test: `test/test_execute_attack.py`

- [ ] **Step 1: 写失败测试，覆盖 `Defense` / `Archery` / `Dueling`**

```python
def test_resolve_defense_style_adds_one_ac_while_wearing_armor() -> None:
    profile = resolver.refresh_entity_armor_class(fighter_with_style("defense"))
    assert profile["ac_breakdown"]["fighting_style_bonus"] == 1


def test_execute_archery_style_adds_two_to_ranged_attack_bonus() -> None:
    request = service.execute(...)
    assert request.context["attack_bonus_breakdown"]["fighting_style_bonus"] == 2


def test_execute_dueling_style_adds_two_damage_for_one_handed_melee_attack() -> None:
    result = service.execute(...)
    assert result["resolution"]["damage_resolution"]["parts"][0]["modifier"] >= 2
```

- [ ] **Step 2: 跑测试确认失败**

Run:

```bash
python3 -m pytest \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_armor_profile_resolver.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_attack_roll_request.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_execute_attack.py -q -k "fighting_style or defense style or archery style or dueling style"
```

Expected:

- 断言失败

- [ ] **Step 3: 在 AC / 攻击 / 伤害链分别接入 fighting style**

```python
style_id = str(fighter_runtime.get("fighting_style", {}).get("style_id", "")).strip().lower()
if style_id == "defense" and armor_definition is not None:
    ac_bonus += 1

if style_id == "archery" and attack_kind == "ranged_weapon":
    attack_bonus += 2

if style_id == "dueling" and is_one_handed_melee and not off_hand_has_weapon:
    damage_parts[0]["modifier"] = int(damage_parts[0].get("modifier", 0)) + 2
```

- [ ] **Step 4: 跑测试确认通过**

Run:

```bash
python3 -m pytest \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_armor_profile_resolver.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_attack_roll_request.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_execute_attack.py -q -k "fighting_style or defense style or archery style or dueling style"
```

Expected:

- 对应风格测试通过

- [ ] **Step 5: Commit**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  test/test_armor_profile_resolver.py \
  test/test_attack_roll_request.py \
  test/test_execute_attack.py \
  tools/services/combat/defense/armor_profile_resolver.py \
  tools/services/combat/attack/attack_roll_request.py \
  tools/services/combat/attack/execute_attack.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: add fighter fighting styles"
```

### Task 6: 状态投影、playbook 与全量验证

**Files:**
- Modify: `tools/services/encounter/get_encounter_state.py`
- Modify: `docs/skill-playbooks/monk.md`
- Modify: `docs/skill-playbooks/rogue.md`
- Modify: `docs/skill-playbooks/fighter.md`
- Test: `test/test_get_encounter_state.py`

- [ ] **Step 1: 写失败测试，锁定新增职业能力摘要**

```python
def test_execute_projects_monk_bonus_action_features() -> None:
    state = service.execute("enc_state_test")
    monk = state["current_turn_entity"]["resources"]["class_features"]["monk"]
    assert "patient_defense" in monk["available_features"]
    assert "step_of_the_wind" in monk["available_features"]


def test_execute_projects_fighter_tactical_mind_and_style() -> None:
    state = service.execute("enc_state_test")
    fighter = state["current_turn_entity"]["resources"]["class_features"]["fighter"]
    assert fighter["tactical_mind"]["enabled"] is True
    assert fighter["fighting_style"]["style_id"] == "archery"
```

- [ ] **Step 2: 跑状态测试确认失败**

Run:

```bash
python3 -m pytest /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_get_encounter_state.py -q -k "patient_defense or step_of_the_wind or tactical_mind or fighting_style"
```

Expected:

- 结果字段缺失

- [ ] **Step 3: 更新投影与 playbook**

```python
projected["monk"]["patient_defense"] = {"enabled": True}
projected["monk"]["step_of_the_wind"] = {"enabled": True}
projected["fighter"]["tactical_mind"] = {"enabled": True}
projected["fighter"]["fighting_style"] = fighter_runtime.get("fighting_style", {})
projected["rogue"]["cunning_strike"] = {
    "enabled": True,
    "max_effects_per_hit": rogue_runtime.get("cunning_strike", {}).get("max_effects_per_hit", 1),
}
```

- [ ] **Step 4: 跑定点状态测试确认通过**

Run:

```bash
python3 -m pytest /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_get_encounter_state.py -q -k "patient_defense or step_of_the_wind or tactical_mind or fighting_style"
```

Expected:

- 相关投影测试通过

- [ ] **Step 5: 跑全量测试**

Run:

```bash
python3 -m unittest discover -s /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test -v
```

Expected:

- `OK`

- [ ] **Step 6: Commit**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  test/test_get_encounter_state.py \
  tools/services/encounter/get_encounter_state.py \
  docs/skill-playbooks/monk.md \
  docs/skill-playbooks/rogue.md \
  docs/skill-playbooks/fighter.md
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "docs: update class feature playbooks and projections"
```

## Self-Review

- Spec coverage:
  - Monk 的 `Patient Defense / Step of the Wind / Slow Fall` 分别覆盖在 Task 1、Task 2。
  - Rogue 的 `Cunning Strike` 全效果覆盖在 Task 3。
  - Fighter 的 `Tactical Mind / Fighting Style` 覆盖在 Task 4、Task 5。
  - 状态投影与 LLM 调用协议覆盖在 Task 6。
- Placeholder scan:
  - 计划中没有 `TODO`、`TBD`、`implement later`。
  - 每个任务都给了明确文件、测试命令、实现骨架和提交命令。
- Type consistency:
  - Monk 主动能力统一使用 `spend_focus`。
  - Rogue 继续使用 `class_feature_options.cunning_strike.effects`。
  - Fighter `fighting_style.style_id` 与 `tactical_mind` 命名保持一致。
