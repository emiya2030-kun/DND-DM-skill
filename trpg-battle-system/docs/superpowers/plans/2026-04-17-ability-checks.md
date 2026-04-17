# Ability Checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `trpg-battle-system` 增加一条可在战斗内外复用的属性检定 / 技能检定能力链，并暴露给 runtime 作为高层命令入口。

**Architecture:** 沿用现有 attack / save spell 的分层模式，新增 `checks` 服务包，拆成 `AbilityCheckRequest`、`ResolveAbilityCheck`、`AbilityCheckResult`、`ExecuteAbilityCheck` 四层。第一版只支持单实体标准 d20 检定，LLM 负责理解玩家自然语言并传入标准化的 `check_type + check + dc`，后端负责别名归一、掷骰、修正值、成功失败判断、事件记录和可选的 `encounter_state` 返回。

**Tech Stack:** Python 3.9, TinyDB repository, unittest, runtime command dispatcher

---

### Task 1: 建立属性检定的标准化目录与请求层

**Files:**
- Create: `tools/services/checks/__init__.py`
- Create: `tools/services/checks/check_catalog.py`
- Create: `tools/services/checks/ability_check_request.py`
- Modify: `tools/services/__init__.py`
- Test: `test/test_ability_check_request.py`

- [ ] **Step 1: Write the failing request-layer tests**

```python
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository
from tools.services import AbilityCheckRequest


def build_actor() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_ally_sabur_001",
        name="Sabur",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 21, "max": 21, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=14,
        ability_mods={"str": 1, "dex": 3, "wis": 2},
        proficiency_bonus=2,
        skill_modifiers={"stealth": 5},
        save_proficiencies=["dex"],
    )


def build_encounter() -> Encounter:
    actor = build_actor()
    return Encounter(
        encounter_id="enc_ability_check_test",
        name="Ability Check Test",
        status="active",
        round=1,
        current_entity_id=actor.entity_id,
        turn_order=[actor.entity_id],
        entities={actor.entity_id: actor},
        map=EncounterMap(
            map_id="map_ability_check_test",
            name="Ability Check Test Map",
            description="Ability check room.",
            width=6,
            height=6,
        ),
    )


class AbilityCheckRequestTests(unittest.TestCase):
    def test_execute_builds_skill_check_request_with_alias_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            request = AbilityCheckRequest(repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="skill",
                check="潜行",
                dc=15,
                vantage="advantage",
                reason="Sabur hides behind the wall",
            )

            self.assertEqual(request.roll_type, "ability_check")
            self.assertEqual(request.actor_entity_id, "ent_ally_sabur_001")
            self.assertEqual(request.formula, "1d20+check_modifier")
            self.assertEqual(request.context["check_type"], "skill")
            self.assertEqual(request.context["check"], "stealth")
            self.assertEqual(request.context["dc"], 15)
            self.assertEqual(request.context["vantage"], "advantage")
            repo.close()

    def test_execute_builds_ability_check_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            request = AbilityCheckRequest(repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="ability",
                check="力量",
                dc=12,
            )

            self.assertEqual(request.context["check_type"], "ability")
            self.assertEqual(request.context["check"], "str")
            repo.close()

    def test_execute_rejects_unknown_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            with self.assertRaisesRegex(ValueError, "unknown_skill_check"):
                AbilityCheckRequest(repo).execute(
                    encounter_id="enc_ability_check_test",
                    actor_id="ent_ally_sabur_001",
                    check_type="skill",
                    check="潜伏术",
                    dc=15,
                )
            repo.close()

    def test_execute_requires_integer_dc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            with self.assertRaisesRegex(ValueError, "dc must be an integer"):
                AbilityCheckRequest(repo).execute(
                    encounter_id="enc_ability_check_test",
                    actor_id="ent_ally_sabur_001",
                    check_type="skill",
                    check="stealth",
                    dc="15",
                )
            repo.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_ability_check_request -v`
Expected: FAIL with import errors because `AbilityCheckRequest` and `checks` package do not exist yet

