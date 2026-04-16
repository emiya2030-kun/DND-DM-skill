---
title: Open Reaction Window Heartbeat
date: 2026-04-16
---

# Goal

Define the minimal implementation for Task 3: collecting `attack_declared` reaction definitions and building a `pending_reaction_window` where an actor that satisfies multiple options appears once with a stack of choices. This work feeds into the broader reaction framework at the point where an attack is waiting for reaction choices such as `shield` or `absorb_elements`.

# Scope

- Support only the `attack_declared` trigger.
- Use the existing `ReactionDefinitionRepository` for static knowledge.
- Emit decision structures without touching movement, attack, or spell host flows beyond returning the resulting window data.
- Target the attack-triggered target (usually the defender) as the only actor eligible for these two options.
- Ensure the test demonstrates the grouping rule: same actor, multiple reactions.

# Approach

1. **CollectReactionCandidates**  
   - Hooks into `ReactionDefinitionRepository.list_by_trigger_type("attack_declared")`.
   - Uses the trigger event to find the attacked `target_entity_id`.
   - Returns entries shaped like `{"actor_entity_id": target_id, "reaction_definition": definition}`.
   - Allows future eligibility checks to live here once more data is available.

2. **OpenReactionWindow**  
   - Reads the encounter via `EncounterRepository` and augments it with the new requests/window in place.
   - Iterates the candidates, bucketed by `actor_entity_id`, so multiple definitions for the same defender become `options` under a single `choice_group`.
   - Builds `reaction_requests` to describe each option and appends them to the encounter so the rest of the framework can resolve them later.
   - Persists the encounter before returning a payload containing `pending_reaction_window`.
   - For this iteration, the window always returns `"status": "waiting_reaction"` because we only call this when a reaction is required.

# Data shapes

- `pending_reaction_window`
  - `window_id`: `rw_{event_id}`
  - `status`: `"waiting_reaction"`
  - `trigger_type`: passes through `"attack_declared"` from the trigger.
  - `host_action_snapshot`: carries the minimal attack context (actor, target, attack_total, phase).
  - `choice_groups`: list of groups keyed by actor.
  - `resolved_group_ids`: starts empty.

- `choice_group`
  - `group_id`: `rg_{actor_id}`
  - `actor_entity_id`: the defender.
  - `options`: each entry describes a reaction option (`shield`, `absorb_elements`), including the `request_id` pointer.

- `reaction_request`
  - `request_id`: `react_{actor_id}_{reaction_type}`
  - `status`: `"pending"`
  - `reaction_type`, `template_type`, `trigger_type`, `trigger_event_id`, `actor_entity_id`, `target_entity_id`, `resource_cost`.

# Test plan & TDD notes

1. **Write failure test**  
   - Build fresh encounter with one target entity and save it to `EncounterRepository`.
   - Call `OpenReactionWindow.execute` on an attack trigger where the target can cast both `shield` and `absorb_elements`.
   - Assert the result keeps a single group for the target and exposes both options.
   - Expect failure initially (ImportError / missing implementation).

2. **Implement minimal production code**  
   - Add the two services, update `tools/services/combat/rules/reactions/__init__.py`, and ensure `reaction_definitions.py` contains the `absorb_elements` definition.
   - Run the test again.

# Self-review checklist

- [x] No TODO/TBD placeholders in this spec.
- [x] Requirements stated explicitly so implementation can stay focused on `attack_declared`.
- [x] Data structures match what the encounter already snapshots (`pending_reaction_window`, `reaction_requests`).
