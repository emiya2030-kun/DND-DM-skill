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
from tools.services.class_features.shared.fighting_styles import (
    has_fighting_style,
    resolve_fighting_style_ids,
)
from tools.services.class_features.shared.spell_slots import (
    build_available_spell_slots_view,
    consume_exact_spell_slot,
    consume_lowest_available_spell_slot,
    ensure_spell_slots_runtime,
    has_any_spell_slot,
    has_exact_spell_slot,
    restore_consumed_spell_slot,
)
from tools.services.class_features.shared.runtime import (
    ensure_barbarian_runtime,
    ensure_class_runtime,
    ensure_fighter_runtime,
    ensure_monk_runtime,
    ensure_paladin_runtime,
    ensure_ranger_runtime,
    ensure_warlock_runtime,
    get_barbarian_runtime,
    get_class_runtime,
    get_fighter_runtime,
    get_monk_runtime,
    get_paladin_runtime,
    get_ranger_runtime,
    get_warlock_runtime,
)
from tools.services.class_features.shared.studied_attacks import (
    add_or_refresh_studied_attack_mark,
    consume_studied_attack_mark,
    fighter_has_studied_attacks,
    get_unconsumed_studied_attack_mark,
    has_unconsumed_studied_attack_mark,
)
from tools.services.class_features.shared.warlock_invocations import (
    find_selected_warlock_invocation,
    get_selected_warlock_invocations,
    has_selected_warlock_invocation,
)

__all__ = [
    "add_or_refresh_studied_attack_mark",
    "consume_studied_attack_mark",
    "consume_exact_spell_slot",
    "consume_lowest_available_spell_slot",
    "build_available_spell_slots_view",
    "ensure_barbarian_runtime",
    "ensure_class_runtime",
    "ensure_fighter_runtime",
    "ensure_monk_runtime",
    "ensure_paladin_runtime",
    "ensure_ranger_runtime",
    "ensure_warlock_runtime",
    "ensure_spell_slots_runtime",
    "ensure_rogue_runtime",
    "fighter_has_studied_attacks",
    "find_selected_warlock_invocation",
    "get_barbarian_runtime",
    "get_unconsumed_studied_attack_mark",
    "get_class_runtime",
    "get_fighter_runtime",
    "get_monk_runtime",
    "get_paladin_runtime",
    "get_ranger_runtime",
    "get_selected_warlock_invocations",
    "get_warlock_runtime",
    "has_fighting_style",
    "has_any_spell_slot",
    "has_exact_spell_slot",
    "has_selected_warlock_invocation",
    "has_unconsumed_studied_attack_mark",
    "normalize_class_feature_options",
    "resolve_fighting_style_ids",
    "resolve_extra_attack_count",
    "resolve_entity_proficiencies",
    "resolve_entity_save_proficiencies",
    "resolve_entity_skill_proficiencies",
    "resolve_rogue_sneak_attack_dice",
    "restore_consumed_spell_slot",
]