- [ ] **Step 3: Write minimal catalog and request implementation**

```python
# tools/services/checks/check_catalog.py
ABILITY_ALIASES = {
    "str": "str",
    "strength": "str",
    "力量": "str",
    "dex": "dex",
    "dexterity": "dex",
    "敏捷": "dex",
    "con": "con",
    "constitution": "con",
    "体质": "con",
    "int": "int",
    "intelligence": "int",
    "智力": "int",
    "wis": "wis",
    "wisdom": "wis",
    "感知": "wis",
    "cha": "cha",
    "charisma": "cha",
    "魅力": "cha",
}

SKILL_ALIASES = {
    "athletics": "athletics",
    "运动": "athletics",
    "acrobatics": "acrobatics",
    "特技": "acrobatics",
    "animal handling": "animal_handling",
    "animal_handling": "animal_handling",
    "驯兽": "animal_handling",
    "arcana": "arcana",
    "奥秘": "arcana",
    "deception": "deception",
    "欺瞒": "deception",
    "history": "history",
    "历史": "history",
    "insight": "insight",
    "洞悉": "insight",
    "intimidation": "intimidation",
    "威吓": "intimidation",
    "investigation": "investigation",
    "调查": "investigation",
    "medicine": "medicine",
    "医药": "medicine",
    "nature": "nature",
    "自然": "nature",
    "perception": "perception",
    "察觉": "perception",
    "performance": "performance",
    "表演": "performance",
    "persuasion": "persuasion",
    "游说": "persuasion",
    "religion": "religion",
    "宗教": "religion",
    "sleight of hand": "sleight_of_hand",
    "sleight_of_hand": "sleight_of_hand",
    "巧手": "sleight_of_hand",
    "stealth": "stealth",
    "潜行": "stealth",
    "隐匿": "stealth",
    "survival": "survival",
    "求生": "survival",
}

SKILL_TO_ABILITY = {
    "athletics": "str",
    "acrobatics": "dex",
    "animal_handling": "wis",
    "arcana": "int",
    "deception": "cha",
    "history": "int",
    "insight": "wis",
    "intimidation": "cha",
    "investigation": "int",
    "medicine": "wis",
    "nature": "int",
    "perception": "wis",
    "performance": "cha",
    "persuasion": "cha",
    "religion": "int",
    "sleight_of_hand": "dex",
    "stealth": "dex",
    "survival": "wis",
}

def normalize_check_name(check_type: str, raw_check: str) -> str:
    normalized = raw_check.strip().lower()
    if check_type == "ability":
        result = ABILITY_ALIASES.get(normalized)
        if result is None:
            raise ValueError("unknown_ability_check")
        return result
    if check_type == "skill":
        result = SKILL_ALIASES.get(normalized)
        if result is None:
            raise ValueError("unknown_skill_check")
        return result
    raise ValueError("check_type must be 'ability' or 'skill'")
```

```python
# tools/services/checks/ability_check_request.py
from uuid import uuid4

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.models.roll_request import RollRequest
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.checks.check_catalog import normalize_check_name


class AbilityCheckRequest:
    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        check_type: str,
        check: str,
        dc: int,
        vantage: str = "normal",
        reason: str | None = None,
    ) -> RollRequest:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_entity_or_raise(encounter, actor_id)
        if not isinstance(dc, int):
            raise ValueError("dc must be an integer")
        if vantage not in {"normal", "advantage", "disadvantage"}:
            raise ValueError("vantage must be 'normal', 'advantage', or 'disadvantage'")
        normalized_check_type = str(check_type).strip().lower()
        normalized_check = normalize_check_name(normalized_check_type, str(check))
        return RollRequest(
            request_id=f"req_check_{uuid4().hex[:12]}",
            encounter_id=encounter.encounter_id,
            actor_entity_id=actor.entity_id,
            roll_type="ability_check",
            formula="1d20+check_modifier",
            reason=reason or f"{actor.name} makes a {normalized_check_type} check",
            context={
                "check_type": normalized_check_type,
                "check": normalized_check,
                "dc": dc,
                "vantage": vantage,
            },
        )
```

