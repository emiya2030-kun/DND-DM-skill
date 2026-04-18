# Metamagic Batch 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为术士补上第一批可战斗落地的超魔法：`Quickened Spell / 瞬发法术`、`Distant Spell / 远程法术`、`Heightened Spell / 升阶法术`、`Careful Spell / 谨慎法术`，并继续复用现有 `metamagic_options` 主链。

**Architecture:** 继续沿现有施法主链分点接入。`SpellRequest` 负责解析和校验超魔声明，`EncounterCastSpell` 负责资源与动作经济，`SavingThrowRequest / ResolveSavingThrow / SavingThrowResult` 负责豁免相关超魔，射程校验继续挂在 `SpellRequest` 的目标校验路径。单次施法只允许一个超魔，不引入新的独立超魔 service。

**Tech Stack:** Python, pytest, `SpellRequest`, `EncounterCastSpell`, `ExecuteSaveSpell`, `SavingThrowRequest`, `ResolveSavingThrow`, `SavingThrowResult`, 术士 runtime helper。

---

## File Map

- Modify: `trpg-battle-system/tools/services/spells/spell_request.py`
  - 扩展 `metamagic_options` 的通用解析
  - 处理 `Quickened / Distant / Heightened / Careful / Subtle`
  - 做声明期校验与结构化 `metamagic` 返回
- Modify: `trpg-battle-system/tools/services/spells/encounter_cast_spell.py`
  - 接收结构化超魔
  - 扣术法点
  - 改写 `Quickened` 的动作经济
  - 记录“本回合是否已施放过一环或更高法术”
- Modify: `trpg-battle-system/tools/services/combat/save_spell/execute_save_spell.py`
  - 透传 `metamagic_options`
  - 让施法声明与豁免链共享同一份超魔上下文
- Modify: `trpg-battle-system/tools/services/combat/save_spell/saving_throw_request.py`
  - 读取 `Heightened` / `Careful`
  - 生成带劣势或自动成功的豁免请求上下文
- Modify: `trpg-battle-system/tools/services/combat/save_spell/resolve_saving_throw.py`
  - 支持自动成功的豁免短路
- Modify: `trpg-battle-system/tools/services/combat/save_spell/saving_throw_result.py`
  - 支持 `Careful` 的“成功豁免半伤改 0”
- Modify: `trpg-battle-system/test/test_spell_request.py`
  - 覆盖声明期校验与结构化返回
- Modify: `trpg-battle-system/test/test_encounter_cast_spell.py`
  - 覆盖 `Quickened` 资源/动作经济/回滚
- Modify: `trpg-battle-system/test/test_execute_save_spell.py`
  - 覆盖 `Heightened` / `Careful` 的主链行为
- Modify: `trpg-battle-system/test/test_saving_throw_request.py`
  - 覆盖豁免请求的超魔上下文注入
- Modify: `trpg-battle-system/test/test_saving_throw_result.py`
  - 覆盖 `Careful` 半伤改零
- Modify: `trpg-battle-system/docs/llm-runtime-tool-guide.md`
- Modify: `trpg-battle-system/docs/development-plan.md`

### Task 1: 扩展 `SpellRequest` 的通用超魔声明与校验

**Files:**
- Modify: `trpg-battle-system/tools/services/spells/spell_request.py`
- Modify: `trpg-battle-system/test/test_spell_request.py`

- [ ] **Step 1: 先写失败测试，锁定这批超魔的声明期行为**

```python
def test_execute_rejects_multiple_metamagic_selection(self) -> None:
    result = service.execute(
        encounter_id="enc_spell_request_test",
        actor_id="ent_caster_001",
        spell_id="chromatic_orb",
        cast_level=1,
        target_entity_ids=["ent_target_humanoid_001"],
        metamagic_options={"selected": ["subtle_spell", "quickened_spell"]},
    )

    self.assertFalse(result["ok"])
    self.assertEqual(result["error_code"], "multiple_metamagic_not_supported")
```

