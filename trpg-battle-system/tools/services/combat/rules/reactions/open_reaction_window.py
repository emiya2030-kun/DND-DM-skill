from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from tools.models import Encounter
from tools.services.combat.rules.reactions.collect_reaction_candidates import CollectReactionCandidates

if TYPE_CHECKING:
    from tools.repositories import EncounterRepository
    from tools.repositories.reaction_definition_repository import ReactionDefinitionRepository


class OpenReactionWindow:
    def __init__(
        self,
        encounter_repository: "EncounterRepository",
        definition_repository: "ReactionDefinitionRepository",
    ) -> None:
        self.encounter_repository = encounter_repository
        self.collect_candidates = CollectReactionCandidates(encounter_repository, definition_repository)

    def execute(self, *, encounter_id: str, trigger_event: dict[str, Any]) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        candidates = self.collect_candidates.execute(encounter=encounter, trigger_event=trigger_event)
        if not candidates:
            return {"status": "no_window_opened", "pending_reaction_window": None, "reaction_requests": []}

        groups_by_actor: dict[str, dict[str, Any]] = {}
        requests: list[dict[str, Any]] = []
        trigger_type = str(trigger_event.get("trigger_type"))
        trigger_event_id = trigger_event.get("event_id")
        target_entity_id = trigger_event.get("target_entity_id")
        request_payloads = trigger_event.get("request_payloads")
        payload_map = request_payloads if isinstance(request_payloads, dict) else {}
        request_overrides = trigger_event.get("request_overrides")
        override_map = request_overrides if isinstance(request_overrides, dict) else {}

        host_snapshot = dict(trigger_event.get("host_action_snapshot", {}))

        for index, candidate in enumerate(candidates, start=1):
            actor_id = str(candidate["actor_entity_id"])
            definition = dict(candidate["reaction_definition"])
            override = override_map.get(actor_id)
            ask_player = True
            auto_resolve = False
            if isinstance(override, dict):
                if "ask_player" in override:
                    ask_player = bool(override["ask_player"])
                if "auto_resolve" in override:
                    auto_resolve = bool(override["auto_resolve"])
            group = groups_by_actor.setdefault(
                actor_id,
                {
                    "group_id": f"rg_{actor_id}",
                    "actor_entity_id": actor_id,
                    "ask_player": ask_player,
                    "auto_resolve": auto_resolve,
                    "status": "pending",
                    "resource_pool": self._resolve_resource_pool(definition),
                    "group_priority": 100,
                    "trigger_sequence": index,
                    "relationship_rank": 1,
                    "tie_break_key": actor_id,
                    "options": [],
                },
            )
            reaction_type = definition["reaction_type"]
            template_type = definition.get("template_type", "generic_reaction")
            request_id = f"react_{uuid4().hex[:12]}"
            payload = {}
            if isinstance(override, dict) and isinstance(override.get("payload"), dict):
                payload = dict(override["payload"])
            elif actor_id in payload_map:
                actor_payload = payload_map.get(actor_id, {})
                if isinstance(actor_payload, dict):
                    typed_payload = actor_payload.get(reaction_type)
                    if isinstance(typed_payload, dict):
                        payload = dict(typed_payload)
                    else:
                        payload = dict(actor_payload)
            request_data = {
                "request_id": request_id,
                "status": "pending",
                "reaction_type": reaction_type,
                "template_type": template_type,
                "trigger_type": trigger_type,
                "trigger_event_id": trigger_event_id,
                "actor_entity_id": actor_id,
                "target_entity_id": target_entity_id,
                "ask_player": True,
                "auto_resolve": False,
                "resource_cost": definition.get("resource_cost", {}),
                "priority": 100,
                "payload": payload,
            }
            if isinstance(override, dict):
                for key, value in override.items():
                    if key in {"request_id", "status", "payload"}:
                        continue
                    request_data[key] = value
            requests.append(
                request_data
            )
            option_id = f"opt_{request_id}"
            group["options"].append(
                {
                    "option_id": option_id,
                    "reaction_type": reaction_type,
                    "template_type": template_type,
                    "request_id": request_id,
                    "label": definition.get("name", reaction_type),
                    "status": "pending",
                }
            )

        group_values = list(groups_by_actor.values())
        pending_window = {
            "window_id": f"rw_{trigger_event_id}",
            "status": "waiting_reaction",
            "trigger_event_id": trigger_event_id,
            "trigger_type": trigger_type,
            "blocking": True,
            "host_action_type": trigger_event.get("host_action_type"),
            "host_action_id": trigger_event.get("host_action_id"),
            "host_action_snapshot": host_snapshot,
            "choice_groups": group_values,
            "resolved_group_ids": [],
        }

        encounter.reaction_requests.extend(requests)
        encounter.pending_reaction_window = pending_window
        self.encounter_repository.save(encounter)
        return {
            "status": "waiting_reaction",
            "pending_reaction_window": pending_window,
            "reaction_requests": requests,
        }

    def _resolve_resource_pool(self, definition: dict[str, Any]) -> str:
        resource_cost = definition.get("resource_cost")
        if isinstance(resource_cost, dict):
            if bool(resource_cost.get("reaction")):
                return "reaction"
            if resource_cost.get("class_feature"):
                return "class_feature"
        return "reaction"

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter
