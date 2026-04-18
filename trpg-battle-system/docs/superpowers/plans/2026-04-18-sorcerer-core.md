# Sorcerer Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `Sorcerer / 术士` 实现 1-7 级非超魔核心能力，包括术法点、先天术法、法术位与术法点转换、术法复苏，以及相关运行态、文档和测试。

**Architecture:** 复用现有职业运行态与法术位框架，在 `class_features.shared.runtime` 中增加术士运行态初始化，在 `class_features.shared.spell_slots` 中为术法点创造的临时法术位增加可追踪存储；战斗增益通过施法请求链路自动读取 `sorcerer` 运行态，不要求 LLM 额外传隐藏参数。显式能力入口统一做成 `Use*`/转换服务，并通过 `tools.services.__init__` 暴露。

**Tech Stack:** Python, pytest, 现有 `EncounterRepository`/`GetEncounterState` 服务层, `class_features.shared` 运行态 helper, `SpellRequest`/施法执行链路。

---

### Task 1: 建立术士运行态与共享导出

**Files:**
- Modify: `trpg-battle-system/tools/services/class_features/shared/runtime.py`
- Modify: `trpg-battle-system/tools/services/class_features/shared/__init__.py`
- Modify: `trpg-battle-system/test/test_class_feature_runtime_helpers.py`

- [ ] **Step 1: 写运行态 helper 的失败测试**

```python
def test_ensure_sorcerer_runtime_derives_core_progression_from_level() -> None:
    helpers = _import_helpers()
    entity = build_entity()
    entity.class_features = {"sorcerer": {"level": 7}}

    sorcerer = helpers.ensure_sorcerer_runtime(entity)

    assert sorcerer["sorcery_points"]["max"] == 7
    assert sorcerer["sorcery_points"]["current"] == 7
    assert sorcerer["innate_sorcery"]["uses_max"] == 2
    assert sorcerer["innate_sorcery"]["uses_current"] == 2
    assert sorcerer["innate_sorcery"]["active"] is False
    assert sorcerer["sorcerous_restoration"]["enabled"] is True
    assert sorcerer["sorcery_incarnate"]["enabled"] is True
```

Run: `python3 -m pytest -q trpg-battle-system/test/test_class_feature_runtime_helpers.py -k sorcerer`
Expected: FAIL with `AttributeError` or missing `ensure_sorcerer_runtime`.

- [ ] **Step 2: 在 shared runtime 中加入术士运行态**

```python
def get_sorcerer_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    runtime = get_class_runtime(entity_or_class_features, "sorcerer")
    if not runtime:
        return {}
    return ensure_sorcerer_runtime(entity_or_class_features)


def ensure_sorcerer_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    sorcerer = ensure_class_runtime(entity_or_class_features, "sorcerer")
    level = int(sorcerer.get("level", 0) or 0)

    sorcery_points = sorcerer.setdefault("sorcery_points", {})
    sorcery_points["max"] = level if level > 0 else int(sorcery_points.get("max", 0) or 0)
    current = sorcery_points.get("current")
    sorcery_points["current"] = current if isinstance(current, int) else sorcery_points["max"]

    innate_sorcery = sorcerer.setdefault("innate_sorcery", {})
    innate_sorcery["enabled"] = level >= 1
    innate_sorcery["uses_max"] = 2 if level >= 1 else 0
    uses_current = innate_sorcery.get("uses_current")
    innate_sorcery["uses_current"] = uses_current if isinstance(uses_current, int) else innate_sorcery["uses_max"]
    innate_sorcery["active"] = bool(innate_sorcery.get("active"))
    innate_sorcery.setdefault("expires_at_turn", None)

    font_of_magic = sorcerer.setdefault("font_of_magic", {})
    font_of_magic["enabled"] = level >= 2

    sorcerous_restoration = sorcerer.setdefault("sorcerous_restoration", {})
    sorcerous_restoration["enabled"] = level >= 5
    sorcerous_restoration["used_since_long_rest"] = bool(
        sorcerous_restoration.get("used_since_long_rest", False)
    )

    sorcery_incarnate = sorcerer.setdefault("sorcery_incarnate", {})
    sorcery_incarnate["enabled"] = level >= 7

    created_spell_slots = sorcerer.setdefault("created_spell_slots", {})
    for slot_level in range(1, 6):
        key = str(slot_level)
        value = created_spell_slots.get(key)
        created_spell_slots[key] = value if isinstance(value, int) and value >= 0 else 0

    return sorcerer
```