```python
def test_execute_accepts_quickened_spell_and_returns_cost(self) -> None:
    result = service.execute(
        encounter_id="enc_spell_request_test",
        actor_id="ent_caster_001",
        spell_id="chromatic_orb",
        cast_level=1,
        target_entity_ids=["ent_target_humanoid_001"],
        metamagic_options={"selected": ["quickened_spell"]},
    )

    self.assertTrue(result["ok"])
    self.assertTrue(result["metamagic"]["quickened_spell"])
    self.assertEqual(result["metamagic"]["sorcery_point_cost"], 2)
```

```python
def test_execute_accepts_distant_spell_for_touch_spell(self) -> None:
    result = service.execute(
        encounter_id="enc_spell_request_test",
        actor_id="ent_caster_001",
        spell_id="shocking_grasp",
        cast_level=0,
        target_entity_ids=["ent_target_humanoid_001"],
        metamagic_options={"selected": ["distant_spell"]},
    )

    self.assertTrue(result["ok"])
    self.assertTrue(result["metamagic"]["distant_spell"])
```

```python
def test_execute_rejects_heightened_spell_without_target_id(self) -> None:
    result = service.execute(
        encounter_id="enc_spell_request_test",
        actor_id="ent_caster_001",
        spell_id="hold_person",
        cast_level=2,
        target_entity_ids=["ent_target_humanoid_001"],
        metamagic_options={"selected": ["heightened_spell"]},
    )

    self.assertFalse(result["ok"])
    self.assertEqual(result["error_code"], "heightened_spell_requires_target")
```

```python
def test_execute_rejects_careful_spell_when_targets_exceed_cha_mod(self) -> None:
    result = service.execute(
        encounter_id="enc_spell_request_test",
        actor_id="ent_caster_001",
        spell_id="burning_hands",
        cast_level=1,
        target_entity_ids=["ent_target_humanoid_001", "ent_target_wolf_001"],
        metamagic_options={
            "selected": ["careful_spell"],
            "careful_target_ids": ["ent_target_humanoid_001", "ent_target_wolf_001", "ent_extra_001"],
        },
    )

    self.assertFalse(result["ok"])
    self.assertEqual(result["error_code"], "careful_spell_too_many_targets")
```

Run: `python3 -m pytest -q trpg-battle-system/test/test_spell_request.py -k "metamagic or quickened or distant or heightened or careful"`
Expected: FAIL，原因应为当前只支持 `subtle_spell`。

- [ ] **Step 2: 在 `SpellRequest` 中把 `metamagic` 结构扩成通用字典**

```python
def _build_default_metamagic(self) -> dict[str, Any]:
    return {
        "selected": [],
        "subtle_spell": False,
        "quickened_spell": False,
        "distant_spell": False,
        "heightened_spell": False,
        "careful_spell": False,
        "sorcery_point_cost": 0,
        "heightened_target_id": None,
        "careful_target_ids": [],
    }
```

```python
def _build_default_noticeability(self) -> dict[str, Any]:
    return {
        "casting_is_perceptible": True,
        "verbal_visible": True,
        "somatic_visible": True,
        "material_visible": True,
        "spell_effect_visible": True,
    }
```

- [ ] **Step 3: 实现 `metamagic_options` 通用解析与单超魔限制**

```python
selected = metamagic_options.get("selected")
if not isinstance(selected, list):
    return default_result

normalized_selected = [str(item).strip().lower() for item in selected if str(item).strip()]
if len(normalized_selected) > 1:
    return {
        "ok": False,
        "error_code": "multiple_metamagic_not_supported",
        "message": "当前一次施法只支持声明一种超魔法",
    }
```

```python
supported = {
    "subtle_spell": 1,
    "quickened_spell": 2,
    "distant_spell": 1,
    "heightened_spell": 2,
    "careful_spell": 1,
}
```

- [ ] **Step 4: 为每个超魔补声明期校验**

```python
if selected_metamagic == "quickened_spell" and action_cost != "action":
    return {
        "ok": False,
        "error_code": "quickened_spell_requires_action_cast_time",
        "message": "瞬发法术只能作用于施法时间为动作的法术",
    }
```