```python
# tools/services/checks/__init__.py
from tools.services.checks.ability_check_request import AbilityCheckRequest

__all__ = ["AbilityCheckRequest"]
```

```python
# tools/services/__init__.py
__all__ = [
    ...
    "AbilityCheckRequest",
]

_LAZY_EXPORTS = {
    ...
    "AbilityCheckRequest": ("tools.services.checks.ability_check_request", "AbilityCheckRequest"),
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest test.test_ability_check_request -v`
Expected: PASS with all request normalization tests green

- [ ] **Step 5: Commit**

```bash
git add tools/services/checks/__init__.py tools/services/checks/check_catalog.py tools/services/checks/ability_check_request.py tools/services/__init__.py test/test_ability_check_request.py
git commit -m "feat: add ability check request normalization"
```

### Task 2: 实现检定总值结算层

**Files:**
- Create: `tools/services/checks/resolve_ability_check.py`
- Modify: `tools/services/checks/__init__.py`
- Test: `test/test_resolve_ability_check.py`

- [ ] **Step 1: Write the failing resolve-layer tests**

```python
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.repositories import EncounterRepository
from tools.services import AbilityCheckRequest, ResolveAbilityCheck
from test.test_ability_check_request import build_encounter


class ResolveAbilityCheckTests(unittest.TestCase):
    def test_execute_uses_skill_modifier_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())
            request = AbilityCheckRequest(repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="skill",
                check="隐匿",
                dc=15,
            )

            result = ResolveAbilityCheck(repo).execute(
                encounter_id="enc_ability_check_test",
                roll_request=request,
                base_roll=12,
            )

            self.assertEqual(result.final_total, 17)
            self.assertEqual(result.metadata["check_bonus"], 5)
            self.assertEqual(result.metadata["check_bonus_breakdown"]["source"], "skill_modifier")
            repo.close()

    def test_execute_falls_back_to_ability_plus_proficiency_for_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.entities["ent_ally_sabur_001"].skill_modifiers = {}
            encounter.entities["ent_ally_sabur_001"].source_ref["skill_proficiencies"] = ["perception"]
            repo.save(encounter)
            request = AbilityCheckRequest(repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="skill",
                check="察觉",
                dc=13,
            )

            result = ResolveAbilityCheck(repo).execute(
                encounter_id="enc_ability_check_test",
                roll_request=request,
                base_roll=10,
            )

            self.assertEqual(result.final_total, 14)
            self.assertEqual(result.metadata["check_bonus_breakdown"]["ability_modifier"], 2)
            self.assertTrue(result.metadata["check_bonus_breakdown"]["is_proficient"])
            repo.close()

    def test_execute_supports_advantage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())
            request = AbilityCheckRequest(repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="ability",
                check="dex",
                dc=14,
                vantage="advantage",
            )

            result = ResolveAbilityCheck(repo).execute(
                encounter_id="enc_ability_check_test",
                roll_request=request,
                base_rolls=[4, 17],
                additional_bonus=1,
            )

            self.assertEqual(result.metadata["vantage"], "advantage")
            self.assertEqual(result.metadata["chosen_roll"], 17)
            self.assertEqual(result.final_total, 21)
            repo.close()

    def test_execute_applies_exhaustion_penalty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.entities["ent_ally_sabur_001"].conditions = ["exhaustion:2"]
            repo.save(encounter)
            request = AbilityCheckRequest(repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="ability",
                check="wis",
                dc=10,
            )

            result = ResolveAbilityCheck(repo).execute(
                encounter_id="enc_ability_check_test",
                roll_request=request,
                base_roll=14,
            )

            self.assertEqual(result.final_total, 12)
            self.assertEqual(result.metadata["d20_penalty"], 4)
            repo.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_resolve_ability_check -v`
Expected: FAIL because `ResolveAbilityCheck` does not exist