- [ ] **Step 3: 导出 shared helper**

```python
from tools.services.class_features.shared.runtime import (
    ensure_sorcerer_runtime,
    get_sorcerer_runtime,
)

__all__ = [
    # ...
    "ensure_sorcerer_runtime",
    "get_sorcerer_runtime",
]
```

- [ ] **Step 4: 运行测试验证 helper**

Run: `python3 -m pytest -q trpg-battle-system/test/test_class_feature_runtime_helpers.py -k sorcerer`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add \
  trpg-battle-system/tools/services/class_features/shared/runtime.py \
  trpg-battle-system/tools/services/class_features/shared/__init__.py \
  trpg-battle-system/test/test_class_feature_runtime_helpers.py
git commit -m "feat: add sorcerer runtime helpers"
```

### Task 2: 为术法点创造的法术位增加存储与重置支持

**Files:**
- Modify: `trpg-battle-system/tools/services/class_features/shared/spell_slots.py`
- Modify: `trpg-battle-system/tools/services/class_features/shared/__init__.py`
- Modify: `trpg-battle-system/test/test_spell_slot_runtime.py`

- [ ] **Step 1: 写法术位临时增减的失败测试**

```python
def test_add_created_spell_slot_increments_slot_pool_and_runtime_counter() -> None:
    entity = build_spellcaster({"sorcerer": {"level": 5}})
    ensure_spell_slots_runtime(entity)

    result = add_created_spell_slot(entity, slot_level=3, amount=1)

    assert result["remaining_after"] == 3
    assert entity.resources["spell_slots"]["3"]["remaining"] == 3
    assert entity.class_features["sorcerer"]["created_spell_slots"]["3"] == 1


def test_clear_created_spell_slots_restores_original_remaining_values() -> None:
    entity = build_spellcaster({"sorcerer": {"level": 5}})
    ensure_spell_slots_runtime(entity)
    add_created_spell_slot(entity, slot_level=1, amount=1)
    add_created_spell_slot(entity, slot_level=2, amount=1)

    clear_created_spell_slots(entity)

    assert entity.resources["spell_slots"]["1"]["remaining"] == entity.resources["spell_slots"]["1"]["max"]
    assert entity.resources["spell_slots"]["2"]["remaining"] == entity.resources["spell_slots"]["2"]["max"]
    assert entity.class_features["sorcerer"]["created_spell_slots"]["1"] == 0
    assert entity.class_features["sorcerer"]["created_spell_slots"]["2"] == 0
```

Run: `python3 -m pytest -q trpg-battle-system/test/test_spell_slot_runtime.py -k created_spell_slot`
Expected: FAIL with missing helper names.

- [ ] **Step 2: 在 spell_slots helper 中加入创建/清理函数**

```python
def add_created_spell_slot(entity: Any, *, slot_level: int, amount: int = 1) -> dict[str, Any]:
    ensure_spell_slots_runtime(entity)
    sorcerer = ensure_sorcerer_runtime(entity)
    if slot_level < 1 or amount < 1:
        raise ValueError("created_spell_slot_invalid")

    slot_key = str(slot_level)
    resources = getattr(entity, "resources", {})
    spell_slots = resources.setdefault("spell_slots", {})
    slot_info = spell_slots.setdefault(slot_key, {"max": 0, "remaining": 0})
    before = int(slot_info.get("remaining", 0) or 0)
    slot_info["remaining"] = before + amount

    created = sorcerer.setdefault("created_spell_slots", {})
    created[slot_key] = int(created.get(slot_key, 0) or 0) + amount
    return {"slot_level": slot_level, "remaining_before": before, "remaining_after": slot_info["remaining"]}


