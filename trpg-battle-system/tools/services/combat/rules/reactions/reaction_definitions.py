"""Static reaction definitions used by the combat rules framework."""

REACTION_DEFINITIONS = {
    "opportunity_attack": {
        "reaction_type": "opportunity_attack",
        "template_type": "leave_reach_interrupt",
        "name": "Opportunity Attack",
        "trigger_type": "leave_reach",
        "resource_cost": {"reaction": True},
        "timing": {
            "window_phase": "leave_reach_interrupt",
            "blocking": True,
        },
        "targeting": {
            "scope": "hostile_reachable",
            "requires_visible_source": True,
            "requires_hostile_source": True,
        },
        "eligibility_checks": [
            "reaction_not_used",
            "actor_is_enemy_of_trigger_mover",
            "actor_has_melee_attack",
            "actor_can_attack",
        ],
        "ask_mode": "player_or_auto_ai",
        "resolver": {"service": "resolve_opportunity_attack_reaction"},
        "ui": {
            "prompt": "Make an opportunity attack?",
            "short_label": "Opportunity Attack",
        },
    },
    "shield": {
        "reaction_type": "shield",
        "template_type": "targeted_defense_rewrite",
        "name": "Shield",
        "trigger_type": "attack_declared",
        "resource_cost": {
            "reaction": True,
            "spell_slot": {"level": 1, "allow_higher_slot": True},
        },
        "timing": {
            "window_phase": "before_attack_result_locked",
            "blocking": True,
        },
        "targeting": {
            "scope": "self",
            "requires_visible_source": False,
            "requires_hostile_source": False,
        },
        "eligibility_checks": [
            "reaction_not_used",
            "actor_is_target_of_trigger",
            "actor_can_cast_reaction_spell",
            "actor_has_spell_shield",
        ],
        "ask_mode": "player_or_auto_ai",
        "resolver": {"service": "resolve_shield_reaction"},
        "ui": {
            "prompt": "Cast Shield?",
            "short_label": "Shield",
        },
    },
    "deflect_attacks": {
        "reaction_type": "deflect_attacks",
        "template_type": "defensive_reaction_reduce_damage",
        "name": "Deflect Attacks",
        "trigger_type": "attack_declared",
        "resource_cost": {"reaction": True},
        "timing": {
            "window_phase": "before_damage_locked",
            "blocking": True,
        },
        "targeting": {
            "scope": "self",
            "requires_visible_source": False,
            "requires_hostile_source": True,
        },
        "eligibility_checks": [
            "reaction_not_used",
            "actor_is_target_of_trigger",
            "actor_has_deflect_attacks",
        ],
        "ask_mode": "player_or_auto_ai",
        "resolver": {"service": "resolve_deflect_attacks_reaction"},
        "ui": {
            "prompt": "Use Deflect Attacks?",
            "short_label": "Deflect Attacks",
        },
    },
    "uncanny_dodge": {
        "reaction_type": "uncanny_dodge",
        "template_type": "defensive_reaction_reduce_damage",
        "name": "Uncanny Dodge",
        "trigger_type": "attack_declared",
        "resource_cost": {"reaction": True},
        "timing": {
            "window_phase": "before_damage_locked",
            "blocking": True,
        },
        "targeting": {
            "scope": "self",
            "requires_visible_source": True,
            "requires_hostile_source": True,
        },
        "eligibility_checks": [
            "reaction_not_used",
            "actor_is_target_of_trigger",
            "actor_has_uncanny_dodge",
        ],
        "ask_mode": "player_or_auto_ai",
        "resolver": {"service": "resolve_uncanny_dodge_reaction"},
        "ui": {
            "prompt": "Use Uncanny Dodge?",
            "short_label": "Uncanny Dodge",
        },
    },
    "absorb_elements": {
        "reaction_type": "absorb_elements",
        "template_type": "post_hit_damage_modifier",
        "name": "Absorb Elements",
        "trigger_type": "attack_declared",
        "resource_cost": {"reaction": True, "spell_slot": {"level": 3, "allow_higher_slot": False}},
        "timing": {
            "window_phase": "before_hit_locked",
            "blocking": True,
        },
        "targeting": {
            "scope": "self",
            "requires_visible_source": False,
            "requires_hostile_source": True,
        },
        "eligibility_checks": [
            "reaction_not_used",
            "actor_is_target_of_trigger",
            "actor_can_cast_reaction_spell",
            "actor_has_absorb_elements",
        ],
        "ask_mode": "player_or_auto_ai",
        "resolver": {"service": "resolve_absorb_elements_reaction"},
        "ui": {
            "prompt": "Use Absorb Elements?",
            "short_label": "Absorb Elements",
        },
    },
    "counterspell": {
        "reaction_type": "counterspell",
        "template_type": "cast_interrupt_contest",
        "name": "Counterspell",
        "trigger_type": "spell_declared",
        "resource_cost": {
            "reaction": True,
            "spell_slot": {"level": 3, "allow_higher_slot": True},
        },
        "timing": {
            "window_phase": "before_spell_resolution",
            "blocking": True,
        },
        "targeting": {
            "scope": "hostile_spellcaster",
            "requires_visible_source": True,
            "requires_hostile_source": True,
        },
        "eligibility_checks": [
            "reaction_not_used",
            "actor_can_see_trigger_caster",
            "actor_can_cast_reaction_spell",
            "actor_has_spell_counterspell",
        ],
        "ask_mode": "player_or_auto_ai",
        "resolver": {"service": "resolve_counterspell_reaction"},
        "ui": {
            "prompt": "Counterspell the spell?",
            "short_label": "Counterspell",
        },
    },
    "indomitable": {
        "reaction_type": "indomitable",
        "template_type": "failed_save_reroll",
        "name": "Indomitable",
        "trigger_type": "failed_save",
        "resource_cost": {"class_feature": "indomitable"},
        "timing": {
            "window_phase": "after_failed_save_before_result_locked",
            "blocking": True,
        },
        "targeting": {
            "scope": "self",
            "requires_visible_source": False,
            "requires_hostile_source": False,
        },
        "eligibility_checks": [
            "actor_has_indomitable",
            "actor_has_remaining_indomitable_use",
        ],
        "ask_mode": "player_or_auto_ai",
        "resolver": {"service": "resolve_indomitable_reaction"},
        "ui": {
            "prompt": "Use Indomitable?",
            "short_label": "Indomitable",
        },
    },
    "tactical_mind": {
        "reaction_type": "tactical_mind",
        "template_type": "failed_ability_check_boost",
        "name": "Tactical Mind",
        "trigger_type": "failed_ability_check",
        "resource_cost": {"class_feature": "tactical_mind"},
        "timing": {
            "window_phase": "after_failed_check_before_result_locked",
            "blocking": True,
        },
        "targeting": {
            "scope": "self",
            "requires_visible_source": False,
            "requires_hostile_source": False,
        },
        "eligibility_checks": [
            "actor_has_tactical_mind",
            "actor_has_remaining_second_wind_use",
        ],
        "ask_mode": "player_or_auto_ai",
        "resolver": {"service": "resolve_tactical_mind_reaction"},
        "ui": {
            "prompt": "Use Tactical Mind?",
            "short_label": "Tactical Mind",
        },
    },
}
