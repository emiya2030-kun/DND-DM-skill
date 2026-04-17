# Barbarian Core Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Barbarian / 野蛮人接入战斗核心能力，包括狂暴状态机、鲁莽攻击、凶蛮打击、危机感应、无甲防御、快速移动、坚韧狂暴等。

**Architecture:** 继续沿用 `entity.class_features["barbarian"]` runtime 模板；主动能力 `use_rage` 做成独立 command，其他被动与半主动能力分别挂入攻击、豁免、检定、先攻、回合开始结束与 HP 更新链；通过 `GetEncounterState` 与 playbook 向 LLM 暴露摘要。

**Tech Stack:** Python 3、unittest/pytest、TinyDB repository、现有 combat runtime services

---

## File Map

- Create: `tools/services/class_features/barbarian/__init__.py`
  - 导出 `UseRage` 与 barbarian runtime helper。
- Create: `tools/services/class_features/barbarian/runtime.py`
  - 维护 barbarian runtime 初始化、等级派生字段、rage 资源等。
- Create: `tools/services/class_features/barbarian/use_rage.py`
  - 进入狂暴 / 延长狂暴 / 莽驰入口。
- Modify: `tools/services/class_features/shared/runtime.py`
  - 注册 barbarian runtime 与通用 `get_class_runtime` 兼容路径。
- Modify: `tools/services/class_features/shared/__init__.py`
  - 导出 barbarian helper。
- Modify: `tools/services/combat/defense/armor_profile_resolver.py`
  - 接入野蛮人无甲防御。
- Modify: `tools/services/combat/attack/attack_roll_request.py`
  - 接入鲁莽攻击、凶蛮打击合法性、原初学识的力量替代、对狂暴攻击的力量判断支持。
- Modify: `tools/services/combat/attack/execute_attack.py`
  - 接入狂暴伤害、凶蛮打击效果、鲁莽攻击状态落点、莽驰后续位移权限。
- Modify: `tools/services/combat/save_spell/saving_throw_request.py`
  - 接入危机感应。
- Modify: `tools/services/combat/save_spell/resolve_saving_throw.py`
  - 接入危机感应、不屈勇武、狂暴中的力量豁免优势。
- Modify: `tools/services/checks/ability_check_request.py`
  - 接入原初学识 ability override 请求字段。
- Modify: `tools/services/checks/resolve_ability_check.py`
  - 接入狂暴中的力量检定优势、原初学识、不屈勇武。
- Modify: `tools/services/encounter/roll_initiative_and_start_encounter.py`
  - 接入野性直觉与持久狂暴先攻恢复。
- Modify: `tools/services/encounter/start_turn.py`
  - 回合开始重置鲁莽攻击状态、应用快速移动。
- Modify: `tools/services/encounter/end_turn.py`
  - 15级前狂暴延长检查与结束。
- Modify: `tools/services/combat/shared/update_hp.py`
  - 接入坚韧狂暴。
- Modify: `tools/services/spells/spell_request.py`
  - 狂暴期间禁止施法。
- Modify: `tools/services/spells/encounter_cast_spell.py`
  - 进入狂暴时打断专注所需的现有行为兼容检查。
- Modify: `tools/services/runtime_dispatcher.py`
  - 注册 `use_rage` command。
- Modify: `tools/services/encounter/get_encounter_state.py`
  - 投影 barbarian runtime 摘要。
- Create: `docs/skill-playbooks/barbarian.md`
  - 记录 LLM 如何调用野蛮人相关能力。

- Test: `test/test_use_rage.py`
- Test: `test/test_armor_profile_resolver.py`
- Test: `test/test_attack_roll_request.py`
- Test: `test/test_execute_attack.py`
- Test: `test/test_resolve_saving_throw.py`
- Test: `test/test_resolve_ability_check.py`
- Test: `test/test_roll_initiative_and_start_encounter.py`
- Test: `test/test_start_turn.py`
- Test: `test/test_end_turn.py`
- Test: `test/test_update_hp.py`
- Test: `test/test_spell_request.py`
- Test: `test/test_runtime_dispatcher.py`
- Test: `test/test_get_encounter_state.py`

### Task 1: Barbarian Runtime 与 `use_rage`

**Files:**
- Create: `tools/services/class_features/barbarian/runtime.py`
- Create: `tools/services/class_features/barbarian/use_rage.py`
- Create: `tools/services/class_features/barbarian/__init__.py`
- Modify: `tools/services/class_features/shared/runtime.py`
- Modify: `tools/services/class_features/shared/__init__.py`
- Test: `test/test_use_rage.py`

- [ ] **Step 1: 写失败测试，锁定 barbarian runtime 初始化**

