# Subtle Spell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `Subtle Spell / 精妙法术` 增加第一版可用实现，使其在战斗中免疫 `Counterspell / 反制法术`，并向 LLM 暴露“施法动作不可察觉”的结构化字段。

**Architecture:** 复用现有施法声明链路，把 `metamagic_options` 作为施法请求级别输入，在 `SpellRequest` 中完成校验与结构化投影，在 `EncounterCastSpell` 中执行术法点扣除与失败回滚，再由 reaction candidate 收集层根据 `spell_declared` payload 跳过 `counterspell`。剧情提示通过 `noticeability` 字段返回，不做独立运行态。

**Tech Stack:** Python, pytest, `SpellRequest`, `EncounterCastSpell`, 反应框架 `collect_reaction_candidates`, 现有 `sorcerer` runtime helper。

---

### Task 1: 为施法请求增加 `metamagic_options` 与 `Subtle Spell` 结构化结果

**Files:**
- Modify: `trpg-battle-system/tools/services/spells/spell_request.py`
- Modify: `trpg-battle-system/test/test_spell_request.py`

- [ ] **Step 1: 写 `SpellRequest` 的失败测试**

```python
def test_execute_accepts_subtle_spell_for_sorcerer_and_returns_noticeability(self) -> None:
    encounter_repo, spell_repo = self._build_repositories(
        {
            "spell_definitions": {
                "hold_person": {
                    "id": "hold_person",
                    "name": "Hold Person",
                    "level": 2,
                    "base": {"level": 2, "casting_time": "1 action", "concentration": True},
                    "resolution": {"activation": "action"},
                    "targeting": {"allowed_target_types": ["creature"]},
                    "save_ability": "wis",
                }
            }
        }
    )
    encounter = encounter_repo.get("enc_spell_request_test")
    caster = encounter.entities["ent_caster_001"]
    caster.class_features = {
        "sorcerer": {"level": 3, "sorcery_points": {"current": 3, "max": 3}}
    }
    caster.spells.append(
        {"spell_id": "hold_person", "name": "Hold Person", "level": 2, "casting_class": "sorcerer"}
    )
    encounter_repo.save(encounter)

    result = SpellRequest(encounter_repo, spell_repo).execute(
        encounter_id="enc_spell_request_test",
        actor_id="ent_caster_001",
        spell_id="hold_person",
        cast_level=2,
        target_entity_ids=["ent_target_humanoid_001"],
        metamagic_options={"selected": ["subtle_spell"]},
    )

    assert result["ok"] is True
    assert result["metamagic"]["subtle_spell"] is True
    assert result["noticeability"]["casting_is_perceptible"] is False
```

```python
def test_execute_rejects_subtle_spell_for_non_sorcerer(self) -> None:
    result = service.execute(
        encounter_id="enc_spell_request_test",
        actor_id="ent_caster_001",
        spell_id="magic_missile",
        cast_level=1,
        metamagic_options={"selected": ["subtle_spell"]},
    )

    assert result["ok"] is False
    assert result["error_code"] == "metamagic_not_available"
```

Run: `python3 -m pytest -q trpg-battle-system/test/test_spell_request.py -k subtle_spell`
Expected: FAIL because `metamagic_options` is unsupported and result fields are missing.

- [ ] **Step 2: 在 `SpellRequest` 中解析超魔参数**

```python
def execute(
    self,
    *,
    encounter_id: str,
    actor_id: str,
    spell_id: str,
    cast_level: int,
    target_entity_ids: list[str] | None = None,
    target_point: dict[str, Any] | None = None,
    declared_action_cost: str | None = None,
    context: dict[str, Any] | None = None,
    allow_out_of_turn_actor: bool = False,
    metamagic_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # ...
```