- [ ] **Step 3: Write minimal resolver implementation**

```python
# tools/services/checks/resolve_ability_check.py
from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.models.roll_request import RollRequest
from tools.models.roll_result import RollResult
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.checks.check_catalog import SKILL_TO_ABILITY
from tools.services.class_features.shared import resolve_entity_skill_proficiencies
from tools.services.combat.rules.conditions import ConditionRuntime
from tools.services.combat.rules.conditions.condition_parser import parse_condition


class ResolveAbilityCheck:
    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository

    def execute(
        self,
        *,
        encounter_id: str,
        roll_request: RollRequest,
        base_roll: int | None = None,
        base_rolls: list[int] | None = None,
        additional_bonus: int = 0,
        metadata: dict[str, Any] | None = None,
        rolled_at: str | None = None,
    ) -> RollResult:
        encounter = self._get_encounter_or_raise(encounter_id)
        self._validate_roll_request(encounter_id, roll_request)
        actor = self._get_entity_or_raise(encounter, roll_request.actor_entity_id)

        check_type = str(roll_request.context["check_type"])
        check = str(roll_request.context["check"])
        requested_vantage = str(roll_request.context.get("vantage", "normal"))
        rolls = self._normalize_base_rolls(base_roll, base_rolls)
        self._ensure_roll_count_for_vantage(rolls, requested_vantage)
        chosen_roll = self._choose_roll(rolls, requested_vantage)
        runtime = self._safe_condition_runtime(actor.conditions)
        exhaustion_penalty = runtime.get_d20_penalty()
        check_bonus, breakdown = self._resolve_bonus(
            actor=actor,
            check_type=check_type,
            check=check,
            additional_bonus=additional_bonus,
        )
        final_total = chosen_roll + check_bonus - exhaustion_penalty

        merged_metadata = dict(metadata or {})
        merged_metadata.update(
            {
                "check_type": check_type,
                "check": check,
                "vantage": requested_vantage,
                "chosen_roll": chosen_roll,
                "check_bonus": check_bonus,
                "check_bonus_breakdown": breakdown,
                "d20_penalty": exhaustion_penalty,
            }
        )

        return RollResult(
            request_id=roll_request.request_id,
            encounter_id=encounter_id,
            actor_entity_id=actor.entity_id,
            roll_type="ability_check",
            final_total=final_total,
            dice_rolls={
                "base_rolls": rolls,
                "chosen_roll": chosen_roll,
                "check_bonus": check_bonus,
                "additional_bonus": additional_bonus,
                "d20_penalty": exhaustion_penalty,
            },
            metadata=merged_metadata,
            rolled_at=rolled_at,
        )

    def _resolve_bonus(self, *, actor: EncounterEntity, check_type: str, check: str, additional_bonus: int) -> tuple[int, dict[str, Any]]:
        if check_type == "ability":
            ability_modifier = int(actor.ability_mods.get(check, 0))
            return ability_modifier + additional_bonus, {
                "source": "ability_modifier",
                "ability": check,
                "ability_modifier": ability_modifier,
                "additional_bonus": additional_bonus,
            }

        if check in actor.skill_modifiers and isinstance(actor.skill_modifiers[check], int):
            skill_modifier = int(actor.skill_modifiers[check])
            return skill_modifier + additional_bonus, {
                "source": "skill_modifier",
                "skill_modifier": skill_modifier,
                "additional_bonus": additional_bonus,
            }

        ability = SKILL_TO_ABILITY[check]
        ability_modifier = int(actor.ability_mods.get(ability, 0))
        is_proficient = check in resolve_entity_skill_proficiencies(actor)
        proficiency_bonus = int(actor.proficiency_bonus) if is_proficient else 0
        total = ability_modifier + proficiency_bonus + additional_bonus
        return total, {
            "source": "ability_plus_proficiency",
            "ability": ability,
            "ability_modifier": ability_modifier,
            "is_proficient": is_proficient,
            "proficiency_bonus_applied": proficiency_bonus,
            "additional_bonus": additional_bonus,
        }
```