```python
if selected_metamagic == "distant_spell" and not self._spell_can_use_distant_spell(spell_definition):
    return {
        "ok": False,
        "error_code": "distant_spell_requires_range_or_touch_spell",
        "message": "远程法术只能用于具有射程或触碰距离的法术",
    }
```

```python
if selected_metamagic == "heightened_spell":
    heightened_target_id = metamagic_options.get("heightened_target_id")
    if not isinstance(heightened_target_id, str) or not heightened_target_id.strip():
        return {
            "ok": False,
            "error_code": "heightened_spell_requires_target",
            "message": "升阶法术需要指定一个吃劣势的目标",
        }
```

```python
if selected_metamagic == "careful_spell":
    careful_target_ids = metamagic_options.get("careful_target_ids")
    if not isinstance(careful_target_ids, list) or not careful_target_ids:
        return {
            "ok": False,
            "error_code": "careful_spell_requires_targets",
            "message": "谨慎法术需要提供被保护目标列表",
        }
```

- [ ] **Step 5: 让 `Distant Spell` 的结果进入返回结构，为后续射程校验做准备**

```python
metamagic_result["distant_spell"] = True
metamagic_result["effective_range_override_feet"] = self._resolve_distant_spell_range_override(
    spell_definition=spell_definition
)
```

```python
return {
    "ok": True,
    # ...
    "metamagic": metamagic_summary,
    "noticeability": noticeability,
}
```

- [ ] **Step 6: 跑定向测试转绿**

Run: `python3 -m pytest -q trpg-battle-system/test/test_spell_request.py -k "metamagic or quickened or distant or heightened or careful"`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add \
  trpg-battle-system/tools/services/spells/spell_request.py \
  trpg-battle-system/test/test_spell_request.py
git commit -m "feat: add metamagic batch 1 request parsing"
```

### Task 2: 在 `EncounterCastSpell` 中落地 `Quickened Spell` 与统一资源扣除

**Files:**
- Modify: `trpg-battle-system/tools/services/spells/encounter_cast_spell.py`
- Modify: `trpg-battle-system/test/test_encounter_cast_spell.py`

- [ ] **Step 1: 先写失败测试，锁定 `Quickened` 的动作经济与回滚**

```python
def test_execute_quickened_spell_uses_bonus_action_and_spends_two_sorcery_points(self) -> None:
    result = service.execute(
        encounter_id="enc_cast_spell_test",
        spell_id="chromatic_orb",
        cast_level=1,
        target_ids=["ent_enemy_iron_duster_001"],
        metamagic_options={"selected": ["quickened_spell"]},
    )

    updated = encounter_repo.get("enc_cast_spell_test")
    self.assertEqual(result["action_cost"], "bonus_action")
    self.assertEqual(result["metamagic"]["sorcery_point_cost"], 2)
    self.assertEqual(updated.entities["ent_ally_eric_001"].class_features["sorcerer"]["sorcery_points"]["current"], 1)
```

```python
def test_execute_quickened_spell_rejects_second_leveled_spell_same_turn(self) -> None:
    caster = encounter.entities["ent_ally_eric_001"]
    caster.class_features["sorcerer"] = {
        "level": 5,
        "sorcery_points": {"max": 5, "current": 5},
        "metamagic": {"leveled_spell_cast_this_turn": True},
    }

    with self.assertRaisesRegex(ValueError, "quickened_spell_conflicts_with_same_turn_leveled_spell"):
        service.execute(
            encounter_id="enc_cast_spell_test",
            spell_id="chromatic_orb",
            cast_level=1,
            target_ids=["ent_enemy_iron_duster_001"],
            metamagic_options={"selected": ["quickened_spell"]},
        )
```

```python
def test_execute_quickened_spell_restores_two_sorcery_points_when_append_event_fails(self) -> None:
    with patch.object(service.append_event, "execute", side_effect=RuntimeError("append_failed")):
        with self.assertRaisesRegex(RuntimeError, "append_failed"):
            service.execute(
                encounter_id="enc_cast_spell_test",
                spell_id="chromatic_orb",
                cast_level=1,
                target_ids=["ent_enemy_iron_duster_001"],
                metamagic_options={"selected": ["quickened_spell"]},
            )