```python
def test_ensure_barbarian_runtime_derives_rage_and_brutal_strike_from_level() -> None:
    entity = build_barbarian(level=13)
    barbarian = ensure_barbarian_runtime(entity)
    assert barbarian["rage"]["max"] == 5
    assert barbarian["rage_damage_bonus"] == 3
    assert barbarian["weapon_mastery_count"] == 4
    assert barbarian["brutal_strike"]["enabled"] is True
    assert barbarian["brutal_strike"]["extra_damage_dice"] == "1d10"
    assert barbarian["brutal_strike"]["max_effects"] == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run:

```bash
python3 -m pytest /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_use_rage.py -q -k "ensure_barbarian_runtime"
```

Expected:

- `ImportError` 或 `NameError`

- [ ] **Step 3: 写最小 runtime 实现**

```python
def ensure_barbarian_runtime(entity_or_class_features: object) -> dict[str, Any]:
    barbarian = ensure_class_runtime(entity_or_class_features, "barbarian")
    level = int(barbarian.get("level", 0) or 0)
    rage = barbarian.setdefault("rage", {})
    rage["max"] = _resolve_rage_uses(level)
    rage.setdefault("remaining", rage["max"])
    rage.setdefault("active", False)
    rage.setdefault("ends_at_turn_end_of", None)
    rage["persistent_rage"] = level >= 15
    rage.setdefault("restored_on_initiative_this_long_rest", False)
    barbarian["rage_damage_bonus"] = _resolve_rage_damage_bonus(level)
    barbarian["weapon_mastery_count"] = _resolve_weapon_mastery_count(level)
    barbarian.setdefault("danger_sense", {"enabled": level >= 2})
    barbarian.setdefault("reckless_attack", {"enabled": level >= 2, "declared_this_turn": False, "active_until_turn_start_of": None})
    barbarian.setdefault("primal_knowledge", {"enabled": level >= 3})
    barbarian.setdefault("feral_instinct", {"enabled": level >= 7})
    barbarian.setdefault("instinctive_pounce", {"enabled": level >= 7})
    barbarian.setdefault("brutal_strike", {"enabled": level >= 9, "extra_damage_dice": "2d10" if level >= 17 else "1d10", "max_effects": 2 if level >= 17 else 1})
    barbarian.setdefault("relentless_rage", {"enabled": level >= 11, "current_dc": 10})
    barbarian.setdefault("indomitable_might", {"enabled": level >= 18})
    return barbarian
```

- [ ] **Step 4: 写失败测试，覆盖进入狂暴、延长狂暴、莽驰**

```python
def test_use_rage_consumes_bonus_action_and_rage_use() -> None:
    result = UseRage(repo).execute(encounter_id="enc_barbarian_test", entity_id="ent_barbarian_001")
    updated = repo.get("enc_barbarian_test")
    barbarian = updated.entities["ent_barbarian_001"]
    assert barbarian.action_economy["bonus_action_used"] is True
    assert barbarian.class_features["barbarian"]["rage"]["active"] is True
    assert barbarian.class_features["barbarian"]["rage"]["remaining"] == 1
    assert result["class_feature_result"]["rage"]["active"] is True


def test_use_rage_extend_only_refreshes_duration_without_spending_use() -> None:
    encounter = build_barbarian_encounter()
    state = ensure_barbarian_runtime(encounter.entities["ent_barbarian_001"])
    state["rage"]["active"] = True
    repo.save(encounter)
    UseRage(repo).execute(encounter_id="enc_barbarian_test", entity_id="ent_barbarian_001", extend_only=True)
    updated = repo.get("enc_barbarian_test")
    assert updated.entities["ent_barbarian_001"].class_features["barbarian"]["rage"]["remaining"] == 2


def test_use_rage_with_pounce_path_grants_half_speed_free_movement() -> None:
    result = UseRage(repo).execute(
        encounter_id="enc_barbarian_test",
        entity_id="ent_barbarian_001",
        pounce_path=[[3, 2], [4, 2], [5, 2]],
    )
    updated = repo.get("enc_barbarian_test")
    assert updated.entities["ent_barbarian_001"].position == {"x": 5, "y": 2}
    assert result["class_feature_result"]["rage"]["instinctive_pounce_used"] is True
```

- [ ] **Step 5: 跑测试确认失败**

Run:

```bash
python3 -m pytest /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_use_rage.py -q -k "use_rage"
```

Expected:

- `ImportError`、`AttributeError` 或断言失败

- [ ] **Step 6: 写最小 `UseRage` 实现**

```python
class UseRage:
    def execute(
        self,
        *,
        encounter_id: str,
        entity_id: str,
        extend_only: bool = False,
        pounce_path: list[list[int]] | None = None,
    ) -> dict[str, Any]:
        encounter = self.encounter_repository.get(encounter_id)
        actor = self._get_entity_or_raise(encounter, entity_id)
        self._ensure_actor_turn(encounter, entity_id)
        self._ensure_bonus_action_available(actor)
        barbarian = ensure_barbarian_runtime(actor)
        rage = barbarian["rage"]
        if actor.equipped_armor and str(actor.equipped_armor.get("category", "")).lower() == "heavy":
            raise ValueError("rage_blocked_by_heavy_armor")
        if extend_only:
            if not rage.get("active"):
                raise ValueError("rage_not_active")
        else:
            if int(rage.get("remaining", 0)) <= 0:
                raise ValueError("rage_no_remaining_uses")
            rage["remaining"] = int(rage["remaining"]) - 1
            rage["active"] = True
            if actor.is_concentrating:
                actor.is_concentrating = False
        actor.action_economy["bonus_action_used"] = True
        rage["ends_at_turn_end_of"] = actor.entity_id
        if pounce_path:
            self.move_service.execute(
                encounter_id=encounter_id,
                entity_id=entity_id,
                path=[tuple(step) for step in pounce_path],
                free_movement_feet=max(0, int(actor.speed.get("walk", 0) / 2)),
            )
        self.encounter_repository.save(encounter)
        return {"ok": True, "class_feature_result": {"rage": {"active": True, "instinctive_pounce_used": bool(pounce_path)}}}
