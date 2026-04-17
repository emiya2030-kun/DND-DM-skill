from tools.services.class_features.shared.extra_attack import resolve_extra_attack_count
from tools.services.class_features.shared.proficiency_resolver import resolve_entity_proficiencies
from tools.services.class_features.shared.runtime import ensure_fighter_runtime, get_fighter_runtime
from tools.services.class_features.shared.studied_attacks import (
    add_or_refresh_studied_attack_mark,
    consume_studied_attack_mark,
    fighter_has_studied_attacks,
    get_unconsumed_studied_attack_mark,
    has_unconsumed_studied_attack_mark,
)

__all__ = [
    "add_or_refresh_studied_attack_mark",
    "consume_studied_attack_mark",
    "ensure_fighter_runtime",
    "fighter_has_studied_attacks",
    "get_unconsumed_studied_attack_mark",
    "get_fighter_runtime",
    "has_unconsumed_studied_attack_mark",
    "resolve_extra_attack_count",
    "resolve_entity_proficiencies",
]
