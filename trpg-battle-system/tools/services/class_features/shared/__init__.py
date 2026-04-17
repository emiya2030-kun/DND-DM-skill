from tools.services.class_features.shared.extra_attack import resolve_extra_attack_count
from tools.services.class_features.rogue import ensure_rogue_runtime, resolve_rogue_sneak_attack_dice
from tools.services.class_features.shared.proficiency_resolver import (
    resolve_entity_proficiencies,
    resolve_entity_save_proficiencies,
    resolve_entity_skill_proficiencies,
)
from tools.services.class_features.shared.martial_feature_options import (
    normalize_class_feature_options,
)
from tools.services.class_features.shared.runtime import (
    ensure_barbarian_runtime,
    ensure_class_runtime,
    ensure_fighter_runtime,
    ensure_monk_runtime,
    get_barbarian_runtime,
    get_class_runtime,
    get_fighter_runtime,
    get_monk_runtime,
)
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
    "ensure_barbarian_runtime",
    "ensure_class_runtime",
    "ensure_fighter_runtime",
    "ensure_monk_runtime",
    "ensure_rogue_runtime",
    "fighter_has_studied_attacks",
    "get_barbarian_runtime",
    "get_unconsumed_studied_attack_mark",
    "get_class_runtime",
    "get_fighter_runtime",
    "get_monk_runtime",
    "has_unconsumed_studied_attack_mark",
    "normalize_class_feature_options",
    "resolve_extra_attack_count",
    "resolve_entity_proficiencies",
    "resolve_entity_save_proficiencies",
    "resolve_entity_skill_proficiencies",
    "resolve_rogue_sneak_attack_dice",
]