def clear_created_spell_slots(entity: Any) -> dict[str, int]:
    ensure_spell_slots_runtime(entity)
    sorcerer = ensure_sorcerer_runtime(entity)
    resources = getattr(entity, "resources", {})
    spell_slots = resources.get("spell_slots") if isinstance(resources, dict) else None
    created = sorcerer.get("created_spell_slots")
    if not isinstance(spell_slots, dict) or not isinstance(created, dict):
        return {}

    cleared: dict[str, int] = {}
    for slot_key, created_amount in created.items():
        if not isinstance(created_amount, int) or created_amount <= 0:
            created[slot_key] = 0
            continue
        slot_info = spell_slots.get(str(slot_key))
        if isinstance(slot_info, dict):
            remaining = int(slot_info.get("remaining", 0) or 0)
            slot_info["remaining"] = max(0, remaining - created_amount)
        created[str(slot_key)] = 0
        cleared[str(slot_key)] = created_amount
    return cleared
```

- [ ] **Step 3: 导出 spell slot helper**

```python
from tools.services.class_features.shared.spell_slots import (
    add_created_spell_slot,
    clear_created_spell_slots,
)
```

- [ ] **Step 4: 运行针对性测试**

Run: `python3 -m pytest -q trpg-battle-system/test/test_spell_slot_runtime.py -k created_spell_slot`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add \
  trpg-battle-system/tools/services/class_features/shared/spell_slots.py \
  trpg-battle-system/tools/services/class_features/shared/__init__.py \
  trpg-battle-system/test/test_spell_slot_runtime.py
git commit -m "feat: support sorcerer-created spell slots"
```

### Task 3: 实现 `Innate Sorcery / 先天术法`

**Files:**
- Create: `trpg-battle-system/tools/services/class_features/sorcerer/__init__.py`
- Create: `trpg-battle-system/tools/services/class_features/sorcerer/use_innate_sorcery.py`
- Modify: `trpg-battle-system/tools/services/__init__.py`
- Modify: `trpg-battle-system/tools/services/spells/spell_request.py`
- Modify: `trpg-battle-system/test/test_spell_request.py`
- Create: `trpg-battle-system/test/test_use_innate_sorcery.py`

- [ ] **Step 1: 写入口服务与施法增益的失败测试**

```python
def test_use_innate_sorcery_spends_bonus_action_and_consumes_use() -> None:
    service = UseInnateSorcery(repo)
    result = service.execute(encounter_id="enc_sorc_001", actor_id="ent_sorc_001")

    innate = result["encounter_state"]["entities"]["ent_sorc_001"]["class_features"]["sorcerer"]["innate_sorcery"]
    assert innate["active"] is True
    assert innate["uses_current"] == 1


def test_spell_request_grants_advantage_and_dc_bonus_while_innate_sorcery_active() -> None:
    caster.class_features = {
        "sorcerer": {
            "level": 3,
            "innate_sorcery": {"enabled": True, "active": True, "uses_max": 2, "uses_current": 1},
        }
    }
    caster.spells = [{"spell_id": "chromatic_orb", "casting_class": "sorcerer", "level": 1}]

    result = SpellRequest(repo, spell_repo).execute(
        encounter_id="enc_spell_req_test",
        actor_id=caster.entity_id,
        spell_id="chromatic_orb",
        cast_level=1,
    )

    assert result["spell_attack_advantage"] is True
    assert result["spell_save_dc_bonus"] == 1
```

Run: `python3 -m pytest -q trpg-battle-system/test/test_use_innate_sorcery.py trpg-battle-system/test/test_spell_request.py -k innate_sorcery`
Expected: FAIL with missing service/result fields.

- [ ] **Step 2: 创建术士 service 包与能力入口**

```python
class UseInnateSorcery:
    def execute(self, *, encounter_id: str, actor_id: str) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        sorcerer = ensure_sorcerer_runtime(actor)
        innate = sorcerer.get("innate_sorcery")
        if not isinstance(innate, dict) or not bool(innate.get("enabled")):
            raise ValueError("innate_sorcery_not_available")
        if bool(actor.action_economy.get("bonus_action_used")):
            raise ValueError("bonus_action_already_used")
        if bool(innate.get("active")):
            raise ValueError("innate_sorcery_already_active")

        used_sorcery_points = False
        uses_current = int(innate.get("uses_current", 0) or 0)
        if uses_current > 0:
            innate["uses_current"] = uses_current - 1
        else:
            sorcery_points = sorcerer.get("sorcery_points")
            if int(sorcerer.get("level", 0) or 0) < 7:
                raise ValueError("innate_sorcery_no_uses_remaining")
            if not isinstance(sorcery_points, dict) or int(sorcery_points.get("current", 0) or 0) < 2:
                raise ValueError("innate_sorcery_requires_sorcery_points")
            sorcery_points["current"] = int(sorcery_points["current"]) - 2
            used_sorcery_points = True

        innate["active"] = True
        innate["expires_at_turn"] = {"rounds_remaining": 10}
        actor.action_economy["bonus_action_used"] = True
        self.encounter_repository.save(encounter)
        return {"class_feature_result": {"innate_sorcery": {"active": True, "used_sorcery_points": used_sorcery_points}}}
```