```

Run: `python3 -m pytest -q trpg-battle-system/test/test_encounter_cast_spell.py -k "quickened_spell or sorcery_points"`
Expected: FAIL，因为当前没有 `Quickened` 的动作规则与同回合法术限制。

- [ ] **Step 2: 从 `SpellRequest` 读取通用 `metamagic`，不要在 `EncounterCastSpell` 再各自猜规则**

```python
spell_request = SpellRequest(self.encounter_repository, self.spell_definition_repository).execute(
    encounter_id=encounter_id,
    actor_id=caster.entity_id,
    spell_id=spell_id,
    cast_level=resolved_cast_level,
    target_entity_ids=resolved_target_ids,
    target_point=target_point,
    declared_action_cost=action_cost,
    metamagic_options=metamagic_options,
    allow_out_of_turn_actor=allow_out_of_turn_actor,
)
```

```python
if not spell_request["ok"]:
    raise ValueError(spell_request["error_code"])
```

- [ ] **Step 3: 用结构化 `metamagic` 改写动作经济，并统一扣术法点**

```python
metamagic = dict(spell_request["metamagic"])
action_cost = "bonus_action" if metamagic.get("quickened_spell") else action_cost
```

```python
sorcery_points_consumed = self._consume_sorcery_points_if_needed(
    caster=caster,
    metamagic=metamagic,
)
```

- [ ] **Step 4: 为“本回合是否已施放过一环或更高法术”补运行态标记**

```python
sorcerer = ensure_sorcerer_runtime(caster)
metamagic_runtime = sorcerer.setdefault("metamagic", {})
if spell_level > 0:
    if metamagic.get("quickened_spell") and bool(metamagic_runtime.get("leveled_spell_cast_this_turn")):
        raise ValueError("quickened_spell_conflicts_with_same_turn_leveled_spell")
```

```python
if resolved_cast_level > 0:
    metamagic_runtime["leveled_spell_cast_this_turn"] = True
```

- [ ] **Step 5: 确保失败回滚包括术法点和动作经济标记**

```python
except Exception:
    self._rollback_spell_slot_if_needed(caster, slot_consumed)
    self._restore_sorcery_points_if_needed(caster=caster, sorcery_points_consumed=sorcery_points_consumed)
    caster.action_economy = previous_action_economy
    self._restore_metamagic_turn_flags_if_needed(caster=caster, previous_metamagic_runtime=previous_metamagic_runtime)
    self.encounter_repository.save(encounter)
    raise
```

- [ ] **Step 6: 跑定向测试转绿**

Run: `python3 -m pytest -q trpg-battle-system/test/test_encounter_cast_spell.py -k "quickened_spell or sorcery_points"`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add \
  trpg-battle-system/tools/services/spells/encounter_cast_spell.py \
  trpg-battle-system/test/test_encounter_cast_spell.py
git commit -m "feat: add quickened spell cast flow"
```

### Task 3: 在声明期和施法期接入 `Distant Spell`

**Files:**
- Modify: `trpg-battle-system/tools/services/spells/spell_request.py`
- Modify: `trpg-battle-system/test/test_spell_request.py`

- [ ] **Step 1: 写失败测试，锁定触碰法术和普通射程翻倍**

```python
def test_execute_distant_spell_allows_touch_spell_at_thirty_feet(self) -> None:
    result = service.execute(
        encounter_id="enc_spell_request_test",
        actor_id="ent_caster_001",
        spell_id="shocking_grasp",
        cast_level=0,
        target_entity_ids=["ent_target_humanoid_001"],
        metamagic_options={"selected": ["distant_spell"]},
    )

    self.assertTrue(result["ok"])
```

```python
def test_execute_distant_spell_doubles_ranged_spell_limit(self) -> None:
    result = service.execute(
        encounter_id="enc_spell_request_test",
        actor_id="ent_caster_001",
        spell_id="ray_of_frost",
        cast_level=0,
        target_entity_ids=["ent_target_humanoid_001"],
        metamagic_options={"selected": ["distant_spell"]},
    )

    self.assertTrue(result["ok"])
```

