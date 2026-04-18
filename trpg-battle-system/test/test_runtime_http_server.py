from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from runtime.context import build_runtime_context
from runtime.http_server import build_runtime_handler_class
from runtime.http_server import ThreadingHTTPServer
from tools.models import Encounter, EncounterEntity, EncounterMap


class RuntimeHttpServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.context = build_runtime_context(data_dir=Path(self.temp_dir.name))
        handler_cls = build_runtime_handler_class(runtime_context=self.context)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.context.close()
        self.temp_dir.cleanup()

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, object] | None = None,
    ) -> tuple[int, dict[str, object]]:
        headers = {}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")

        request = Request(f"{self.base_url}{path}", data=data, method=method, headers=headers)
        try:
            with urlopen(request, timeout=5) as response:
                body = response.read().decode("utf-8")
                return response.status, json.loads(body)
        except HTTPError as error:
            body = error.read().decode("utf-8")
            return error.code, json.loads(body)

    def _request_raw(
        self,
        method: str,
        path: str,
        *,
        body: bytes,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, payload
        finally:
            connection.close()

    def _seed_attack_encounter(self) -> None:
        actor = EncounterEntity(
            entity_id="ent_ally_eric_001",
            name="Eric",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 2, "y": 2},
            hp={"current": 20, "max": 20, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=15,
            ability_mods={"str": 1, "dex": 3, "con": 1, "int": 0, "wis": 0, "cha": 2},
            proficiency_bonus=2,
            weapons=[
                {
                    "weapon_id": "rapier",
                    "name": "Rapier",
                    "attack_bonus": 5,
                    "damage": [{"formula": "1d8+3", "type": "piercing"}],
                    "properties": ["finesse"],
                    "range": {"normal": 5, "long": 5},
                }
            ],
        )
        target = EncounterEntity(
            entity_id="ent_enemy_goblin_001",
            name="Goblin",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 3, "y": 2},
            hp={"current": 9, "max": 9, "temp": 0},
            ac=13,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
        )
        encounter = Encounter(
            encounter_id="enc_execute_attack_test",
            name="Execute Attack Test Encounter",
            status="active",
            round=1,
            current_entity_id=actor.entity_id,
            turn_order=[actor.entity_id, target.entity_id],
            entities={actor.entity_id: actor, target.entity_id: target},
            map=EncounterMap(
                map_id="map_execute_attack_test",
                name="Execute Attack Test Map",
                description="A small combat room.",
                width=8,
                height=8,
            ),
        )
        self.context.encounter_repository.save(encounter)

    def test_health_endpoint_returns_ok_payload(self) -> None:
        status, payload = self._request("GET", "/runtime/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("commands", payload)
        self.assertIn("execute_attack", payload["commands"])
        self.assertIn("move_entity", payload["commands"])

    def test_unknown_command_returns_structured_json_payload(self) -> None:
        status, payload = self._request(
            "POST",
            "/runtime/command",
            payload={"command": "unknown_command", "args": {"encounter_id": "enc_missing"}},
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "unknown_command")

    def test_command_endpoint_preserves_rule_context_in_error_payload(self) -> None:
        with patch(
            "runtime.http_server.execute_runtime_command",
            return_value={
                "ok": False,
                "command": "cast_spell",
                "error_code": "spell_slot_cast_already_used_this_turn",
                "message": "本回合已通过自身施法消耗过一次法术位。",
                "rule_context": {
                    "casting_source": "self_spellcasting",
                    "reaction_spell_exception": True,
                },
            },
        ):
            status, payload = self._request(
                "POST",
                "/runtime/command",
                payload={"command": "cast_spell", "args": {"encounter_id": "enc_test"}},
            )

        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "spell_slot_cast_already_used_this_turn")
        self.assertEqual(
            payload["rule_context"],
            {
                "casting_source": "self_spellcasting",
                "reaction_spell_exception": True,
            },
        )

    def test_execute_attack_command_hits_and_returns_updated_encounter_state(self) -> None:
        self._seed_attack_encounter()

        with patch("tools.services.combat.attack.execute_attack.random.randint", side_effect=[12, 4]):
            status, payload = self._request(
                "POST",
                "/runtime/command",
                payload={
                    "command": "execute_attack",
                    "args": {
                        "encounter_id": "enc_execute_attack_test",
                        "actor_id": "ent_ally_eric_001",
                        "target_id": "ent_enemy_goblin_001",
                        "weapon_id": "rapier",
                    },
                },
            )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "execute_attack")
        self.assertTrue(payload["result"]["attack_result"]["resolution"]["hit"])
        self.assertEqual(payload["result"]["attack_result"]["roll_result"]["final_total"], 17)
        self.assertEqual(payload["result"]["attack_result"]["resolution"]["hp_update"]["hp_after"], 2)

        updated = self.context.encounter_repository.get("enc_execute_attack_test")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 2)

    def test_encounter_state_requires_encounter_id_and_returns_json_error(self) -> None:
        status, payload = self._request("GET", "/runtime/encounter-state")
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "invalid_request")

    def test_command_endpoint_rejects_malformed_json_with_stable_json_error(self) -> None:
        status, payload = self._request_raw(
            "POST",
            "/runtime/command",
            body=b"{",
            headers={"Content-Type": "application/json", "Content-Length": "1"},
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "invalid_json")

    def test_command_endpoint_rejects_non_object_args(self) -> None:
        status, payload = self._request(
            "POST",
            "/runtime/command",
            payload={"command": "start_random_encounter", "args": []},
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "invalid_request")
        self.assertEqual(payload["message"], "args must be an object")

    def test_command_end_turn_and_advance_missing_encounter_id_returns_command_error_payload(self) -> None:
        status, payload = self._request(
            "POST",
            "/runtime/command",
            payload={"command": "end_turn_and_advance", "args": {}},
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "end_turn_and_advance")
        self.assertEqual(payload["error_code"], "encounter_id is required")

    def test_command_endpoint_rejects_invalid_content_length_with_stable_json_error(self) -> None:
        status, payload = self._request_raw(
            "POST",
            "/runtime/command",
            body=b"{}",
            headers={"Content-Type": "application/json", "Content-Length": "abc"},
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "invalid_request")

    def test_command_execution_unexpected_exception_returns_internal_error_json(self) -> None:
        with patch("runtime.http_server.execute_runtime_command", side_effect=RuntimeError("boom")):
            status, payload = self._request(
                "POST",
                "/runtime/command",
                payload={"command": "start_random_encounter", "args": {}},
            )

        self.assertEqual(status, 500)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "internal_error")