```python
def _resolve_metamagic(
    self,
    *,
    actor: Any,
    known_spell: dict[str, Any],
    metamagic_options: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if metamagic_options is None:
        return None
    selected = metamagic_options.get("selected")
    if not isinstance(selected, list):
        raise ValueError("metamagic_options.selected must be a list")
    normalized = [str(item).strip().lower() for item in selected if str(item).strip()]
    if any(item != "subtle_spell" for item in normalized):
        raise ValueError("unknown_metamagic_option")
    if len(normalized) > 1:
        raise ValueError("only_one_metamagic_option_supported")
    if not normalized:
        return None

    if normalized[0] == "subtle_spell":
        sorcerer = ensure_sorcerer_runtime(actor)
        if int(sorcerer.get("level", 0) or 0) < 2:
            return {"ok": False, "error_code": "metamagic_not_available", "message": "当前施法者无法使用精妙法术"}
        sorcery_points = sorcerer.get("sorcery_points")
        if not isinstance(sorcery_points, dict) or int(sorcery_points.get("current", 0) or 0) < 1:
            return {"ok": False, "error_code": "insufficient_sorcery_points", "message": "术法点不足，无法使用精妙法术"}
        return {
            "selected": ["subtle_spell"],
            "subtle_spell": True,
            "sorcery_point_cost": 1,
            "noticeability": {
                "casting_is_perceptible": False,
                "verbal_visible": False,
                "somatic_visible": False,
                "material_visible": False,
                "spell_effect_visible": True,
            },
        }
```

- [ ] **Step 3: 把 `metamagic` 与 `noticeability` 写入返回结果**

```python
metamagic_result = self._resolve_metamagic(
    actor=actor,
    known_spell=known_spell,
    metamagic_options=metamagic_options,
)
if isinstance(metamagic_result, dict) and metamagic_result.get("ok") is False:
    return metamagic_result
```

```python
return {
    "ok": True,
    # ...
    "metamagic": {
        "selected": list(metamagic_result.get("selected", [])) if isinstance(metamagic_result, dict) else [],
        "subtle_spell": bool(metamagic_result.get("subtle_spell")) if isinstance(metamagic_result, dict) else False,
        "sorcery_point_cost": int(metamagic_result.get("sorcery_point_cost", 0) or 0)
        if isinstance(metamagic_result, dict)
        else 0,
    },
    "noticeability": dict(metamagic_result.get("noticeability", {})) if isinstance(metamagic_result, dict) else {
        "casting_is_perceptible": True,
        "verbal_visible": True,
        "somatic_visible": True,
        "material_visible": True,
        "spell_effect_visible": True,
    },
}
```

- [ ] **Step 4: 运行针对性测试**

Run: `python3 -m pytest -q trpg-battle-system/test/test_spell_request.py -k subtle_spell`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add \
  trpg-battle-system/tools/services/spells/spell_request.py \
  trpg-battle-system/test/test_spell_request.py
git commit -m "feat: add subtle spell request parsing"
```

### Task 2: 在施法声明阶段扣除并回滚术法点

**Files:**
- Modify: `trpg-battle-system/tools/services/spells/encounter_cast_spell.py`
- Modify: `trpg-battle-system/test/test_encounter_cast_spell.py`

- [ ] **Step 1: 写 `EncounterCastSpell` 的失败测试**

```python
def test_execute_subtle_spell_spends_one_sorcery_point(self) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        encounter = build_encounter()
        caster = encounter.entities["ent_ally_eric_001"]
        caster.class_features["sorcerer"] = {"level": 3, "sorcery_points": {"current": 3, "max": 3}}
        caster.spells.append({"spell_id": "hold_person", "name": "Hold Person", "level": 2, "casting_class": "sorcerer"})
        encounter_repo.save(encounter)

        result = EncounterCastSpell(encounter_repo, AppendEvent(event_repo)).execute(
            encounter_id="enc_cast_spell_test",
            spell_id="hold_person",
            cast_level=2,
            target_ids=["ent_enemy_iron_duster_001"],
            metamagic_options={"selected": ["subtle_spell"]},
        )

        updated = encounter_repo.get("enc_cast_spell_test")
        assert updated.entities["ent_ally_eric_001"].class_features["sorcerer"]["sorcery_points"]["current"] == 2
        assert result["metamagic"]["subtle_spell"] is True