```

- [ ] **Step 7: 跑测试确认通过**

Run:

```bash
python3 -m pytest /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_use_rage.py -q
```

Expected:

- `4 passed`

- [ ] **Step 8: Commit**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  test/test_use_rage.py \
  tools/services/class_features/barbarian/__init__.py \
  tools/services/class_features/barbarian/runtime.py \
  tools/services/class_features/barbarian/use_rage.py \
  tools/services/class_features/shared/runtime.py \
  tools/services/class_features/shared/__init__.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: add barbarian rage runtime"
```

### Task 2: 无甲防御、危机感应、野性直觉、快速移动

**Files:**
- Modify: `tools/services/combat/defense/armor_profile_resolver.py`
- Modify: `tools/services/combat/save_spell/saving_throw_request.py`
- Modify: `tools/services/encounter/roll_initiative_and_start_encounter.py`
- Modify: `tools/services/encounter/start_turn.py`
- Test: `test/test_armor_profile_resolver.py`
- Test: `test/test_resolve_saving_throw.py`
- Test: `test/test_roll_initiative_and_start_encounter.py`
- Test: `test/test_start_turn.py`

- [ ] **Step 1: 写失败测试，覆盖无甲防御可持盾**

```python
def test_resolve_unarmored_defense_for_barbarian_without_armor_allows_shield() -> None:
    actor = build_actor()
    actor.ability_mods["dex"] = 2
    actor.ability_mods["con"] = 3
    actor.class_features = {"barbarian": {"level": 1}}
    actor.equipped_armor = None
    actor.equipped_shield = {"armor_id": "shield"}
    profile = ArmorProfileResolver().resolve(actor)
    assert profile["ac"] == 17
    assert profile["ac_breakdown"]["base_formula"] == "10+dex+con+shield"
```

- [ ] **Step 2: 跑测试确认失败**

Run:

```bash
python3 -m pytest /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_armor_profile_resolver.py -q -k "barbarian"
```

Expected:

- 断言失败，当前 AC 未按 `10 + DEX + CON + shield`

- [ ] **Step 3: 写最小实现**

```python
def _resolve_barbarian_unarmored_defense(self, actor: EncounterEntity) -> dict[str, Any] | None:
    barbarian = get_class_runtime(actor, "barbarian")
    if not barbarian or actor.equipped_armor is not None:
        return None
    dex_mod = int(actor.ability_mods.get("dex", 0))
    con_mod = int(actor.ability_mods.get("con", 0))
    shield_bonus = 2 if actor.equipped_shield else 0
    return {
        "ac": 10 + dex_mod + con_mod + shield_bonus,
        "ac_breakdown": {"base_formula": "10+dex+con+shield" if shield_bonus else "10+dex+con"},
    }
```

- [ ] **Step 4: 写失败测试，覆盖危机感应、野性直觉、快速移动**

```python
def test_execute_danger_sense_adds_advantage_to_dex_save() -> None:
    request = SavingThrowRequest().execute(..., target_id="ent_barbarian_001", save_ability="dex", ...)
    assert request.context["vantage"] == "advantage"


def test_roll_initiative_uses_advantage_for_feral_instinct() -> None:
    result = RollInitiativeAndStartEncounter(repo).execute("enc_barbarian_test")
    row = next(item for item in result["initiative_results"] if item["entity_id"] == "ent_barbarian_001")
    assert row["vantage"] == "advantage"


def test_start_turn_applies_fast_movement_when_not_in_heavy_armor() -> None:
    updated = StartTurn(repo, event_repo).execute("enc_barbarian_test")
    barbarian = updated.entities["ent_barbarian_001"]
    assert barbarian.speed["walk"] == 40
```

- [ ] **Step 5: 跑测试确认失败**

Run:

```bash
python3 -m pytest \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_resolve_saving_throw.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_roll_initiative_and_start_encounter.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_start_turn.py -q -k "barbarian or danger_sense or feral_instinct or fast_movement"
```

Expected:

- 至少 3 个失败

- [ ] **Step 6: 写最小实现**

```python
# saving_throw_request.py
if save_ability == "dex":
    barbarian = get_class_runtime(target, "barbarian")
    if barbarian and barbarian.get("danger_sense", {}).get("enabled") and not target_is_incapacitated(target):
        vantage_sources["advantage"].append("barbarian_danger_sense")

# roll_initiative_and_start_encounter.py
if barbarian.get("feral_instinct", {}).get("enabled"):
    vantage = "advantage"

# start_turn.py
barbarian = ensure_barbarian_runtime(entity)
if barbarian and not _is_heavy_armor(entity):
    entity.speed["walk"] = int(entity.speed.get("base_walk", entity.speed.get("walk", 0))) + 10
```