Run: `python3 -m pytest -q trpg-battle-system/test/test_spell_request.py -k distant_spell`
Expected: FAIL，原因应为当前射程校验未读取 `effective_range_override_feet`。

- [ ] **Step 2: 在 `SpellRequest` 的射程校验中读取超魔改写**

```python
effective_range_feet = self._resolve_effective_range_feet(
    spell_definition=spell_definition,
    metamagic=metamagic_summary,
)
```

```python
if metamagic.get("distant_spell") and isinstance(base_range_feet, int) and base_range_feet >= 5:
    return base_range_feet * 2
if metamagic.get("distant_spell") and spell_range_kind == "touch":
    return 30
```

- [ ] **Step 3: 把计算后的有效射程写回返回结果，便于 LLM 与后续链路复用**

```python
result["metamagic"]["effective_range_override_feet"] = effective_range_feet
```

- [ ] **Step 4: 跑定向测试转绿**

Run: `python3 -m pytest -q trpg-battle-system/test/test_spell_request.py -k distant_spell`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add \
  trpg-battle-system/tools/services/spells/spell_request.py \
  trpg-battle-system/test/test_spell_request.py
git commit -m "feat: add distant spell range overrides"
```

### Task 4: 在豁免链接入 `Heightened Spell` 与 `Careful Spell`

**Files:**
- Modify: `trpg-battle-system/tools/services/combat/save_spell/execute_save_spell.py`
- Modify: `trpg-battle-system/tools/services/combat/save_spell/saving_throw_request.py`
- Modify: `trpg-battle-system/tools/services/combat/save_spell/resolve_saving_throw.py`
- Modify: `trpg-battle-system/tools/services/combat/save_spell/saving_throw_result.py`
- Modify: `trpg-battle-system/test/test_execute_save_spell.py`
- Modify: `trpg-battle-system/test/test_saving_throw_request.py`
- Modify: `trpg-battle-system/test/test_saving_throw_result.py`

- [ ] **Step 1: 先写失败测试，锁定豁免劣势、自动成功和半伤改零**

```python
def test_execute_save_spell_heightened_spell_sets_disadvantage_for_selected_target(self) -> None:
    result = service.execute(
        encounter_id="enc_save_spell_test",
        target_id="ent_target_001",
        spell_id="hold_person",
        base_rolls=[17, 4],
        cast_level=2,
        metamagic_options={
            "selected": ["heightened_spell"],
            "heightened_target_id": "ent_target_001",
        },
    )

    self.assertEqual(result["roll_result"]["metadata"]["vantage"], "disadvantage")
    self.assertEqual(result["roll_result"]["dice_rolls"]["chosen_roll"], 4)
```

```python
def test_execute_save_spell_careful_spell_marks_protected_target_auto_success(self) -> None:
    result = service.execute(
        encounter_id="enc_save_spell_test",
        target_id="ent_target_001",
        spell_id="burning_hands",
        base_roll=2,
        cast_level=1,
        damage_rolls=[{"formula": "3d6", "total": 9, "damage_type": "fire"}],
        metamagic_options={
            "selected": ["careful_spell"],
            "careful_target_ids": ["ent_target_001"],
        },
    )

    self.assertTrue(result["resolution"]["success"])
```

```python
def test_saving_throw_result_careful_spell_turns_half_damage_into_zero(self) -> None:
    self.assertEqual(result["damage_resolution"]["total_damage"], 0)