```python
# tools/services/checks/__init__.py
from tools.services.checks.ability_check_request import AbilityCheckRequest
from tools.services.checks.resolve_ability_check import ResolveAbilityCheck

__all__ = ["AbilityCheckRequest", "ResolveAbilityCheck"]
```

```python
# tools/services/__init__.py
__all__ = [
    ...
    "ResolveAbilityCheck",
]

_LAZY_EXPORTS = {
    ...
    "ResolveAbilityCheck": ("tools.services.checks.resolve_ability_check", "ResolveAbilityCheck"),
}
```

If `resolve_entity_skill_proficiencies` does not exist yet, add it in `tools/services/class_features/shared/proficiency_resolver.py` and export it from `tools/services/class_features/shared/__init__.py`:

```python
def resolve_entity_skill_proficiencies(entity: Any) -> list[str]:
    source_ref = entity.source_ref if hasattr(entity, "source_ref") else entity.get("source_ref", {})
    values = source_ref.get("skill_proficiencies", [])
    return [str(item).strip().lower() for item in values if str(item).strip()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest test.test_resolve_ability_check -v`
Expected: PASS with skill modifier, fallback proficiency, advantage, and exhaustion cases green

- [ ] **Step 5: Commit**

```bash
git add tools/services/checks/__init__.py tools/services/checks/resolve_ability_check.py tools/services/__init__.py tools/services/class_features/shared/proficiency_resolver.py tools/services/class_features/shared/__init__.py test/test_resolve_ability_check.py
git commit -m "feat: resolve ability check totals"
```

### Task 3: 实现结果层与高层执行入口

**Files:**
- Create: `tools/services/checks/ability_check_result.py`
- Create: `tools/services/checks/execute_ability_check.py`
- Modify: `tools/services/checks/__init__.py`
- Modify: `tools/services/__init__.py`
- Test: `test/test_ability_check_result.py`
- Test: `test/test_execute_ability_check.py`

- [ ] **Step 1: Write the failing result and execute tests**

```python
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.repositories import EncounterRepository, EventRepository
from tools.services import (
    AbilityCheckRequest,
    AbilityCheckResult,
    AppendEvent,
    ExecuteAbilityCheck,
    ResolveAbilityCheck,
)
from test.test_ability_check_request import build_encounter


class AbilityCheckResultTests(unittest.TestCase):
    def test_execute_returns_success_comparison_and_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            request = AbilityCheckRequest(encounter_repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="skill",
                check="stealth",
                dc=15,
            )
            roll_result = ResolveAbilityCheck(encounter_repo).execute(
                encounter_id="enc_ability_check_test",
                roll_request=request,
                base_roll=12,
            )

            result = AbilityCheckResult(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
            ).execute(
                encounter_id="enc_ability_check_test",
                roll_request=request,
                roll_result=roll_result,
            )

            self.assertTrue(result["success"])
            self.assertFalse(result["failed"])
            self.assertEqual(result["comparison"]["left_label"], "ability_check_total")
            self.assertEqual(result["comparison"]["right_value"], 15)
            self.assertIsInstance(result["event_id"], str)
            encounter_repo.close()
            event_repo.close()


class ExecuteAbilityCheckTests(unittest.TestCase):
    def test_execute_auto_rolls_and_returns_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            result = ExecuteAbilityCheck(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
            ).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="skill",
                check="察觉",
                dc=13,
                include_encounter_state=True,
            )

            self.assertEqual(result["check"], "察觉")
            self.assertEqual(result["normalized_check"], "perception")
            self.assertIn("roll_result", result)
            self.assertIn("encounter_state", result)
            self.assertEqual(result["encounter_state"]["encounter_id"], "enc_ability_check_test")
            encounter_repo.close()
            event_repo.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_ability_check_result test.test_execute_ability_check -v`
Expected: FAIL because `AbilityCheckResult` and `ExecuteAbilityCheck` do not exist