- [ ] **Step 7: 跑测试确认通过**

Run:

```bash
python3 -m pytest \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_armor_profile_resolver.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_resolve_saving_throw.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_roll_initiative_and_start_encounter.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_start_turn.py -q -k "barbarian or danger_sense or feral_instinct or fast_movement"
```

Expected:

- 全部通过

- [ ] **Step 8: Commit**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  test/test_armor_profile_resolver.py \
  test/test_resolve_saving_throw.py \
  test/test_roll_initiative_and_start_encounter.py \
  test/test_start_turn.py \
  tools/services/combat/defense/armor_profile_resolver.py \
  tools/services/combat/save_spell/saving_throw_request.py \
  tools/services/encounter/roll_initiative_and_start_encounter.py \
  tools/services/encounter/start_turn.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: add barbarian defense and initiative features"
```

### Task 3: 鲁莽攻击与狂暴伤害

**Files:**
- Modify: `tools/services/combat/attack/attack_roll_request.py`
- Modify: `tools/services/combat/attack/execute_attack.py`
- Test: `test/test_attack_roll_request.py`
- Test: `test/test_execute_attack.py`

- [ ] **Step 1: 写失败测试，覆盖鲁莽攻击请求合法性**

```python
def test_execute_reckless_attack_grants_advantage_on_first_strength_attack() -> None:
    request = AttackRollRequest().execute(
        encounter_id="enc_barbarian_test",
        actor_id="ent_barbarian_001",
        target_id="ent_enemy_001",
        weapon_id="greataxe",
        class_feature_options={"reckless_attack": True},
    )
    assert request.context["vantage"] == "advantage"
    assert "barbarian_reckless_attack" in request.context["vantage_sources"]["advantage"]


def test_execute_rejects_reckless_attack_outside_first_attack_of_turn() -> None:
    encounter.entities["ent_barbarian_001"].class_features["barbarian"]["reckless_attack"]["declared_this_turn"] = True
    with pytest.raises(ValueError, match="reckless_attack_already_declared"):
        AttackRollRequest().execute(...)
```

- [ ] **Step 2: 跑测试确认失败**

Run:

```bash
python3 -m pytest /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_attack_roll_request.py -q -k "reckless_attack"
```

Expected:

- 断言失败或 `ValueError` 未触发

- [ ] **Step 3: 写最小请求层实现**

```python
barbarian = ensure_barbarian_runtime(actor)
reckless = parsed_options.get("reckless_attack")
if reckless:
    if encounter.current_entity_id != actor.entity_id:
        raise ValueError("reckless_attack_requires_current_turn")
    runtime = barbarian.get("reckless_attack", {})
    if runtime.get("declared_this_turn"):
        raise ValueError("reckless_attack_already_declared")
    if chosen_ability != "str":
        raise ValueError("reckless_attack_requires_strength_attack")
    runtime["declared_this_turn"] = True
    vantage_sources["advantage"].append("barbarian_reckless_attack")
```

- [ ] **Step 4: 写失败测试，覆盖狂暴伤害与敌人打你有优势**

```python
def test_execute_applies_rage_damage_bonus_on_strength_hit() -> None:
    result = ExecuteAttack(repo, event_repo).execute(
        encounter_id="enc_barbarian_test",
        actor_id="ent_barbarian_001",
        target_id="ent_enemy_001",
        weapon_id="greataxe",
        attack_roll={"final_total": 21, "base_roll": 15},
        damage_rolls=[{"source": "weapon_damage", "formula": "1d12+4", "total": 10}],
    )
    parts = result["damage_resolution"]["damage_parts"]
    assert any(part["source"] == "barbarian_rage_damage" and part["total"] == 2 for part in parts)


def test_execute_reckless_attack_marks_barbarian_as_easier_to_hit_until_next_turn() -> None:
    ExecuteAttack(... class_feature_options={"reckless_attack": True}, ...)
    updated = repo.get("enc_barbarian_test")
    effects = updated.entities["ent_barbarian_001"].turn_effects
    assert any(effect.get("effect_type") == "barbarian_reckless_defense_penalty" for effect in effects)
```

- [ ] **Step 5: 跑测试确认失败**

Run:

```bash
python3 -m pytest /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_execute_attack.py -q -k "rage_damage or reckless"
```

Expected:

- 至少 2 个失败

- [ ] **Step 6: 写最小实现**

```python
def _maybe_append_barbarian_rage_damage_part(...):
    barbarian = ensure_barbarian_runtime(actor)
    rage = barbarian.get("rage", {})
    if not rage.get("active") or chosen_ability != "str":
        return
    damage_parts.append({
        "source": "barbarian_rage_damage",
        "formula": str(barbarian.get("rage_damage_bonus", 0)),
        "damage_type": base_damage_type,
    })

