from runtime.commands.start_random_encounter import start_random_encounter
from runtime.commands.move_and_attack import move_and_attack
from runtime.commands.execute_attack import execute_attack
from runtime.commands.execute_ability_check import execute_ability_check
from runtime.commands.end_turn_and_advance import end_turn_and_advance
from runtime.commands.cast_spell import cast_spell
from runtime.commands.use_disengage import use_disengage
from runtime.commands.use_dodge import use_dodge
from runtime.commands.use_help_attack import use_help_attack
from runtime.commands.use_help_ability_check import use_help_ability_check

COMMAND_HANDLERS = {
    "start_random_encounter": start_random_encounter,
    "move_and_attack": move_and_attack,
    "execute_attack": execute_attack,
    "execute_ability_check": execute_ability_check,
    "end_turn_and_advance": end_turn_and_advance,
    "cast_spell": cast_spell,
    "use_disengage": use_disengage,
    "use_dodge": use_dodge,
    "use_help_attack": use_help_attack,
    "use_help_ability_check": use_help_ability_check,
}

__all__ = [
    "COMMAND_HANDLERS",
    "start_random_encounter",
    "move_and_attack",
    "execute_attack",
    "execute_ability_check",
    "end_turn_and_advance",
    "cast_spell",
    "use_disengage",
    "use_dodge",
    "use_help_attack",
    "use_help_ability_check",
]