- [ ] **Step 3: 在 `SpellRequest` 中注入术士法术增益**

```python
from tools.services.class_features.shared import ensure_sorcerer_runtime

def _resolve_spellcasting_class(self, *, known_spell: dict[str, Any]) -> str | None:
    casting_class = known_spell.get("casting_class")
    if isinstance(casting_class, str) and casting_class.strip():
        return casting_class.strip().lower()
    classes = known_spell.get("classes")
    if isinstance(classes, list) and len(classes) == 1:
        return str(classes[0]).strip().lower()
    return None

def _resolve_sorcerer_spell_modifiers(self, *, actor: Any, known_spell: dict[str, Any]) -> dict[str, Any]:
    if self._resolve_spellcasting_class(known_spell=known_spell) != "sorcerer":
        return {"spell_attack_advantage": False, "spell_save_dc_bonus": 0}
    sorcerer = ensure_sorcerer_runtime(actor)
    innate = sorcerer.get("innate_sorcery")
    if not isinstance(innate, dict) or not bool(innate.get("active")):
        return {"spell_attack_advantage": False, "spell_save_dc_bonus": 0}
    return {"spell_attack_advantage": True, "spell_save_dc_bonus": 1}
```

- [ ] **Step 4: 暴露顶层 service**

```python
__all__ = [
    # ...
    "UseInnateSorcery",
]

_LAZY_EXPORTS = {
    # ...
    "UseInnateSorcery": ("tools.services.class_features.sorcerer.use_innate_sorcery", "UseInnateSorcery"),
}
```

- [ ] **Step 5: 运行针对性测试**

Run: `python3 -m pytest -q trpg-battle-system/test/test_use_innate_sorcery.py trpg-battle-system/test/test_spell_request.py -k innate_sorcery`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add \
  trpg-battle-system/tools/services/class_features/sorcerer/__init__.py \
  trpg-battle-system/tools/services/class_features/sorcerer/use_innate_sorcery.py \
  trpg-battle-system/tools/services/__init__.py \
  trpg-battle-system/tools/services/spells/spell_request.py \
  trpg-battle-system/test/test_spell_request.py \
  trpg-battle-system/test/test_use_innate_sorcery.py
git commit -m "feat: add innate sorcery"
```

### Task 4: 实现 `Font of Magic / 魔力泉涌`

**Files:**
- Create: `trpg-battle-system/tools/services/class_features/sorcerer/convert_spell_slot_to_sorcery_points.py`
- Create: `trpg-battle-system/tools/services/class_features/sorcerer/create_spell_slot_from_sorcery_points.py`
- Modify: `trpg-battle-system/tools/services/class_features/sorcerer/__init__.py`
- Modify: `trpg-battle-system/tools/services/__init__.py`
- Create: `trpg-battle-system/test/test_convert_spell_slot_to_sorcery_points.py`
- Create: `trpg-battle-system/test/test_create_spell_slot_from_sorcery_points.py`

- [ ] **Step 1: 写两个转换服务的失败测试**

```python
def test_convert_spell_slot_to_sorcery_points_consumes_exact_slot() -> None:
    service = ConvertSpellSlotToSorceryPoints(repo)
    result = service.execute(encounter_id="enc_sorc_001", actor_id="ent_sorc_001", slot_level=2)

    assert result["class_feature_result"]["font_of_magic"]["sorcery_points_after"] == 4
    assert result["class_feature_result"]["font_of_magic"]["consumed_slot_level"] == 2