def _mark_reckless_penalty(...):
    add_or_replace_turn_effect(actor, {
        "effect_type": "barbarian_reckless_defense_penalty",
        "expires_at": {"phase": "start_of_turn", "entity_id": actor.entity_id},
    })
```

- [ ] **Step 7: 跑测试确认通过**

Run:

```bash
python3 -m pytest \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_attack_roll_request.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_execute_attack.py -q -k "reckless or rage_damage"
```

Expected:

- 相关测试全部通过

- [ ] **Step 8: Commit**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  test/test_attack_roll_request.py \
  test/test_execute_attack.py \
  tools/services/combat/attack/attack_roll_request.py \
  tools/services/combat/attack/execute_attack.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: add barbarian reckless attack and rage damage"
```

### Task 4: 凶蛮打击

**Files:**
- Modify: `tools/services/combat/attack/attack_roll_request.py`
- Modify: `tools/services/combat/attack/execute_attack.py`
- Modify: `tools/services/combat/attack/weapon_mastery_effects.py`
- Test: `test/test_attack_roll_request.py`
- Test: `test/test_execute_attack.py`

- [ ] **Step 1: 写失败测试，覆盖凶蛮打击声明合法性**

```python
def test_execute_brutal_strike_requires_reckless_attack_and_advantage() -> None:
    with pytest.raises(ValueError, match="brutal_strike_requires_reckless_attack"):
        AttackRollRequest().execute(
            ...,
            class_feature_options={"brutal_strike": {"effects": ["forceful_blow"]}},
        )
```

- [ ] **Step 2: 跑测试确认失败**

Run:

```bash
python3 -m pytest /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_attack_roll_request.py -q -k "brutal_strike"
```

Expected:

- 失败，当前未校验该规则

- [ ] **Step 3: 写最小请求层实现**

```python
brutal = parsed_options.get("brutal_strike")
if brutal:
    runtime = ensure_barbarian_runtime(actor).get("brutal_strike", {})
    if not runtime.get("enabled"):
        raise ValueError("brutal_strike_not_available")
    if not barbarian["reckless_attack"].get("declared_this_turn"):
        raise ValueError("brutal_strike_requires_reckless_attack")
    if final_vantage != "advantage":
        raise ValueError("brutal_strike_requires_advantage")
    if parsed_disadvantage:
        raise ValueError("brutal_strike_cannot_be_used_with_disadvantage")
```

- [ ] **Step 4: 写失败测试，覆盖四种效果与 17 级双效果**

```python
def test_execute_brutal_strike_forceful_blow_pushes_target_15_feet() -> None:
    result = ExecuteAttack(... class_feature_options={"brutal_strike": {"effects": ["forceful_blow"]}}, ...)
    assert result["class_feature_resolution"]["brutal_strike"]["effects_applied"] == ["forceful_blow"]
    assert result["forced_movement"]["distance_feet"] == 15


def test_execute_brutal_strike_hamstring_blow_applies_speed_penalty() -> None:
    result = ExecuteAttack(... class_feature_options={"brutal_strike": {"effects": ["hamstring_blow"]}}, ...)
    updated = repo.get("enc_barbarian_test")
    target = updated.entities["ent_enemy_001"]
    assert any(effect.get("effect_type") == "barbarian_hamstring_blow" for effect in target.turn_effects)


def test_execute_brutal_strike_level_seventeen_allows_two_effects() -> None:
    result = ExecuteAttack(... class_feature_options={"brutal_strike": {"effects": ["forceful_blow", "sundering_blow"]}}, ...)
    assert result["class_feature_resolution"]["brutal_strike"]["extra_damage_formula"] == "2d10"
    assert result["class_feature_resolution"]["brutal_strike"]["effects_applied"] == ["forceful_blow", "sundering_blow"]
```

- [ ] **Step 5: 跑测试确认失败**

Run:

```bash
python3 -m pytest /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_execute_attack.py -q -k "brutal_strike"
```

Expected:

- 至少 3 个失败

- [ ] **Step 6: 写最小实现**

```python
def _resolve_barbarian_brutal_strike(...):
    runtime = ensure_barbarian_runtime(actor)["brutal_strike"]
    damage_parts.append({
        "source": "barbarian_brutal_strike",
        "formula": runtime["extra_damage_dice"],
        "damage_type": base_damage_type,
    })
    for effect_id in effects:
        if effect_id == "forceful_blow":
            forced = resolve_forced_movement(..., distance_feet=15, ignore_opportunity_attacks=True)
        elif effect_id == "hamstring_blow":
            add_or_replace_turn_effect(target, {"effect_type": "barbarian_hamstring_blow", "speed_penalty_feet": 15, ...})
        elif effect_id == "staggering_blow":
            add_or_replace_turn_effect(target, {"effect_type": "barbarian_staggering_blow", "save_disadvantage": True, "opportunity_attacks_blocked": True, ...})
        elif effect_id == "sundering_blow":
            add_or_replace_turn_effect(target, {"effect_type": "barbarian_sundering_blow", "next_attack_bonus": 5, ...})
```

- [ ] **Step 7: 跑测试确认通过**