```

Run: `python3 -m pytest -q trpg-battle-system/test/test_execute_save_spell.py trpg-battle-system/test/test_saving_throw_request.py trpg-battle-system/test/test_saving_throw_result.py -k "heightened or careful"`
Expected: FAIL，因为当前豁免链还没读取超魔上下文。

- [ ] **Step 2: 让 `ExecuteSaveSpell` 透传 `metamagic_options` 到施法声明和豁免请求**

```python
cast = self.encounter_cast_spell.execute(
    encounter_id=encounter_id,
    spell_id=spell_id,
    target_ids=[target_id],
    cast_level=cast_level,
    reason=description,
    metamagic_options=metamagic_options,
)
```

```python
request = self.saving_throw_request.execute(
    encounter_id=encounter_id,
    target_id=target_id,
    spell_id=spell_id,
    vantage=vantage,
    description=description,
    metamagic=cast.get("metamagic"),
)
```

- [ ] **Step 3: 在 `SavingThrowRequest` 中把 `Heightened` 和 `Careful` 转成请求上下文**

```python
if metamagic.get("heightened_spell") and target.entity_id == metamagic.get("heightened_target_id"):
    normalized_vantage = "disadvantage"
    vantage_sources["disadvantage"].append("heightened_spell")
```

```python
auto_success = bool(
    metamagic.get("careful_spell") and target.entity_id in set(metamagic.get("careful_target_ids", []))
)
```

```python
"metamagic": metamagic,
"auto_success": auto_success,
```

- [ ] **Step 4: 在 `ResolveSavingThrow` 中支持自动成功短路**

```python
auto_success = bool(roll_request.context.get("auto_success"))
if auto_success:
    chosen_roll = max(normalized_rolls)
    final_total = max(save_dc, chosen_roll + save_bonus)
```

```python
result_metadata["auto_success"] = auto_success
```

- [ ] **Step 5: 在 `SavingThrowResult` 中处理 `Careful` 的半伤改零**

```python
if self._careful_spell_zero_damage_applies(
    roll_request=roll_request,
    success=success,
    damage_resolution=damage_resolution,
):
    damage_resolution = dict(damage_resolution)
    damage_resolution["total_damage"] = 0
    damage_resolution["careful_spell_zero_damage"] = True
```

```python
def _careful_spell_zero_damage_applies(...):
    metamagic = roll_request.context.get("metamagic")
    return bool(
        success
        and isinstance(metamagic, dict)
        and metamagic.get("careful_spell")
        and roll_request.context.get("auto_success")
        and damage_resolution.get("total_damage", 0) > 0
    )
```

- [ ] **Step 6: 跑定向测试转绿**

Run: `python3 -m pytest -q trpg-battle-system/test/test_execute_save_spell.py trpg-battle-system/test/test_saving_throw_request.py trpg-battle-system/test/test_saving_throw_result.py -k "heightened or careful"`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add \
  trpg-battle-system/tools/services/combat/save_spell/execute_save_spell.py \
  trpg-battle-system/tools/services/combat/save_spell/saving_throw_request.py \
  trpg-battle-system/tools/services/combat/save_spell/resolve_saving_throw.py \
  trpg-battle-system/tools/services/combat/save_spell/saving_throw_result.py \
  trpg-battle-system/test/test_execute_save_spell.py \
  trpg-battle-system/test/test_saving_throw_request.py \
  trpg-battle-system/test/test_saving_throw_result.py
git commit -m "feat: add heightened and careful spell save flow"
```

### Task 5: 更新 LLM 文档并做回归验证

**Files:**
- Modify: `trpg-battle-system/docs/llm-runtime-tool-guide.md`
- Modify: `trpg-battle-system/docs/development-plan.md`

- [ ] **Step 1: 更新 LLM 文档，写清新的 `metamagic_options` 格式与限制**

```md
- `Quickened Spell / 瞬发法术`
  - 通过 `EncounterCastSpell(..., metamagic_options={"selected": ["quickened_spell"]})`
  - 消耗 2 点术法点
  - 本次施法改为附赠动作
  - 本回合不能和另一道 1 环或更高法术并用
```

```md
- `Distant Spell / 远程法术`
  - 通过 `metamagic_options={"selected": ["distant_spell"]}`
  - 普通射程翻倍；触碰法术改为 30 尺
```

```md
- `Heightened Spell / 升阶法术`
  - 通过 `metamagic_options={"selected": ["heightened_spell"], "heightened_target_id": "..."}`
```

```md
- `Careful Spell / 谨慎法术`
  - 通过 `metamagic_options={"selected": ["careful_spell"], "careful_target_ids": [...]}`
```