```

```python
def test_execute_rolls_back_sorcery_points_when_append_event_fails(self) -> None:
    with patch.object(AppendEvent, "execute", side_effect=RuntimeError("boom")):
        with self.assertRaisesRegex(RuntimeError, "boom"):
            service.execute(
                encounter_id="enc_cast_spell_test",
                spell_id="hold_person",
                cast_level=2,
                target_ids=["ent_enemy_iron_duster_001"],
                metamagic_options={"selected": ["subtle_spell"]},
            )

    updated = encounter_repo.get("enc_cast_spell_test")
    assert updated.entities["ent_ally_eric_001"].class_features["sorcerer"]["sorcery_points"]["current"] == 3
```

Run: `python3 -m pytest -q trpg-battle-system/test/test_encounter_cast_spell.py -k subtle_spell`
Expected: FAIL because `EncounterCastSpell` does not consume or rollback sorcery points.

- [ ] **Step 2: 扩 `EncounterCastSpell.execute` 签名并透传超魔**

```python
def execute(
    self,
    *,
    encounter_id: str,
    spell_id: str,
    cast_level: int,
    target_ids: list[str] | None = None,
    target_point: dict[str, Any] | None = None,
    reason: str | None = None,
    spell_options: dict[str, Any] | None = None,
    include_encounter_state: bool = True,
    apply_no_roll_immediate_effects: bool = True,
    allow_out_of_turn_actor: bool = False,
    metamagic_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
```

- [ ] **Step 3: 在施法成功声明时扣 1 点术法点，并在异常时回滚**

```python
spell_request = SpellRequest(...).execute(
    encounter_id=encounter_id,
    actor_id=caster.entity_id,
    spell_id=spell_id,
    cast_level=cast_level,
    target_entity_ids=resolved_target_ids,
    target_point=target_point,
    metamagic_options=metamagic_options,
    allow_out_of_turn_actor=allow_out_of_turn_actor,
)
metamagic = spell_request.get("metamagic") if isinstance(spell_request, dict) else {}
subtle_spell_used = isinstance(metamagic, dict) and bool(metamagic.get("subtle_spell"))
if subtle_spell_used:
    sorcerer = ensure_sorcerer_runtime(caster)
    sorcery_points = sorcerer["sorcery_points"]
    sorcery_points_before = int(sorcery_points.get("current", 0) or 0)
    sorcery_points["current"] = sorcery_points_before - 1
else:
    sorcery_points_before = None
```

```python
payload = {
    # ...
    "metamagic": spell_request.get("metamagic"),
    "noticeability": spell_request.get("noticeability"),
}
```

```python
except Exception:
    self._rollback_spell_slot_if_needed(caster, slot_consumed)
    if subtle_spell_used and sorcery_points_before is not None:
        ensure_sorcerer_runtime(caster)["sorcery_points"]["current"] = sorcery_points_before
    caster.action_economy = previous_action_economy
    self.encounter_repository.save(encounter)
    raise
```

- [ ] **Step 4: 在返回值里带出 `metamagic` 与 `noticeability`**

```python
result = {
    "encounter_id": encounter.encounter_id,
    # ...
    "metamagic": spell_request.get("metamagic"),
    "noticeability": spell_request.get("noticeability"),
}
```

- [ ] **Step 5: 运行针对性测试**

Run: `python3 -m pytest -q trpg-battle-system/test/test_encounter_cast_spell.py -k subtle_spell`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add \
  trpg-battle-system/tools/services/spells/encounter_cast_spell.py \
  trpg-battle-system/test/test_encounter_cast_spell.py
git commit -m "feat: spend sorcery points for subtle spell"
```

### Task 3: 在反应候选收集层跳过 `counterspell`

**Files:**
- Modify: `trpg-battle-system/tools/services/combat/rules/reactions/collect_reaction_candidates.py`
- Modify: `trpg-battle-system/test/test_collect_reaction_candidates.py`
- Modify: `trpg-battle-system/test/test_encounter_cast_spell.py`

- [ ] **Step 1: 写 `counterspell` 跳过逻辑的失败测试**

```python
def test_collect_candidates_ignores_counterspell_when_spell_declared_is_subtle() -> None:
    trigger_event = {
        "trigger_type": "spell_declared",
        "caster_entity_id": "ent_caster_001",
        "payload": {
            "spell_id": "hold_person",
            "metamagic": {"subtle_spell": True},
            "noticeability": {"casting_is_perceptible": False},
        },
    }

    candidates = service.execute(encounter=encounter, trigger_event=trigger_event)

    assert candidates == []
```

```python
def test_execute_does_not_open_counterspell_window_for_subtle_spell(self) -> None:
    result = service.execute(
        encounter_id="enc_cast_spell_test",
        spell_id="hold_person",
        cast_level=2,
        target_ids=["ent_enemy_iron_duster_001"],
        metamagic_options={"selected": ["subtle_spell"]},
    )

    assert result.get("status") != "waiting_reaction"
    assert result.get("pending_reaction_window") is None
```

Run: `python3 -m pytest -q trpg-battle-system/test/test_collect_reaction_candidates.py trpg-battle-system/test/test_encounter_cast_spell.py -k subtle_spell`
Expected: FAIL because subtle spell still allows counterspell candidate collection.

- [ ] **Step 2: 在 `collect_reaction_candidates.py` 中读取 `spell_declared.payload.metamagic`**

```python
if trigger_type == "spell_declared":
    payload = trigger_event.get("payload")
    if isinstance(payload, dict):
        metamagic = payload.get("metamagic")
        if isinstance(metamagic, dict) and bool(metamagic.get("subtle_spell")):
            return []
```

- [ ] **Step 3: 保留普通施法原行为不变**

```python
definitions = [definition for definition in definitions if definition.get("reaction_type") == "counterspell"]
```

这段逻辑保留，只是在 `subtle_spell` 命中时提前返回空列表。

- [ ] **Step 4: 运行针对性测试**

Run: `python3 -m pytest -q trpg-battle-system/test/test_collect_reaction_candidates.py trpg-battle-system/test/test_encounter_cast_spell.py -k subtle_spell`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add \
  trpg-battle-system/tools/services/combat/rules/reactions/collect_reaction_candidates.py \
  trpg-battle-system/test/test_collect_reaction_candidates.py \
  trpg-battle-system/test/test_encounter_cast_spell.py
git commit -m "feat: block counterspell on subtle spell"
```

### Task 4: 更新 LLM 文档并跑全量验证

**Files:**
- Modify: `trpg-battle-system/docs/llm-runtime-tool-guide.md`
- Modify: `trpg-battle-system/docs/development-plan.md`
- Modify: `trpg-battle-system/test/test_spell_request.py`
- Modify: `trpg-battle-system/test/test_encounter_cast_spell.py`

- [ ] **Step 1: 补 LLM 文档段落**

```markdown
- `metamagic_options={"selected": ["subtle_spell"]}`
  - 目前只支持 `subtle_spell`
  - 若本次施法声明为 `subtle_spell`：
    - 会消耗 1 点术法点
    - 不会触发 `Counterspell / 反制法术`
    - 返回结果会带：
      - `metamagic.subtle_spell = true`
      - `noticeability.casting_is_perceptible = false`
  - 这表示施法动作本身不可察觉，不表示法术效果一定不可见
```

- [ ] **Step 2: 在开发日志里登记当前范围**

```markdown
- [x] `Subtle Spell / 精妙法术` 第一版
  - 已实现：
    - 不触发 `counterspell`
    - 向 LLM 返回 `noticeability`
  - 未实现：
    - 其他超魔
    - 完整施法可见性系统
```

- [ ] **Step 3: 跑功能相关回归**

Run: `python3 -m pytest -q trpg-battle-system/test/test_spell_request.py trpg-battle-system/test/test_encounter_cast_spell.py trpg-battle-system/test/test_collect_reaction_candidates.py -k subtle_spell`
Expected: PASS

- [ ] **Step 4: 跑全量测试**

Run: `python3 -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add \
  trpg-battle-system/docs/llm-runtime-tool-guide.md \
  trpg-battle-system/docs/development-plan.md \
  trpg-battle-system/test/test_spell_request.py \
  trpg-battle-system/test/test_encounter_cast_spell.py \
  trpg-battle-system/test/test_collect_reaction_candidates.py
git commit -m "docs: document subtle spell runtime behavior"
```