Run:

```bash
python3 -m pytest \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_attack_roll_request.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_execute_attack.py -q -k "brutal_strike"
```

Expected:

- 相关测试通过

- [ ] **Step 8: Commit**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  test/test_attack_roll_request.py \
  test/test_execute_attack.py \
  tools/services/combat/attack/attack_roll_request.py \
  tools/services/combat/attack/execute_attack.py \
  tools/services/combat/attack/weapon_mastery_effects.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: add barbarian brutal strike"
```

### Task 5: 原初学识、不屈勇武、狂暴中的力量优势

**Files:**
- Modify: `tools/services/checks/ability_check_request.py`
- Modify: `tools/services/checks/resolve_ability_check.py`
- Modify: `tools/services/combat/save_spell/resolve_saving_throw.py`
- Test: `test/test_resolve_ability_check.py`
- Test: `test/test_resolve_saving_throw.py`

- [ ] **Step 1: 写失败测试，覆盖原初学识改力量**

```python
def test_execute_primal_knowledge_allows_stealth_check_with_strength_while_raging() -> None:
    result = ResolveAbilityCheck().execute(
        encounter=encounter,
        actor=actor,
        check_type="skill",
        check_key="stealth",
        dc=14,
        roll_total=12,
        context={"class_feature_options": {"primal_knowledge": True}},
    )
    assert result["modifier_breakdown"]["ability_used"] == "str"
```

- [ ] **Step 2: 跑测试确认失败**

Run:

```bash
python3 -m pytest /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_resolve_ability_check.py -q -k "primal_knowledge"
```

Expected:

- 断言失败

- [ ] **Step 3: 写最小实现**

```python
if options.get("primal_knowledge"):
    barbarian = ensure_barbarian_runtime(actor)
    allowed = {"acrobatics", "intimidation", "perception", "stealth", "survival"}
    if barbarian.get("rage", {}).get("active") and check_key in allowed:
        ability_key = "str"
```

- [ ] **Step 4: 写失败测试，覆盖力量检定/豁免优势与不屈勇武**

```python
def test_execute_rage_grants_advantage_on_strength_check() -> None:
    result = ResolveAbilityCheck().execute(...)
    assert result["vantage"] == "advantage"


def test_execute_indomitable_might_raises_strength_check_floor() -> None:
    result = ResolveAbilityCheck().execute(...)
    assert result["final_total"] == 20


def test_execute_indomitable_might_raises_strength_save_floor() -> None:
    result = ResolveSavingThrow().execute(...)
    assert result["final_total"] == 20
```

- [ ] **Step 5: 跑测试确认失败**

Run:

```bash
python3 -m pytest \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_resolve_ability_check.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_resolve_saving_throw.py -q -k "barbarian or indomitable_might or strength"
```

Expected:

- 至少 3 个失败

- [ ] **Step 6: 写最小实现**

```python
# resolve_ability_check.py
if ability_key == "str" and barbarian.get("rage", {}).get("active"):
    vantage_sources["advantage"].append("barbarian_rage_strength_advantage")
if ability_key == "str" and barbarian.get("indomitable_might", {}).get("enabled"):
    final_total = max(final_total, actor.abilities["str"])

# resolve_saving_throw.py
if save_ability == "str" and barbarian.get("rage", {}).get("active"):
    vantage_sources["advantage"].append("barbarian_rage_strength_save_advantage")
if save_ability == "str" and barbarian.get("indomitable_might", {}).get("enabled"):
    final_total = max(final_total, actor.abilities["str"])
```

- [ ] **Step 7: 跑测试确认通过**

Run:

```bash
python3 -m pytest \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_resolve_ability_check.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_resolve_saving_throw.py -q -k "barbarian or indomitable_might or strength"
```

Expected:

- 相关测试通过

- [ ] **Step 8: Commit**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  test/test_resolve_ability_check.py \
  test/test_resolve_saving_throw.py \
  tools/services/checks/ability_check_request.py \
  tools/services/checks/resolve_ability_check.py \
  tools/services/combat/save_spell/resolve_saving_throw.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: add barbarian checks and save features"
```

### Task 6: 狂暴结束检查、持久狂暴、坚韧狂暴、施法限制

**Files:**
- Modify: `tools/services/encounter/end_turn.py`
- Modify: `tools/services/combat/shared/update_hp.py`
- Modify: `tools/services/spells/spell_request.py`
- Modify: `tools/services/encounter/roll_initiative_and_start_encounter.py`
- Test: `test/test_end_turn.py`
- Test: `test/test_update_hp.py`
- Test: `test/test_spell_request.py`
- Test: `test/test_roll_initiative_and_start_encounter.py`

- [ ] **Step 1: 写失败测试，覆盖回合结束狂暴延长与结束**