def test_create_spell_slot_from_sorcery_points_spends_bonus_action_and_tracks_created_slot() -> None:
    service = CreateSpellSlotFromSorceryPoints(repo)
    result = service.execute(encounter_id="enc_sorc_001", actor_id="ent_sorc_001", slot_level=3)

    assert result["class_feature_result"]["font_of_magic"]["sorcery_points_after"] == 0
    assert result["class_feature_result"]["font_of_magic"]["created_slot_level"] == 3
    assert result["encounter_state"]["entities"]["ent_sorc_001"]["resources"]["spell_slots"]["3"]["remaining"] == 3
```

Run: `python3 -m pytest -q trpg-battle-system/test/test_convert_spell_slot_to_sorcery_points.py trpg-battle-system/test/test_create_spell_slot_from_sorcery_points.py`
Expected: FAIL with missing modules.

- [ ] **Step 2: 实现“法术位转术法点”**

```python
class ConvertSpellSlotToSorceryPoints:
    def execute(self, *, encounter_id: str, actor_id: str, slot_level: int) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        sorcerer = ensure_sorcerer_runtime(actor)
        if int(sorcerer.get("level", 0) or 0) < 2:
            raise ValueError("font_of_magic_not_available")

        sorcery_points = sorcerer["sorcery_points"]
        current = int(sorcery_points.get("current", 0) or 0)
        maximum = int(sorcery_points.get("max", 0) or 0)
        if current + slot_level > maximum:
            raise ValueError("sorcery_points_overflow")

        consume_exact_spell_slot(actor, slot_level)
        sorcery_points["current"] = current + slot_level
        self.encounter_repository.save(encounter)
        return {"class_feature_result": {"font_of_magic": {"consumed_slot_level": slot_level, "sorcery_points_after": sorcery_points["current"]}}}
```

- [ ] **Step 3: 实现“术法点造法术位”**

```python
CREATE_SLOT_COSTS = {
    1: {"cost": 2, "min_level": 2},
    2: {"cost": 3, "min_level": 3},
    3: {"cost": 5, "min_level": 5},
    4: {"cost": 6, "min_level": 7},
    5: {"cost": 7, "min_level": 9},
}

class CreateSpellSlotFromSorceryPoints:
    def execute(self, *, encounter_id: str, actor_id: str, slot_level: int) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        sorcerer = ensure_sorcerer_runtime(actor)
        rule = CREATE_SLOT_COSTS.get(slot_level)
        if rule is None:
            raise ValueError("invalid_created_spell_slot_level")
        if int(sorcerer.get("level", 0) or 0) < int(rule["min_level"]):
            raise ValueError("created_spell_slot_level_not_available")
        if bool(actor.action_economy.get("bonus_action_used")):
            raise ValueError("bonus_action_already_used")

        sorcery_points = sorcerer["sorcery_points"]
        current = int(sorcery_points.get("current", 0) or 0)
        if current < int(rule["cost"]):
            raise ValueError("insufficient_sorcery_points")

        sorcery_points["current"] = current - int(rule["cost"])
        add_created_spell_slot(actor, slot_level=slot_level, amount=1)
        actor.action_economy["bonus_action_used"] = True
        self.encounter_repository.save(encounter)
        return {"class_feature_result": {"font_of_magic": {"created_slot_level": slot_level, "sorcery_points_after": sorcery_points["current"]}}}
```

- [ ] **Step 4: 导出服务**

```python
from tools.services.class_features.sorcerer.convert_spell_slot_to_sorcery_points import (
    ConvertSpellSlotToSorceryPoints,
)
from tools.services.class_features.sorcerer.create_spell_slot_from_sorcery_points import (
    CreateSpellSlotFromSorceryPoints,
)
```

- [ ] **Step 5: 运行针对性测试**

Run: `python3 -m pytest -q trpg-battle-system/test/test_convert_spell_slot_to_sorcery_points.py trpg-battle-system/test/test_create_spell_slot_from_sorcery_points.py`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add \
  trpg-battle-system/tools/services/class_features/sorcerer/convert_spell_slot_to_sorcery_points.py \
  trpg-battle-system/tools/services/class_features/sorcerer/create_spell_slot_from_sorcery_points.py \
  trpg-battle-system/tools/services/class_features/sorcerer/__init__.py \
  trpg-battle-system/tools/services/__init__.py \
  trpg-battle-system/test/test_convert_spell_slot_to_sorcery_points.py \
  trpg-battle-system/test/test_create_spell_slot_from_sorcery_points.py
git commit -m "feat: add font of magic slot conversion"
```