- [ ] **Step 2: 在开发计划中记录第一批超魔已落地范围**

```md
### 2026-04-18 补充：Metamagic Batch 1

- 已完成：
  - `Quickened Spell`
  - `Distant Spell`
  - `Heightened Spell`
  - `Careful Spell`
- 当前限制：
  - 一次施法仅支持一个超魔
```

- [ ] **Step 3: 运行本轮相关全量回归**

Run:

```bash
python3 -m pytest -q \
  trpg-battle-system/test/test_spell_request.py \
  trpg-battle-system/test/test_encounter_cast_spell.py \
  trpg-battle-system/test/test_execute_save_spell.py \
  trpg-battle-system/test/test_saving_throw_request.py \
  trpg-battle-system/test/test_saving_throw_result.py
```

Expected: PASS

- [ ] **Step 4: 如时间允许，补跑完整套件**

Run:

```bash
python3 -m pytest -q
```

Expected: PASS；若失败，记录与本轮无关的现有失败项，不要静默忽略。

- [ ] **Step 5: Commit**

```bash
git add \
  trpg-battle-system/docs/llm-runtime-tool-guide.md \
  trpg-battle-system/docs/development-plan.md
git commit -m "docs: document metamagic batch 1"
```

## Self-Review

- Spec coverage:
  - `SpellRequest` 通用超魔解析：Task 1
  - `Quickened` 资源与动作经济：Task 2
  - `Distant` 射程改写：Task 3
  - `Heightened` / `Careful` 豁免链：Task 4
  - 文档与 LLM 使用说明：Task 5
- Placeholder scan:
  - 无 `TBD` / `TODO` / “之后再补”的执行步骤
- Type consistency:
  - 全程统一使用 `metamagic_options`
  - 结构化结果统一使用 `metamagic`
  - 豁免链统一读取 `heightened_target_id` / `careful_target_ids`

---

## 2026-04-19 补充：2024 施法位消耗规则修正

**规则修正目标：**

- 不再使用“同回合附赠动作高环法术限制”的旧版口径
- 改为 2024 规则：
  - 每回合中，角色通过施法至多只能实际消耗一次法术位
  - 不消耗法术位的施法不计入此限制
- 本次只纳入三条主链：
  - `EncounterCastSpell`
  - `ExecuteSpell`
  - `ExecuteSaveSpell`
- 不纳入独立类特性 service：
  - `UseArmorOfShadows`
  - `UseFiendishVigor`
  - 其他本来就不消耗法术位的独立调用

### Task 6: 统一“本回合已通过施法消耗法术位”判定

**Files:**
- Modify: `trpg-battle-system/tools/services/spells/encounter_cast_spell.py`
- Modify: `trpg-battle-system/test/test_encounter_cast_spell.py`
- Modify: `trpg-battle-system/test/test_execute_save_spell.py`
- Modify: `trpg-battle-system/docs/llm-runtime-tool-guide.md`
- Modify: `trpg-battle-system/docs/development-plan.md`

- [ ] **Step 1: 先写失败测试，锁定新规则**

```python
def test_execute_quickened_spell_marks_spell_slot_cast_used_this_turn_when_it_spends_a_slot(self) -> None:
    result = service.execute(
        encounter_id="enc_cast_spell_test",
        spell_id="chromatic_orb",
        target_ids=["ent_enemy_iron_duster_001"],
        cast_level=1,
        metamagic_options={"selected": ["quickened_spell"]},
    )

    updated = encounter_repo.get("enc_cast_spell_test")
    assert updated is not None
    assert result["slot_consumed"] is not None
    assert updated.entities["ent_ally_eric_001"].action_economy["spell_slot_cast_used_this_turn"] is True
```

```python
def test_execute_allows_cantrip_after_spell_slot_cast_used_this_turn(self) -> None:
    caster.action_economy["spell_slot_cast_used_this_turn"] = True

    result = service.execute(
        encounter_id="enc_cast_spell_test",
        spell_id="fire_bolt",
        target_ids=["ent_enemy_iron_duster_001"],
        cast_level=0,
    )

    assert result["spell_id"] == "fire_bolt"
```