```python
def test_execute_keeps_rage_when_barbarian_attacked_this_turn() -> None:
    encounter.entities["ent_barbarian_001"].class_features["barbarian"]["rage"]["active"] = True
    encounter.entities["ent_barbarian_001"].combat_flags["rage_extended_by_attack_this_turn"] = True
    EndTurn(repo, event_repo).execute("enc_barbarian_test")
    updated = repo.get("enc_barbarian_test")
    assert updated.entities["ent_barbarian_001"].class_features["barbarian"]["rage"]["active"] is True


def test_execute_ends_rage_when_no_extension_condition_met() -> None:
    encounter.entities["ent_barbarian_001"].class_features["barbarian"]["rage"]["active"] = True
    EndTurn(repo, event_repo).execute("enc_barbarian_test")
    updated = repo.get("enc_barbarian_test")
    assert updated.entities["ent_barbarian_001"].class_features["barbarian"]["rage"]["active"] is False
```

- [ ] **Step 2: 跑测试确认失败**

Run:

```bash
python3 -m pytest /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_end_turn.py -q -k "rage"
```

Expected:

- 断言失败

- [ ] **Step 3: 写最小回合结束实现**

```python
def _maybe_resolve_barbarian_rage_timeout(entity: EncounterEntity) -> None:
    barbarian = ensure_barbarian_runtime(entity)
    rage = barbarian.get("rage", {})
    if not rage.get("active"):
        return
    if rage.get("persistent_rage"):
        return
    if _is_heavy_armor(entity) or entity_has_condition(entity, "incapacitated"):
        rage["active"] = False
        return
    if entity.combat_flags.get("rage_extended_by_attack_this_turn") or entity.combat_flags.get("rage_extended_by_forced_save_this_turn"):
        rage["ends_at_turn_end_of"] = entity.entity_id
        return
    rage["active"] = False
```

- [ ] **Step 4: 写失败测试，覆盖坚韧狂暴、持久狂暴、狂暴期间禁施法**

```python
def test_execute_relentless_rage_success_sets_hp_to_double_barbarian_level() -> None:
    result = UpdateHp(repo, event_repo).execute(
        encounter_id="enc_barbarian_test",
        target_id="ent_barbarian_001",
        hp_change=50,
        damage_type="slashing",
    )
    updated = repo.get("enc_barbarian_test")
    assert updated.entities["ent_barbarian_001"].hp["current"] == 22
    assert result["hp_resolution"]["class_feature_resolution"]["relentless_rage"]["triggered"] is True


def test_execute_persistent_rage_restores_rage_uses_on_initiative_once_per_long_rest() -> None:
    result = RollInitiativeAndStartEncounter(repo).execute("enc_barbarian_test")
    row = next(item for item in result["initiative_results"] if item["entity_id"] == "ent_barbarian_001")
    assert row["class_feature_resolution"]["persistent_rage"]["restored"] is True


def test_execute_rejects_spellcasting_while_raging() -> None:
    with pytest.raises(ValueError, match="cannot_cast_spells_while_raging"):
        SpellRequest(repo).execute(... actor_id="ent_barbarian_001", spell_id="healing_word", ...)
```

- [ ] **Step 5: 跑测试确认失败**

Run:

```bash
python3 -m pytest \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_update_hp.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_roll_initiative_and_start_encounter.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_spell_request.py -q -k "barbarian or relentless_rage or persistent_rage or raging"
```

Expected:

- 至少 3 个失败

- [ ] **Step 6: 写最小实现**

```python
# update_hp.py
if target.hp["current"] <= 0 and barbarian["rage"]["active"] and barbarian["relentless_rage"]["enabled"]:
    save_total = ResolveSavingThrow().execute(... save_ability="con", auto_roll=True)["final_total"]
    if save_total >= barbarian["relentless_rage"]["current_dc"]:
        target.hp["current"] = barbarian["level"] * 2
        barbarian["relentless_rage"]["current_dc"] += 5
        return result

# spell_request.py
barbarian = get_class_runtime(actor, "barbarian")
if barbarian and barbarian.get("rage", {}).get("active"):
    raise ValueError("cannot_cast_spells_while_raging")

# roll_initiative_and_start_encounter.py
if barbarian["rage"]["persistent_rage"] and not barbarian["rage"]["restored_on_initiative_this_long_rest"]:
    barbarian["rage"]["remaining"] = barbarian["rage"]["max"]
    barbarian["rage"]["restored_on_initiative_this_long_rest"] = True
```

- [ ] **Step 7: 跑测试确认通过**

Run:

```bash
python3 -m pytest \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_end_turn.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_update_hp.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_roll_initiative_and_start_encounter.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_spell_request.py -q -k "barbarian or rage or relentless_rage or persistent_rage or raging"
```

Expected:

- 相关测试通过

- [ ] **Step 8: Commit**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  test/test_end_turn.py \
  test/test_update_hp.py \
  test/test_roll_initiative_and_start_encounter.py \
  test/test_spell_request.py \
  tools/services/encounter/end_turn.py \
  tools/services/combat/shared/update_hp.py \
  tools/services/spells/spell_request.py \
  tools/services/encounter/roll_initiative_and_start_encounter.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: add barbarian rage lifecycle and relentless rage"