- [ ] **Step 3: Write minimal result and execute implementation**

```python
# tools/services/checks/ability_check_result.py
from typing import Any

from tools.models.roll_request import RollRequest
from tools.models.roll_result import RollResult
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.events.append_event import AppendEvent


class AbilityCheckResult:
    def __init__(self, encounter_repository: EncounterRepository, append_event: AppendEvent):
        self.encounter_repository = encounter_repository
        self.append_event = append_event

    def execute(
        self,
        *,
        encounter_id: str,
        roll_request: RollRequest,
        roll_result: RollResult,
    ) -> dict[str, Any]:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        dc = roll_request.context.get("dc")
        if not isinstance(dc, int):
            raise ValueError("roll_request.context.dc must be an integer")
        success = roll_result.final_total >= dc
        payload = {
            "encounter_id": encounter_id,
            "actor_id": roll_result.actor_entity_id,
            "check_type": roll_request.context["check_type"],
            "check": roll_request.context["check"],
            "dc": dc,
            "final_total": roll_result.final_total,
            "success": success,
            "failed": not success,
            "vantage": roll_result.metadata.get("vantage"),
            "chosen_roll": roll_result.metadata.get("chosen_roll"),
            "bonus_breakdown": roll_result.metadata.get("check_bonus_breakdown"),
            "comparison": {
                "left_label": "ability_check_total",
                "left_value": roll_result.final_total,
                "operator": ">=",
                "right_label": "dc",
                "right_value": dc,
                "passed": success,
            },
        }
        event = self.append_event.execute(
            encounter_id=encounter_id,
            round=encounter.round,
            event_type="ability_check_resolved",
            actor_entity_id=roll_result.actor_entity_id,
            target_entity_id=None,
            request_id=roll_request.request_id,
            payload=payload,
        )
        payload["event_id"] = event.event_id
        return payload
```

```python
# tools/services/checks/execute_ability_check.py
import random
from typing import Any

from tools.repositories.encounter_repository import EncounterRepository
from tools.repositories.event_repository import EventRepository
from tools.services.checks.ability_check_request import AbilityCheckRequest
from tools.services.checks.ability_check_result import AbilityCheckResult
from tools.services.checks.resolve_ability_check import ResolveAbilityCheck
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent


class ExecuteAbilityCheck:
    def __init__(
        self,
        encounter_repository: EncounterRepository,
        append_event: AppendEvent | None = None,
    ):
        self.encounter_repository = encounter_repository
        self.append_event = append_event or AppendEvent(EventRepository())
        self.request_service = AbilityCheckRequest(encounter_repository)
        self.resolve_service = ResolveAbilityCheck(encounter_repository)
        self.result_service = AbilityCheckResult(encounter_repository, self.append_event)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        check_type: str,
        check: str,
        dc: int,
        vantage: str = "normal",
        additional_bonus: int = 0,
        reason: str | None = None,
        include_encounter_state: bool = False,
    ) -> dict[str, Any]:
        request = self.request_service.execute(
            encounter_id=encounter_id,
            actor_id=actor_id,
            check_type=check_type,
            check=check,
            dc=dc,
            vantage=vantage,
            reason=reason,
        )
        base_rolls = [random.randint(1, 20)]
        if vantage in {"advantage", "disadvantage"}:
            base_rolls.append(random.randint(1, 20))
        roll_result = self.resolve_service.execute(
            encounter_id=encounter_id,
            roll_request=request,
            base_rolls=base_rolls,
            additional_bonus=additional_bonus,
        )
        outcome = self.result_service.execute(
            encounter_id=encounter_id,
            roll_request=request,
            roll_result=roll_result,
        )
        response = {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "check_type": check_type,
            "check": check,
            "normalized_check": request.context["check"],
            "request": request.to_dict(),
            "roll_result": roll_result.to_dict(),
            **outcome,
        }
        if include_encounter_state:
            response["encounter_state"] = GetEncounterState(self.encounter_repository).execute(encounter_id)
        return response
```