```python
def test_execute_rejects_second_spell_that_would_spend_spell_slot_this_turn(self) -> None:
    caster.action_economy["spell_slot_cast_used_this_turn"] = True

    with self.assertRaisesRegex(ValueError, "spell_slot_cast_already_used_this_turn"):
        service.execute(
            encounter_id="enc_cast_spell_test",
            spell_id="chromatic_orb",
            target_ids=["ent_enemy_iron_duster_001"],
            cast_level=1,
        )
```

```python
def test_execute_free_cast_does_not_mark_spell_slot_cast_used_this_turn(self) -> None:
    result = service.execute(
        encounter_id="enc_cast_spell_test",
        spell_id="find_steed",
        cast_level=2,
        target_point={"x": 5, "y": 5, "anchor": "cell_center"},
    )

    updated = encounter_repo.get("enc_cast_spell_test")
    assert updated is not None
    assert result["slot_consumed"] is None
    assert updated.entities["ent_ally_eric_001"].action_economy.get("spell_slot_cast_used_this_turn") is not True
```

Run: `python3 -m pytest -q trpg-battle-system/test/test_encounter_cast_spell.py -k "spell_slot_cast_used_this_turn or quickened_spell"`
Expected: FAIL，原因应为当前仍使用旧的 `leveled_spell` 标记与限制。

- [ ] **Step 2: 在 `EncounterCastSpell` 收口“这次施法是否实际消耗法术位”**

```python
will_consume_spell_slot = (
    spell_level > 0
    and not free_find_steed_cast_used
    and not free_hunters_mark_cast_used
)
```

```python
if will_consume_spell_slot and bool(caster.action_economy.get("spell_slot_cast_used_this_turn")):
    raise ValueError("spell_slot_cast_already_used_this_turn")
```

```python
if slot_consumed is not None:
    caster.action_economy["spell_slot_cast_used_this_turn"] = True
```

- [ ] **Step 3: 删除旧 quickened 同回合高环法术限制**

```python
# remove:
# leveled_spell_cast_this_turn
# bonus_action_leveled_spell_cast_this_turn
# cannot_cast_bonus_action_leveled_spell_after_leveled_spell
# cannot_cast_leveled_spell_after_bonus_action_leveled_spell
```

改为仅保留：

```python
if bool(metamagic.get("quickened_spell")):
    action_cost = "bonus_action"
```

- [ ] **Step 4: 确认 `ExecuteSpell` / `ExecuteSaveSpell` 自动继承**

无需在两个上层入口重复写判定逻辑；它们通过调用 `EncounterCastSpell` 自动继承规则。

补一条验证测试：

```python
def test_execute_save_spell_rejects_second_slot_spending_spell_in_same_turn(self) -> None:
    caster.action_economy["spell_slot_cast_used_this_turn"] = True
    with self.assertRaisesRegex(ValueError, "spell_slot_cast_already_used_this_turn"):
        service.execute(...)
```

- [ ] **Step 5: 更新文档**

明确写清：

- 当前系统使用的是“本回合是否已有一次施法实际消耗法术位”
- 不按“附赠动作高环法术限制”处理
- 免费施法 / 物品施法 / 戏法不计入这条限制

- [ ] **Step 6: 跑测试转绿**

Run:

```bash
python3 -m pytest -q \
  trpg-battle-system/test/test_encounter_cast_spell.py \
  trpg-battle-system/test/test_execute_save_spell.py
```

Expected: PASS

- [ ] **Step 7: 全链回归**

Run:

```bash
python3 -m pytest -q \
  trpg-battle-system/test/test_spell_request.py \
  trpg-battle-system/test/test_encounter_cast_spell.py \
  trpg-battle-system/test/test_spell_reaction_window.py \
  trpg-battle-system/test/test_saving_throw_request.py \
  trpg-battle-system/test/test_saving_throw_result.py \
  trpg-battle-system/test/test_execute_save_spell.py
```

Expected: PASS