```

### Task 7: Runtime command、状态投影与 playbook

**Files:**
- Modify: `tools/services/runtime_dispatcher.py`
- Modify: `tools/services/encounter/get_encounter_state.py`
- Create: `docs/skill-playbooks/barbarian.md`
- Test: `test/test_runtime_dispatcher.py`
- Test: `test/test_get_encounter_state.py`

- [ ] **Step 1: 写失败测试，覆盖 runtime command 注册**

```python
def test_command_handlers_include_use_rage() -> None:
    dispatcher = build_dispatcher()
    assert "use_rage" in dispatcher.command_handlers
```

- [ ] **Step 2: 跑测试确认失败**

Run:

```bash
python3 -m pytest /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_runtime_dispatcher.py -q -k "use_rage"
```

Expected:

- 断言失败

- [ ] **Step 3: 写最小 command 注册**

```python
command_handlers["use_rage"] = lambda **kwargs: UseRage(encounter_repository, move_service).execute(
    encounter_id=kwargs["encounter_id"],
    entity_id=kwargs["entity_id"],
    extend_only=bool(kwargs.get("extend_only", False)),
    pounce_path=kwargs.get("pounce_path"),
)
```

- [ ] **Step 4: 写失败测试，覆盖状态投影**

```python
def test_execute_projects_barbarian_runtime_resources() -> None:
    player.class_features["barbarian"] = {"level": 15, "rage": {"remaining": 4, "max": 5, "active": True}}
    state = GetEncounterState(repo, event_repo).execute("enc_view_test")
    barbarian = state["current_turn_entity"]["resources"]["class_features"]["barbarian"]
    assert barbarian["rage"]["active"] is True
    assert barbarian["rage"]["remaining"] == 4
    assert "rage" in barbarian["available_features"]
    assert "reckless_attack" in barbarian["available_features"]
    assert "persistent_rage" in barbarian["available_features"]
```

- [ ] **Step 5: 跑测试确认失败**

Run:

```bash
python3 -m pytest /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_get_encounter_state.py -q -k "barbarian"
```

Expected:

- 断言失败

- [ ] **Step 6: 写最小投影与 playbook**

```python
# get_encounter_state.py
CLASS_FEATURE_VIEW_CONFIG["barbarian"] = {
    "fields": ["level", "rage", "rage_damage_bonus", "reckless_attack", "brutal_strike", "relentless_rage"],
    "available_features": ["rage", "reckless_attack", "danger_sense", "brutal_strike", "relentless_rage", "persistent_rage", "indomitable_might"],
}
```

```markdown
# Barbarian

## 进入狂暴
```json
{
  "command": "use_rage",
  "args": {
    "encounter_id": "enc_preview_demo",
    "entity_id": "pc_barbarian"
  }
}
```

## 鲁莽攻击
在 `execute_attack` 的 `class_feature_options` 中声明：

```json
{
  "reckless_attack": true
}
```
```

- [ ] **Step 7: 跑测试确认通过**

Run:

```bash
python3 -m pytest \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_runtime_dispatcher.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_get_encounter_state.py -q -k "use_rage or barbarian"
```

Expected:

- 相关测试通过

- [ ] **Step 8: Commit**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  test/test_runtime_dispatcher.py \
  test/test_get_encounter_state.py \
  tools/services/runtime_dispatcher.py \
  tools/services/encounter/get_encounter_state.py \
  docs/skill-playbooks/barbarian.md
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "docs: expose barbarian runtime and playbook"
```

### Task 8: 全量验证与收尾

**Files:**
- Modify: `docs/development-plan.md`
  - 仅在需要同步总体进度时更新。

- [ ] **Step 1: 跑野蛮人相关定点测试**

Run:

```bash
python3 -m pytest \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_use_rage.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_armor_profile_resolver.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_attack_roll_request.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_execute_attack.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_resolve_saving_throw.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_resolve_ability_check.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_roll_initiative_and_start_encounter.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_end_turn.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_update_hp.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_spell_request.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_runtime_dispatcher.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_get_encounter_state.py -q -k "barbarian or use_rage or reckless_attack or brutal_strike or relentless_rage or persistent_rage"
```

Expected:

- 所有野蛮人相关测试通过

- [ ] **Step 2: 跑全量测试**

Run:

```bash
python3 -m unittest discover -s test -v
```

Expected:

- `OK`

- [ ] **Step 3: 最终提交**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system status --short
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add -A
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: add barbarian core combat features"
```

## Self-Review

- Spec coverage:
  - `Rage / 无甲防御 / Weapon Mastery / Danger Sense / Reckless Attack / Primal Knowledge / Extra Attack / Fast Movement / Feral Instinct / Instinctive Pounce / Brutal Strike / Relentless Rage / Persistent Rage / Indomitable Might` 都有对应任务。
  - `Weapon Mastery` 本轮通过 runtime 初始化与既有精通模板接入，不单独拆任务；实现时若现有模板缺口暴露，应在 Task 1 或 Task 3 中一并补测试。
- Placeholder scan:
  - 无 `TBD / TODO / implement later`。
- Type consistency:
  - 新 command 统一使用 `entity_id`。
  - 既有攻击与检定链仍沿用 `actor_id`，在 runtime command 内部映射。