```python
# tools/services/checks/__init__.py
from tools.services.checks.ability_check_request import AbilityCheckRequest
from tools.services.checks.ability_check_result import AbilityCheckResult
from tools.services.checks.execute_ability_check import ExecuteAbilityCheck
from tools.services.checks.resolve_ability_check import ResolveAbilityCheck

__all__ = [
    "AbilityCheckRequest",
    "AbilityCheckResult",
    "ExecuteAbilityCheck",
    "ResolveAbilityCheck",
]
```

```python
# tools/services/__init__.py
__all__ = [
    ...
    "AbilityCheckResult",
    "ExecuteAbilityCheck",
]

_LAZY_EXPORTS = {
    ...
    "AbilityCheckResult": ("tools.services.checks.ability_check_result", "AbilityCheckResult"),
    "ExecuteAbilityCheck": ("tools.services.checks.execute_ability_check", "ExecuteAbilityCheck"),
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest test.test_ability_check_result test.test_execute_ability_check -v`
Expected: PASS with event payload and full-chain execute behavior green

- [ ] **Step 5: Commit**

```bash
git add tools/services/checks/__init__.py tools/services/checks/ability_check_result.py tools/services/checks/execute_ability_check.py tools/services/__init__.py test/test_ability_check_result.py test/test_execute_ability_check.py
git commit -m "feat: add ability check execution chain"
```

### Task 4: 暴露 runtime 命令并补集成回归

**Files:**
- Create: `runtime/commands/execute_ability_check.py`
- Modify: `runtime/commands/__init__.py`
- Test: `test/test_runtime_execute_ability_check.py`
- Modify: `test/test_runtime_dispatcher.py`

- [ ] **Step 1: Write the failing runtime tests**

```python
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.commands import COMMAND_HANDLERS
from runtime.context import build_runtime_context
from runtime.dispatcher import execute_runtime_command


class RuntimeExecuteAbilityCheckTests(unittest.TestCase):
    def test_command_handlers_include_execute_ability_check(self) -> None:
        self.assertIn("execute_ability_check", COMMAND_HANDLERS)

    def test_execute_ability_check_runs_and_returns_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                from test.test_ability_check_request import build_encounter

                context.encounter_repository.save(build_encounter())
                module = __import__("runtime.commands.execute_ability_check", fromlist=["execute_ability_check"])

                with patch.object(
                    module.ExecuteAbilityCheck,
                    "execute",
                    return_value={
                        "encounter_id": "enc_ability_check_test",
                        "actor_id": "ent_ally_sabur_001",
                        "normalized_check": "stealth",
                        "success": True,
                        "encounter_state": {"encounter_id": "enc_ability_check_test"},
                    },
                ) as mocked_execute:
                    result = execute_runtime_command(
                        context,
                        command="execute_ability_check",
                        args={
                            "encounter_id": "enc_ability_check_test",
                            "actor_id": "ent_ally_sabur_001",
                            "check_type": "skill",
                            "check": "隐匿",
                            "dc": 15,
                        },
                        handlers=COMMAND_HANDLERS,
                    )

                self.assertTrue(result["ok"])
                self.assertEqual(result["result"]["normalized_check"], "stealth")
                self.assertEqual(result["encounter_state"]["encounter_id"], "enc_ability_check_test")
                _, kwargs = mocked_execute.call_args
                self.assertEqual(kwargs["check_type"], "skill")
                self.assertEqual(kwargs["check"], "隐匿")
                self.assertEqual(kwargs["dc"], 15)
                self.assertTrue(kwargs["include_encounter_state"])
            finally:
                context.close()
```

Also extend `test/test_runtime_dispatcher.py` with:

```python
    def test_command_handlers_include_execute_ability_check(self) -> None:
        self.assertIn("execute_ability_check", COMMAND_HANDLERS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_runtime_execute_ability_check test.test_runtime_dispatcher -v`
Expected: FAIL because the runtime command is not registered yet

- [ ] **Step 3: Write minimal runtime command and handler registration**

