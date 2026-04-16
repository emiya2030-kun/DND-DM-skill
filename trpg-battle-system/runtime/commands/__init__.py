from runtime.commands.start_random_encounter import start_random_encounter
from runtime.commands.move_and_attack import move_and_attack
from runtime.commands.end_turn_and_advance import end_turn_and_advance
from runtime.commands.cast_spell import cast_spell

COMMAND_HANDLERS = {
    "start_random_encounter": start_random_encounter,
    "move_and_attack": move_and_attack,
    "end_turn_and_advance": end_turn_and_advance,
    "cast_spell": cast_spell,
}

__all__ = [
    "COMMAND_HANDLERS",
    "start_random_encounter",
    "move_and_attack",
    "end_turn_and_advance",
    "cast_spell",
]