### Task 5: 实现 `Sorcerous Restoration / 术法复苏` 与长休清理

**Files:**
- Create: `trpg-battle-system/tools/services/class_features/sorcerer/use_sorcerous_restoration.py`
- Modify: `trpg-battle-system/tools/services/class_features/sorcerer/__init__.py`
- Modify: `trpg-battle-system/tools/services/__init__.py`
- Modify: `trpg-battle-system/tools/services/spells/encounter_cast_spell.py`
- Create: `trpg-battle-system/test/test_use_sorcerous_restoration.py`
- Modify: `trpg-battle-system/test/test_encounter_cast_spell.py`

- [ ] **Step 1: 写术法复苏与长休清理的失败测试**

```python
def test_use_sorcerous_restoration_recovers_half_level_sorcery_points_once_per_long_rest() -> None:
    service = UseSorcerousRestoration(repo)
    result = service.execute(encounter_id="enc_sorc_001", actor_id="ent_sorc_001")

    assert result["class_feature_result"]["sorcerous_restoration"]["restored_points"] == 3
    assert result["class_feature_result"]["sorcerous_restoration"]["used_since_long_rest"] is True


def test_long_rest_reset_clears_created_spell_slots_and_restoration_flag() -> None:
    caster.class_features["sorcerer"] = {
        "level": 5,
        "created_spell_slots": {"1": 1, "2": 0, "3": 0, "4": 0, "5": 0},
        "sorcerous_restoration": {"enabled": True, "used_since_long_rest": True},
    }

    service._apply_long_rest_resets(caster)

    assert caster.class_features["sorcerer"]["created_spell_slots"]["1"] == 0
    assert caster.class_features["sorcerer"]["sorcerous_restoration"]["used_since_long_rest"] is False
```

Run: `python3 -m pytest -q trpg-battle-system/test/test_use_sorcerous_restoration.py trpg-battle-system/test/test_encounter_cast_spell.py -k sorcer`
Expected: FAIL with missing service or missing reset behavior.

- [ ] **Step 2: 实现术法复苏服务**

```python
class UseSorcerousRestoration:
    def execute(self, *, encounter_id: str, actor_id: str) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        sorcerer = ensure_sorcerer_runtime(actor)
        restoration = sorcerer.get("sorcerous_restoration")
        if not isinstance(restoration, dict) or not bool(restoration.get("enabled")):
            raise ValueError("sorcerous_restoration_not_available")
        if bool(restoration.get("used_since_long_rest")):
            raise ValueError("sorcerous_restoration_already_used")

        level = int(sorcerer.get("level", 0) or 0)
        restore_cap = level // 2
        sorcery_points = sorcerer["sorcery_points"]
        current = int(sorcery_points.get("current", 0) or 0)
        maximum = int(sorcery_points.get("max", 0) or 0)
        restored = min(restore_cap, max(0, maximum - current))
        sorcery_points["current"] = current + restored
        restoration["used_since_long_rest"] = True
        self.encounter_repository.save(encounter)
        return {"class_feature_result": {"sorcerous_restoration": {"restored_points": restored, "used_since_long_rest": True}}}
```

- [ ] **Step 3: 在现有长休重置入口里接入术士清理**

```python
def _apply_long_rest_resets(self, actor: Any) -> None:
    # existing resets ...
    sorcerer = ensure_sorcerer_runtime(actor)
    sorcery_points = sorcerer.get("sorcery_points")
    if isinstance(sorcery_points, dict):
        sorcery_points["current"] = int(sorcery_points.get("max", 0) or 0)

    innate = sorcerer.get("innate_sorcery")
    if isinstance(innate, dict):
        innate["uses_current"] = int(innate.get("uses_max", 0) or 0)
        innate["active"] = False
        innate["expires_at_turn"] = None

    restoration = sorcerer.get("sorcerous_restoration")
    if isinstance(restoration, dict):
        restoration["used_since_long_rest"] = False

    clear_created_spell_slots(actor)
```

- [ ] **Step 4: 暴露顶层 service**

```python
__all__ = [
    # ...
    "UseSorcerousRestoration",
]
```

- [ ] **Step 5: 运行针对性测试**