```python
# runtime/commands/execute_ability_check.py
from __future__ import annotations

from typing import Any

from runtime.context import BattleRuntimeContext
from tools.services import AppendEvent, ExecuteAbilityCheck


def _require_arg(args: dict[str, object], key: str) -> object:
    value = args.get(key)
    if value is None:
        raise ValueError(f"{key} is required")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"{key} is required")
    return value


def execute_ability_check(context: BattleRuntimeContext, args: dict[str, object]) -> dict[str, Any]:
    encounter_id = str(_require_arg(args, "encounter_id"))
    actor_id = str(_require_arg(args, "actor_id"))
    check_type = str(_require_arg(args, "check_type"))
    check = str(_require_arg(args, "check"))
    dc = _require_arg(args, "dc")
    if isinstance(dc, bool) or not isinstance(dc, int):
        raise ValueError("dc must be an integer")

    service = ExecuteAbilityCheck(
        encounter_repository=context.encounter_repository,
        append_event=AppendEvent(context.event_repository),
    )
    result = service.execute(
        encounter_id=encounter_id,
        actor_id=actor_id,
        check_type=check_type,
        check=check,
        dc=dc,
        vantage=str(args.get("vantage") or "normal"),
        additional_bonus=int(args.get("additional_bonus") or 0),
        reason=args.get("reason"),
        include_encounter_state=True,
    )
    return {
        "encounter_id": encounter_id,
        "result": result,
        "encounter_state": result["encounter_state"],
    }
```

```python
# runtime/commands/__init__.py
from runtime.commands.execute_ability_check import execute_ability_check

COMMAND_HANDLERS = {
    ...
    "execute_ability_check": execute_ability_check,
}

__all__ = [
    ...
    "execute_ability_check",
]
```

- [ ] **Step 4: Run focused and full validation**

Run: `python3 -m unittest test.test_ability_check_request test.test_resolve_ability_check test.test_ability_check_result test.test_execute_ability_check test.test_runtime_execute_ability_check test.test_runtime_dispatcher -v`
Expected: PASS with all ability-check-focused tests green

Run: `python3 -m unittest discover -s test -v`
Expected: PASS with full suite green and no regressions in existing attack / spell / runtime flows

- [ ] **Step 5: Review diff and commit**

Run: `git diff -- tools/services/__init__.py tools/services/checks runtime/commands/__init__.py runtime/commands/execute_ability_check.py test/test_ability_check_request.py test/test_resolve_ability_check.py test/test_ability_check_result.py test/test_execute_ability_check.py test/test_runtime_execute_ability_check.py test/test_runtime_dispatcher.py`
Expected: only ability-check chain, exports, and runtime registration changes

```bash
git add tools/services/__init__.py tools/services/checks runtime/commands/__init__.py runtime/commands/execute_ability_check.py test/test_ability_check_request.py test/test_resolve_ability_check.py test/test_ability_check_result.py test/test_execute_ability_check.py test/test_runtime_execute_ability_check.py test/test_runtime_dispatcher.py
git commit -m "feat: expose ability checks through runtime"
```

## Self-Review

- Spec coverage:
  - 单实体 `ability/skill + dc`：Task 1-3 覆盖
  - 中英别名归一：Task 1 覆盖
  - 优势 / 劣势与力竭惩罚：Task 2 覆盖
  - `success / failed / comparison / event`：Task 3 覆盖
  - `include_encounter_state`：Task 3-4 覆盖
  - runtime 高层入口：Task 4 覆盖
  - 不做对抗检定 / 不做擒抱专用逻辑：本计划未引入相关 task，边界保持正确
- Placeholder scan:
  - 未使用 `TODO` / `TBD`
  - 每个 task 都包含具体文件、测试、命令和最小代码骨架
- Type consistency:
  - 对外统一使用 `check_type`, `check`, `dc`, `vantage`, `additional_bonus`
  - 内部统一 `roll_type="ability_check"`
  - 结果统一返回 `normalized_check` 和 `comparison`