Run: `python3 -m pytest -q trpg-battle-system/test/test_use_sorcerous_restoration.py trpg-battle-system/test/test_encounter_cast_spell.py -k sorcer`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add \
  trpg-battle-system/tools/services/class_features/sorcerer/use_sorcerous_restoration.py \
  trpg-battle-system/tools/services/class_features/sorcerer/__init__.py \
  trpg-battle-system/tools/services/__init__.py \
  trpg-battle-system/tools/services/spells/encounter_cast_spell.py \
  trpg-battle-system/test/test_use_sorcerous_restoration.py \
  trpg-battle-system/test/test_encounter_cast_spell.py
git commit -m "feat: add sorcerous restoration"
```

### Task 6: 文档、运行态展示与全量验证

**Files:**
- Modify: `trpg-battle-system/tools/services/encounter/get_encounter_state.py`
- Modify: `trpg-battle-system/test/test_get_encounter_state.py`
- Modify: `trpg-battle-system/docs/llm-runtime-tool-guide.md`
- Modify: `trpg-battle-system/docs/development-plan.md`

- [ ] **Step 1: 写 encounter state 与 LLM 接口的失败测试**

```python
def test_get_encounter_state_exposes_sorcerer_runtime_summary() -> None:
    state = GetEncounterState(repo).execute("enc_sorc_001")
    sorcerer = state["entities"]["ent_sorc_001"]["class_features"]["sorcerer"]

    assert sorcerer["sorcery_points"]["current"] == 5
    assert sorcerer["innate_sorcery"]["active"] is False
    assert sorcerer["created_spell_slots"]["1"] == 0
```

Run: `python3 -m pytest -q trpg-battle-system/test/test_get_encounter_state.py -k sorcerer`
Expected: FAIL because sorcerer runtime summary is absent.

- [ ] **Step 2: 暴露玩家可见术士运行态摘要**

```python
if "sorcerer" in entity.class_features:
    sorcerer = ensure_sorcerer_runtime(entity)
    class_features_view["sorcerer"] = {
        "level": int(sorcerer.get("level", 0) or 0),
        "sorcery_points": dict(sorcerer.get("sorcery_points", {})),
        "innate_sorcery": dict(sorcerer.get("innate_sorcery", {})),
        "sorcerous_restoration": dict(sorcerer.get("sorcerous_restoration", {})),
        "created_spell_slots": dict(sorcerer.get("created_spell_slots", {})),
    }
```

- [ ] **Step 3: 更新 LLM 文档与开发日志**

```markdown
- `use_innate_sorcery(encounter_id, actor_id)`
  - `actor_id`：要激活先天术法的术士实体 ID
  - 消耗附赠动作；若正常次数耗尽且术士等级 7+，后端会自动尝试改扣 2 点术法点

- `convert_spell_slot_to_sorcery_points(encounter_id, actor_id, slot_level)`
  - 不消耗动作；消耗指定法术位，按同环阶数值转为术法点

- `create_spell_slot_from_sorcery_points(encounter_id, actor_id, slot_level)`
  - 消耗附赠动作；仅支持 1-5 环；后端会记录为长休后清空的临时法术位

- `use_sorcerous_restoration(encounter_id, actor_id)`
  - 每长休周期一次；恢复不超过术士等级一半的已消耗术法点
```

- [ ] **Step 4: 跑术士相关测试与全量**

Run: `python3 -m pytest -q trpg-battle-system/test/test_class_feature_runtime_helpers.py trpg-battle-system/test/test_spell_slot_runtime.py trpg-battle-system/test/test_use_innate_sorcery.py trpg-battle-system/test/test_convert_spell_slot_to_sorcery_points.py trpg-battle-system/test/test_create_spell_slot_from_sorcery_points.py trpg-battle-system/test/test_use_sorcerous_restoration.py trpg-battle-system/test/test_spell_request.py trpg-battle-system/test/test_get_encounter_state.py`
Expected: PASS

Run: `python3 -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add \
  trpg-battle-system/tools/services/encounter/get_encounter_state.py \
  trpg-battle-system/test/test_get_encounter_state.py \
  trpg-battle-system/docs/llm-runtime-tool-guide.md \
  trpg-battle-system/docs/development-plan.md
git commit -m "docs: document sorcerer runtime tools"
```
