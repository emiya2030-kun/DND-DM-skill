from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.armor_definition_repository import ArmorDefinitionRepository
from tools.repositories.class_feature_definition_repository import ClassFeatureDefinitionRepository
from tools.repositories.encounter_repository import EncounterRepository
from tools.repositories.event_repository import EventRepository
from tools.repositories.weapon_definition_repository import WeaponDefinitionRepository
from tools.services.combat.attack.weapon_profile_resolver import WeaponProfileResolver
from tools.services.combat.attack.weapon_mastery_effects import (
    build_weapon_mastery_effect_labels,
    get_weapon_mastery_speed_penalty,
)
from tools.services.combat.defense.armor_profile_resolver import ArmorProfileResolver
from tools.services.class_features.barbarian.runtime import ensure_barbarian_runtime
from tools.services.class_features.shared import (
    build_available_spell_slots_view,
    ensure_fighter_runtime,
    ensure_bard_runtime,
    ensure_cleric_runtime,
    ensure_druid_runtime,
    ensure_monk_runtime,
    ensure_paladin_runtime,
    ensure_ranger_runtime,
    ensure_rogue_runtime,
    ensure_spell_slots_runtime,
    ensure_sorcerer_runtime,
    ensure_warlock_runtime,
    ensure_wizard_runtime,
    has_fighting_style,
    resolve_entity_save_proficiencies,
)
from tools.services.class_features.shared.warlock_invocations import resolve_gaze_of_two_minds_origin
from tools.services.encounter.monster_action_schema import evaluate_monster_action_availability
from tools.services.shared_turns import list_current_turn_group_members
from tools.services.encounter.enemy_tactical_engagement import build_enemy_reachable_targets
from tools.services.encounter.movement_rules import validate_movement_path
from tools.services.map.build_map_notes import BuildMapNotes
from tools.services.map.render_battlemap_view import RenderBattlemapView

# Close-score window for "prefer concentration target" tie-break in enemy tactical brief.
ENEMY_TACTICAL_BRIEF_CLOSE_SCORE_WINDOW = 8.0
ENEMY_HYBRID_LOW_HIT_CHANCE_THRESHOLD = 0.40

MARTIAL_CLASS_SUMMARIES = {
    "monk": {
        "fields": [
            "level",
            "focus_points",
            "martial_arts_die",
            "martial_arts",
            "uncanny_metabolism",
            "slow_fall",
            "flurry_of_blows",
            "unarmored_movement_bonus_feet",
            "stunning_strike",
            "evasion",
            "heightened_focus",
            "self_restoration",
            "deflect_energy",
            "disciplined_survivor",
            "perfect_focus",
            "superior_defense",
        ],
        "available_features": [
            {"key": "martial_arts", "level_required": 1},
            {"key": "flurry_of_blows", "level_required": 2},
            {"key": "patient_defense", "level_required": 2},
            {"key": "step_of_the_wind", "level_required": 2},
            {"key": "stunning_strike", "level_required": 5},
        ],
    },
    "rogue": {
        "fields": ["level", "sneak_attack"],
        "available_features": ["sneak_attack", "cunning_action"],
    },
    "paladin": {
        "fields": [
            "level",
            "prepared_spells_count",
            "spell_preparation_mode",
            "always_prepared_spells",
            "divine_smite",
            "lay_on_hands",
            "faithful_steed",
            "channel_divinity",
            "aura_of_protection",
            "aura_of_courage",
            "radiant_strikes",
        ],
        "available_features": ["divine_smite", "lay_on_hands", "aura_of_protection"],
    },
    "barbarian": {
        "fields": ["level", "rage", "rage_damage_bonus", "reckless_attack", "brutal_strike", "relentless_rage"],
        "available_features": ["rage", "reckless_attack", "danger_sense"],
    },
    "ranger": {
        "fields": [
            "level",
            "prepared_spells_count",
            "spell_preparation_mode",
            "always_prepared_spells",
            "weapon_mastery_count",
            "favored_enemy",
            "deft_explorer",
            "fighting_style",
            "roving",
            "tireless",
            "relentless_hunter",
            "natures_veil",
            "precise_hunter",
            "feral_senses",
            "foe_slayer",
        ],
        "available_features": ["favored_enemy", "weapon_mastery"],
    },
    "cleric": {
        "fields": [
            "level",
            "cantrips_known",
            "prepared_spells_count",
            "spell_preparation_mode",
            "always_prepared_spells",
            "channel_divinity",
            "divine_spark",
            "turn_undead",
            "sear_undead",
            "blessed_strikes",
            "improved_blessed_strikes",
            "divine_intervention",
        ],
        "available_features": ["spellcasting"],
    },
    "druid": {
        "fields": [
            "level",
            "cantrips_known",
            "prepared_spells_count",
            "spell_preparation_mode",
            "always_prepared_spells",
            "druidic",
            "wild_shape",
            "wild_companion",
            "wild_resurgence",
            "elemental_fury",
            "beast_spells",
            "archdruid",
        ],
        "available_features": ["spellcasting"],
    },
    "warlock": {
        "fields": [
            "level",
            "invocations_known",
            "cantrips_known",
            "prepared_spells_count",
            "eldritch_invocations",
            "pact_of_the_chain",
            "armor_of_shadows",
            "fiendish_vigor",
            "eldritch_mind",
            "devils_sight",
            "pact_of_the_blade",
            "gaze_of_two_minds",
            "eldritch_smite",
            "lifedrinker",
            "magical_cunning",
            "contact_patron",
            "mystic_arcanum",
            "eldritch_master",
        ],
        "available_features": ["eldritch_invocations", "pact_magic"],
    },
    "sorcerer": {
        "fields": [
            "level",
            "cantrips_known",
            "prepared_spells_count",
            "sorcery_points",
            "innate_sorcery",
            "font_of_magic",
            "sorcerous_restoration",
            "sorcery_incarnate",
            "created_spell_slots",
        ],
        "available_features": ["spellcasting", "innate_sorcery"],
    },
    "bard": {
        "fields": [
            "level",
            "cantrips_known",
            "prepared_spells_count",
            "bardic_inspiration",
            "expertise",
            "jack_of_all_trades",
            "font_of_inspiration",
            "countercharm",
            "magical_secrets",
            "superior_inspiration",
            "words_of_creation",
        ],
        "available_features": ["bardic_inspiration", "spellcasting"],
    },
    "wizard": {
        "fields": [
            "level",
            "cantrips_known",
            "prepared_spells_count",
            "spell_preparation_mode",
            "always_prepared_spells",
        ],
        "available_features": ["spellcasting"],
    },
}

AVAILABLE_FEATURE_LABELS_ZH = {
    "monk": {
        "martial_arts": "武艺",
        "flurry_of_blows": "疾风连击",
        "patient_defense": "坚强防御",
        "step_of_the_wind": "疾步如风",
        "stunning_strike": "震慑拳",
    },
    "fighter": {
        "weapon_mastery": "武器精通",
        "second_wind": "回气",
        "action_surge": "动作如潮",
        "tactical_mind": "战术思维",
        "tactical_shift": "战术转进",
        "extra_attack": "额外攻击",
        "indomitable": "不屈",
        "tactical_master": "战术主宰",
        "studied_attacks": "究明攻击",
    },
    "rogue": {
        "sneak_attack": "偷袭",
        "cunning_action": "巧诈动作",
    },
    "paladin": {
        "divine_smite": "至圣斩",
        "lay_on_hands": "圣疗",
        "aura_of_protection": "守护灵光",
        "spellcasting": "施法",
        "faithful_steed": "忠诚坐骑",
        "channel_divinity": "引导神力",
        "abjure_foes": "斥退仇敌",
        "aura_of_courage": "勇气灵光",
        "radiant_strikes": "辉耀打击",
        "restoring_touch": "疗愈之触",
    },
    "barbarian": {
        "rage": "狂暴",
        "reckless_attack": "鲁莽攻击",
        "danger_sense": "危机感应",
        "brutal_strike": "凶蛮打击",
        "relentless_rage": "坚韧狂暴",
        "persistent_rage": "持久狂暴",
        "indomitable_might": "不屈勇武",
    },
    "ranger": {
        "favored_enemy": "宿敌",
        "weapon_mastery": "武器精通",
        "spellcasting": "施法",
        "deft_explorer": "老练探险者",
        "fighting_style": "战斗风格",
        "extra_attack": "额外攻击",
        "roving": "漫游",
        "tireless": "不知疲倦",
        "relentless_hunter": "无情猎手",
        "natures_veil": "自然帷幕",
        "precise_hunter": "精准猎手",
        "feral_senses": "野性感官",
        "foe_slayer": "屠敌者",
    },
    "cleric": {
        "spellcasting": "施法",
        "channel_divinity": "引导神力",
        "divine_spark": "神圣火花",
        "turn_undead": "斥亡死灵",
        "sear_undead": "灼烧亡灵",
        "blessed_strikes": "祝圣打击",
        "divine_intervention": "神迹祈请",
        "improved_blessed_strikes": "强化祝圣打击",
    },
    "druid": {
        "spellcasting": "施法",
        "druidic": "德鲁伊语",
        "wild_shape": "野性变形",
        "wild_companion": "野性伙伴",
        "wild_resurgence": "野性复苏",
        "elemental_fury": "元素狂怒",
        "beast_spells": "兽形施法",
        "archdruid": "大德鲁伊",
    },
    "bard": {
        "bardic_inspiration": "吟游诗人激励",
        "spellcasting": "施法",
        "expertise": "专精",
        "jack_of_all_trades": "万事通",
        "font_of_inspiration": "激励之源",
        "countercharm": "反迷惑",
        "magical_secrets": "魔法奥秘",
        "superior_inspiration": "先发激励",
        "words_of_creation": "创生圣言",
    },
    "warlock": {
        "eldritch_invocations": "邪术祈请",
        "pact_magic": "契约魔法",
        "armor_of_shadows": "暗影护甲",
        "fiendish_vigor": "邪魔活力",
        "eldritch_mind": "邪术心智",
        "devils_sight": "魔鬼视觉",
        "pact_of_the_blade": "刃之契约",
        "pact_of_the_chain": "链之契约",
        "gaze_of_two_minds": "双心凝视",
        "eldritch_smite": "邪术惩击",
        "lifedrinker": "噬命者",
        "magical_cunning": "魔法机敏",
        "contact_patron": "联系宗主",
        "mystic_arcanum": "秘法玄奥",
        "eldritch_master": "邪术宗师",
    },
    "sorcerer": {
        "spellcasting": "施法",
        "innate_sorcery": "先天术法",
        "font_of_magic": "魔法源泉",
        "sorcerous_restoration": "术法复原",
        "sorcery_incarnate": "术法化身",
    },
    "wizard": {
        "spellcasting": "施法",
    },
}

DISPLAY_NAME_MAP = {
    "Rapier": "刺剑",
    "Eldritch Blast": "魔能爆",
    "Hold Person": "定身类人",
    "Blindness/Deafness": "目盲/耳聋术",
    "Burning Hands": "燃烧之手",
    "Sacred Flame": "圣火术",
    "Fireball": "火球术",
}

DAMAGE_TYPE_MAP = {
    "acid": "强酸",
    "bludgeoning": "钝击",
    "cold": "寒冷",
    "fire": "火焰",
    "force": "力场",
    "lightning": "闪电",
    "necrotic": "暗蚀",
    "piercing": "穿刺",
    "poison": "毒素",
    "psychic": "心灵",
    "radiant": "光耀",
    "slashing": "挥砍",
    "thunder": "雷鸣",
}

WEAPON_PROPERTY_MAP = {
    "finesse": "灵巧",
    "light": "轻型",
    "thrown": "投掷",
    "ammunition": "弹药",
    "two_handed": "双手",
    "reach": "触及",
    "heavy": "重型",
}

CONDITION_NAME_MAP = {
    "blinded": "目盲",
    "charmed": "魅惑",
    "deafened": "耳聋",
    "exhaustion": "力竭",
    "frightened": "恐慌",
    "grappled": "擒抱",
    "incapacitated": "失能",
    "invisible": "隐形",
    "paralyzed": "麻痹",
    "petrified": "石化",
    "poisoned": "中毒",
    "prone": "倒地",
    "restrained": "束缚",
    "stunned": "震慑",
    "unconscious": "昏迷",
}

CHECK_KEY_MAP = {
    "acrobatics": "杂技",
    "animal_handling": "驯兽",
    "arcana": "奥秘",
    "athletics": "运动",
    "deception": "欺瞒",
    "history": "历史",
    "insight": "洞悉",
    "intimidation": "威吓",
    "investigation": "调查",
    "medicine": "医药",
    "nature": "自然",
    "perception": "察觉",
    "performance": "表演",
    "persuasion": "游说",
    "religion": "宗教",
    "sleight_of_hand": "巧手",
    "stealth": "隐匿",
    "survival": "求生",
}

PLAYER_SHEET_ABILITY_LABELS = {
    "str": "力量",
    "dex": "敏捷",
    "con": "体魄",
    "int": "智力",
    "wis": "感知",
    "cha": "魅力",
}

PLAYER_SHEET_SKILL_LABELS = {
    "athletics": "运动",
    "acrobatics": "特技",
    "sleight_of_hand": "巧手",
    "stealth": "隐匿",
    "arcana": "奥秘",
    "history": "历史",
    "investigation": "调查",
    "nature": "自然",
    "religion": "宗教",
    "animal_handling": "驯兽",
    "insight": "洞悉",
    "medicine": "医药",
    "perception": "察觉",
    "survival": "求生",
    "deception": "欺瞒",
    "intimidation": "威吓",
    "performance": "表演",
    "persuasion": "游说",
}

PLAYER_SHEET_SKILL_ABILITIES = {
    "athletics": "str",
    "acrobatics": "dex",
    "sleight_of_hand": "dex",
    "stealth": "dex",
    "arcana": "int",
    "history": "int",
    "investigation": "int",
    "nature": "int",
    "religion": "int",
    "animal_handling": "wis",
    "insight": "wis",
    "medicine": "wis",
    "perception": "wis",
    "survival": "wis",
    "deception": "cha",
    "intimidation": "cha",
    "performance": "cha",
    "persuasion": "cha",
}

CLASS_NAME_MAP = {
    "barbarian": "野蛮人",
    "bard": "吟游诗人",
    "cleric": "牧师",
    "druid": "德鲁伊",
    "fighter": "战士",
    "monk": "武僧",
    "paladin": "圣武士",
    "ranger": "游侠",
    "rogue": "游荡者",
    "sorcerer": "术士",
    "warlock": "邪术师",
    "wizard": "法师",
}

PLAYER_SHEET_CLASS_FEATURES = {
    "fighter": [
        {
            "key": "fighting_style",
            "level": 1,
            "label": "战斗风格",
            "description": "获得 1 项战斗风格专长；每次获得战士等级时可更换。",
        },
        {
            "key": "second_wind",
            "level": 1,
            "label": "回气",
            "description": "附赠动作回复 1d10 + 战士等级生命。初始 2 次；短休回 1 次，长休全回。高等级获得更多次数。",
        },
        {
            "key": "weapon_mastery",
            "level": 1,
            "label": "武器精通",
            "description": "掌握 3 种简易或军用武器的精通词条；长休后可替换 1 种。高等级可掌握更多武器。",
        },
        {
            "key": "action_surge",
            "level": 2,
            "label": "动作如潮",
            "description": "你的回合内额外获得 1 个动作，但不能用于魔法动作。短休或长休恢复；17级起每次休息可用 2 次。",
        },
        {
            "key": "tactical_mind",
            "level": 2,
            "label": "战术思维",
            "description": "属性检定失败时，可消耗 1 次回气来掷 1d10 加到结果上；若仍失败，则不消耗回气次数。",
        },
        {
            "key": "tactical_shift",
            "level": 2,
            "label": "战术转进",
            "description": "使用回气时，可额外移动最多一半速度，且不会引发借机攻击。",
        },
        {
            "key": "subclass",
            "level": 3,
            "label": "战士子职",
            "description": "选择 1 个战士子职，并获得对应等级的全部子职特性。",
        },
        {
            "key": "ability_score_improvement",
            "level": 4,
            "label": "属性值提升",
            "description": "获得属性值提升专长或其他符合条件的专长；后续多个战士等级会再次获得。",
        },
        {
            "key": "extra_attack",
            "level": 5,
            "label": "额外攻击",
            "description": "执行攻击动作时可攻击 2 次。",
        },
        {
            "key": "indomitable",
            "level": 9,
            "label": "不屈",
            "description": "豁免失败时可重骰，并获得等同战士等级的加值。长休恢复；13级起 2 次，17级起 3 次。",
        },
        {
            "key": "tactical_master",
            "level": 9,
            "label": "战术主宰",
            "description": "使用武器精通时，可将精通词条改为推离、削弱或缓速之一。",
        },
        {
            "key": "extra_attack_2",
            "level": 11,
            "label": "额外攻击（二）",
            "description": "执行攻击动作时可攻击 3 次。",
        },
        {
            "key": "studied_attacks",
            "level": 13,
            "label": "究明攻击",
            "description": "攻击失手后，在你下个回合结束前对该目标的下一次攻击具有优势。",
        },
        {
            "key": "epic_boon",
            "level": 19,
            "label": "传奇恩惠",
            "description": "获得 1 项传奇恩惠专长或其他适用专长。",
        },
        {
            "key": "extra_attack_3",
            "level": 20,
            "label": "额外攻击（三）",
            "description": "执行攻击动作时可攻击 4 次。",
        },
    ],
    "barbarian": [
        {
            "key": "rage",
            "level": 1,
            "label": "狂暴",
            "description": "进入狂暴以获得近战增伤、力量优势和伤害抗性。",
        },
        {
            "key": "weapon_mastery",
            "level": 1,
            "label": "武器精通",
            "description": "掌握多种武器精通效果，强化命中的附加控制力。",
        },
        {
            "key": "unarmored_defense",
            "level": 1,
            "label": "无甲防御",
            "description": "未穿护甲时以体魄和敏捷共同支撑防御。",
        },
        {
            "key": "danger_sense",
            "level": 2,
            "label": "危险感知",
            "description": "对可见来源造成的敏捷豁免更警觉，较难被范围效果压制。",
        },
        {
            "key": "reckless_attack",
            "level": 2,
            "label": "鲁莽攻击",
            "description": "以让敌人更容易反击为代价，换取本回合近战攻击优势。",
        },
        {
            "key": "primal_knowledge",
            "level": 3,
            "label": "原初学识",
            "description": "强化野蛮人与力量相关的探索和技能表现。",
        },
        {
            "key": "subclass",
            "level": 3,
            "label": "野蛮人子职",
            "description": "选择 1 个野蛮人子职，并获得对应等级的全部子职特性。",
        },
        {
            "key": "ability_score_improvement",
            "level": 4,
            "label": "属性值提升",
            "description": "获得属性值提升专长或其他符合条件的专长。",
        },
        {
            "key": "extra_attack",
            "level": 5,
            "label": "额外攻击",
            "description": "执行攻击动作时可攻击 2 次。",
        },
        {
            "key": "fast_movement",
            "level": 5,
            "label": "快速移动",
            "description": "未穿重甲时获得额外移动速度，更容易贴近或追击目标。",
        },
        {
            "key": "feral_instinct",
            "level": 7,
            "label": "野性直觉",
            "description": "先攻更敏锐，并减少因措手不及而错失进攻的风险。",
        },
        {
            "key": "instinctive_pounce",
            "level": 7,
            "label": "本能猛扑",
            "description": "开始狂暴时立刻追加位移，快速压上战线。",
        },
        {
            "key": "brutal_strike",
            "level": 9,
            "label": "残暴打击",
            "description": "放弃优势时换取额外伤害骰与战术效果。",
        },
        {
            "key": "relentless_rage",
            "level": 11,
            "label": "不屈狂怒",
            "description": "在致命打击前挣扎站稳，以体魄豁免避免直接倒下。",
        },
        {
            "key": "improved_brutal_strike_13",
            "level": 13,
            "label": "强化凶蛮打击",
            "description": "凶蛮打击获得更多可选效果。",
        },
        {
            "key": "persistent_rage",
            "level": 15,
            "label": "持久狂暴",
            "description": "狂暴更稳定持久，并可在投先攻时回满使用次数一次。",
        },
        {
            "key": "improved_brutal_strike_17",
            "level": 17,
            "label": "强化凶蛮打击",
            "description": "凶蛮打击额外伤害提升，并可同时附加两种效果。",
        },
        {
            "key": "indomitable_might",
            "level": 18,
            "label": "不屈勇武",
            "description": "力量检定或力量豁免过低时，可直接改用力量值。",
        },
        {
            "key": "epic_boon",
            "level": 19,
            "label": "传奇恩惠",
            "description": "获得 1 项传奇恩惠专长或其他适用专长。",
        },
        {
            "key": "primal_champion",
            "level": 20,
            "label": "原初斗士",
            "description": "力量和体质各 +4，二者上限提升到 25。",
        },
    ],
    "monk": [
        {
            "key": "martial_arts",
            "level": 1,
            "label": "武艺",
            "description": "满足条件时，可用附赠动作追加一次徒手打击，并以武艺骰和敏捷强化徒手打击与武僧武器攻击。",
        },
        {
            "key": "unarmored_defense",
            "level": 1,
            "label": "无甲防御",
            "description": "未穿护甲且未持盾时，AC = 10 + 敏捷调整值 + 感知调整值。",
        },
        {
            "key": "monks_focus",
            "level": 2,
            "label": "武僧武功",
            "description": "获得功力资源，并可用其发动三项核心武功：疾风连击可用附赠动作进行两次徒手打击；坚强防御可用附赠动作撤离，消耗功力时还可同时回避；疾步如风可用附赠动作疾走，消耗功力时还可同时撤离并强化跳跃。",
        },
        {
            "key": "unarmored_movement",
            "level": 2,
            "label": "无甲移动",
            "description": "未穿护甲且未持盾时，速度提高；加值随武僧等级成长。",
        },
        {
            "key": "uncanny_metabolism",
            "level": 2,
            "label": "运转周天",
            "description": "投先攻时可回满功力并恢复生命，但长休前只能这样做一次。",
        },
        {
            "key": "deflect_attacks",
            "level": 3,
            "label": "拨挡攻击",
            "description": "被攻击命中时，可用反应减少伤害；若减到 0，可消耗 1 点功力把伤害转回给其他目标。",
        },
        {
            "key": "subclass",
            "level": 3,
            "label": "武僧子职",
            "description": "选择 1 个武僧子职，并获得对应等级的全部子职特性。",
        },
        {
            "key": "ability_score_improvement",
            "level": 4,
            "label": "属性值提升",
            "description": "获得属性值提升专长或其他符合条件的专长。",
        },
        {
            "key": "slow_fall",
            "level": 4,
            "label": "轻身坠",
            "description": "坠落时可用反应大幅减少坠落伤害。",
        },
        {
            "key": "extra_attack",
            "level": 5,
            "label": "额外攻击",
            "description": "执行攻击动作时可攻击 2 次。",
        },
        {
            "key": "stunning_strike",
            "level": 5,
            "label": "震慑拳",
            "description": "每回合一次，命中后可消耗 1 点功力迫使目标体质豁免；失败则震慑，成功也会被减速并更容易被后续攻击命中。",
        },
        {
            "key": "empowered_strikes",
            "level": 6,
            "label": "真力注拳",
            "description": "徒手打击可改造成力场伤害。",
        },
        {
            "key": "evasion",
            "level": 7,
            "label": "反射闪避",
            "description": "面对可进行敏捷豁免减半伤害的效果时，成功则无伤，失败也只受一半伤害；失能时无效。",
        },
        {
            "key": "acrobatic_movement",
            "level": 9,
            "label": "飞檐走壁",
            "description": "未穿护甲且未持盾时，在自己的回合内可沿垂直表面与液体表面移动而不坠落。",
        },
        {
            "key": "heightened_focus",
            "level": 10,
            "label": "出神入化",
            "description": "强化三项核心武功：疾风连击消耗 1 点功力时可进行 3 次徒手打击而非 2 次；坚强防御消耗功力使用时获得 2 个武艺骰的临时生命值；疾步如风消耗功力使用时可带上 1 名邻近自愿生物一起移动且不触发借机攻击。",
        },
        {
            "key": "self_restoration",
            "level": 10,
            "label": "返本还元",
            "description": "每回合结束可移除魅惑、恐慌或中毒之一；也不再因不吃不喝而累积力竭。",
        },
        {
            "key": "deflect_energy",
            "level": 13,
            "label": "拨挡能量",
            "description": "拨挡攻击现在可对抗任何伤害类型，不再只限物理伤害。",
        },
        {
            "key": "disciplined_survivor",
            "level": 14,
            "label": "圆融自在",
            "description": "获得所有豁免熟练；豁免失败时可消耗 1 点功力重骰。",
        },
        {
            "key": "perfect_focus",
            "level": 15,
            "label": "明镜止水",
            "description": "投先攻时若不使用运转周天，且功力过低，可直接恢复到 4 点。",
        },
        {
            "key": "superior_defense",
            "level": 18,
            "label": "无懈可击",
            "description": "可消耗 3 点功力进入高防御状态，持续期间对力场以外的所有伤害具有抗性。",
        },
        {
            "key": "epic_boon",
            "level": 19,
            "label": "传奇恩惠",
            "description": "获得 1 项传奇恩惠专长或其他适用专长。",
        },
        {
            "key": "body_and_mind",
            "level": 20,
            "label": "天人合一",
            "description": "敏捷和感知各 +4，且两者上限提升到 25。",
        },
    ],
}

HP_STATUS_MAP = {
    "DOWN": "倒地",
    "HEALTHY": "健康",
    "WOUNDED": "受伤",
    "BLOODIED": "重伤",
}


class GetEncounterState:
    """把底层 Encounter 投影成 `get_encounter_state` 视图对象。"""

    def __init__(
        self,
        repository: EncounterRepository,
        event_repository: EventRepository | None = None,
        battlemap_view_service: RenderBattlemapView | None = None,
        map_notes_service: BuildMapNotes | None = None,
        armor_definition_repository: ArmorDefinitionRepository | None = None,
        class_feature_definition_repository: ClassFeatureDefinitionRepository | None = None,
    ):
        self.repository = repository
        self.event_repository = event_repository
        self.battlemap_view_service = battlemap_view_service or RenderBattlemapView()
        self.map_notes_service = map_notes_service or BuildMapNotes()
        self.armor_definition_repository = armor_definition_repository or ArmorDefinitionRepository()
        self.class_feature_definition_repository = class_feature_definition_repository or ClassFeatureDefinitionRepository()
        self.weapon_definition_repository = WeaponDefinitionRepository()
        self.armor_profile_resolver = ArmorProfileResolver(self.armor_definition_repository)
        self.weapon_profile_resolver = WeaponProfileResolver(self.weapon_definition_repository)

    def execute(self, encounter_id: str) -> dict[str, Any]:
        """读取指定 encounter，并返回视图层对象。"""
        encounter = self.repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")

        current_entity = self._get_current_entity(encounter)
        recent_forced_movement = self._build_recent_forced_movement(encounter)
        recent_turn_effects = self._build_recent_turn_effects(encounter)
        recent_activity = self._build_recent_activity(encounter)
        spell_area_overlays = self._build_spell_area_overlays(encounter)
        player_sheet_source = self._build_player_sheet_source(encounter)
        current_turn_entity = self._build_current_turn_entity(encounter, current_entity)
        current_turn_group = self._build_current_turn_group(encounter)
        turn_order = self._build_turn_order(encounter, current_entity)
        active_spell_summaries = self._build_active_spell_summaries(encounter)
        retargetable_spell_actions = self._build_retargetable_spell_actions(
            encounter,
            current_entity=current_entity,
        )
        battlemap_details = self._build_battlemap_details(encounter)
        battlemap_view = self.battlemap_view_service.execute(
            encounter,
            recent_forced_movement=recent_forced_movement,
            recent_turn_effects=recent_turn_effects,
            recent_activity=recent_activity,
            spell_area_overlays=spell_area_overlays,
        )
        map_notes = self.map_notes_service.execute(encounter)
        reaction_requests = self._build_reaction_requests(encounter)
        pending_reaction_window = self._build_pending_reaction_window(encounter)
        pending_movement = self._build_pending_movement(encounter)
        encounter_notes = encounter.encounter_notes

        return {
            "encounter_id": encounter.encounter_id,
            "encounter_name": encounter.name,
            "round": encounter.round,
            "player_sheet_source": player_sheet_source,
            "current_turn_entity": current_turn_entity,
            "current_turn_group": current_turn_group,
            "turn_order": turn_order,
            "active_spell_summaries": active_spell_summaries,
            "retargetable_spell_actions": retargetable_spell_actions,
            "battlemap_details": battlemap_details,
            "battlemap_view": battlemap_view,
            "map_notes": map_notes,
            "reaction_requests": reaction_requests,
            "pending_reaction_window": pending_reaction_window,
            "pending_movement": pending_movement,
            "spell_area_overlays": spell_area_overlays,
            "recent_activity": recent_activity,
            "recent_forced_movement": recent_forced_movement,
            "recent_turn_effects": recent_turn_effects,
            "encounter_notes": encounter_notes,
            "encounter": self._build_encounter_payload(
                encounter,
                current_turn_group=current_turn_group,
                turn_order=turn_order,
            ),
            "player_sheet": player_sheet_source,
            "current_turn_context": self._build_current_turn_context(
                encounter,
                entity=current_entity,
                current_turn_entity=current_turn_entity,
                current_turn_group=current_turn_group,
            ),
            "battlemap": self._build_battlemap_payload(
                encounter,
                current_entity=current_entity,
                battlemap_details=battlemap_details,
                battlemap_view=battlemap_view,
                map_notes=map_notes,
                recent_activity=recent_activity,
                recent_forced_movement=recent_forced_movement,
                recent_turn_effects=recent_turn_effects,
                spell_area_overlays=spell_area_overlays,
            ),
            "interaction": self._build_interaction_payload(
                reaction_requests=reaction_requests,
                pending_reaction_window=pending_reaction_window,
                pending_movement=pending_movement,
                retargetable_spell_actions=retargetable_spell_actions,
            ),
        }

    def _build_encounter_payload(
        self,
        encounter: Encounter,
        *,
        current_turn_group: dict[str, Any] | None,
        turn_order: list[dict[str, Any]],
    ) -> dict[str, Any]:
        current_entity = self._get_current_entity(encounter)
        return {
            "encounter_id": encounter.encounter_id,
            "name": encounter.name,
            "status": encounter.status,
            "round": encounter.round,
            "current_entity_id": encounter.current_entity_id,
            "current_entity_name": current_entity.name if current_entity is not None else None,
            "turn_order": turn_order,
            "current_turn_group": current_turn_group,
            "active_spell_summaries": self._build_active_spell_summaries(encounter),
            "encounter_notes": encounter.encounter_notes,
        }

    def _build_current_turn_context(
        self,
        encounter: Encounter,
        *,
        entity: EncounterEntity | None,
        current_turn_entity: dict[str, Any] | None,
        current_turn_group: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if entity is None or current_turn_entity is None:
            return None

        available_actions = current_turn_entity.get("available_actions", {})
        current_turn_context: dict[str, Any] = {
            "actor": self._build_current_turn_context_actor(current_turn_entity),
            "current_turn_group": self._build_current_turn_context_group(current_turn_group),
            "actor_options": {
                "weapon_attacks": self._build_current_turn_context_weapon_attacks(available_actions.get("weapons", [])),
                "spells": self._build_current_turn_context_spells(entity),
                "spell_slots_available": available_actions.get("spell_slots_available", {}),
                "traits": self._build_current_turn_context_traits(entity),
                "actions": self._build_current_turn_context_actions(encounter, entity, "actions_metadata", "action_id"),
                "bonus_actions": self._build_current_turn_context_actions(encounter, entity, "bonus_actions_metadata", "bonus_action_id"),
                "legendary_actions": self._build_current_turn_context_actions(
                    encounter, entity, "legendary_actions_metadata", "legendary_action_id"
                ),
                "reactions": self._build_current_turn_context_actions(encounter, entity, "reactions_metadata", "reaction_id"),
            },
            "targeting": self._build_current_turn_context_targeting(current_turn_entity.get("weapon_ranges", {})),
        }
        enemy_tactical_brief = self._build_enemy_tactical_brief(encounter, entity)
        if enemy_tactical_brief is not None:
            current_turn_context["enemy_tactical_brief"] = enemy_tactical_brief
        enemy_ranged_tactical_brief = self._build_enemy_ranged_tactical_brief(encounter, entity)
        if enemy_ranged_tactical_brief is not None:
            current_turn_context["enemy_ranged_tactical_brief"] = enemy_ranged_tactical_brief
        enemy_hybrid_tactical_brief = self._build_enemy_hybrid_tactical_brief(encounter, entity)
        if enemy_hybrid_tactical_brief is not None:
            current_turn_context["enemy_hybrid_tactical_brief"] = enemy_hybrid_tactical_brief
        unified_recommendation = self._build_unified_enemy_turn_recommendation(
            enemy_tactical_brief=enemy_tactical_brief,
            enemy_ranged_tactical_brief=enemy_ranged_tactical_brief,
            enemy_hybrid_tactical_brief=enemy_hybrid_tactical_brief,
        )
        if unified_recommendation is not None:
            current_turn_context["recommended_tactic"] = unified_recommendation["recommended_tactic"]
            current_turn_context["contingencies"] = unified_recommendation["contingencies"]
        return current_turn_context

    def _build_current_turn_context_actor(
        self,
        current_turn_entity: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "id": current_turn_entity.get("id"),
            "name": current_turn_entity.get("name"),
            "level": current_turn_entity.get("level"),
            "hp": current_turn_entity.get("hp"),
            "position": current_turn_entity.get("position"),
            "movement_remaining": current_turn_entity.get("movement_remaining"),
            "ac": current_turn_entity.get("ac"),
            "speed": current_turn_entity.get("speed"),
            "spell_save_dc": current_turn_entity.get("spell_save_dc"),
            "spellcasting": self._build_current_turn_context_spellcasting(current_turn_entity.get("spellcasting")),
            "conditions": current_turn_entity.get("conditions"),
            "ongoing_effects": current_turn_entity.get("ongoing_effects"),
            "resources": self._build_current_turn_context_resources(current_turn_entity.get("resources")),
        }

    def _build_current_turn_context_group(
        self,
        current_turn_group: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(current_turn_group, dict):
            return None
        controlled_members = current_turn_group.get("controlled_members")
        normalized_members: list[dict[str, Any]] = []
        if isinstance(controlled_members, list):
            for member in controlled_members:
                if not isinstance(member, dict):
                    continue
                normalized_members.append(
                    {
                        "entity_id": member.get("entity_id"),
                        "name": member.get("name"),
                        "relation": member.get("relation"),
                    }
                )
        return {
            "owner_entity_id": current_turn_group.get("owner_entity_id"),
            "owner_name": current_turn_group.get("owner_name"),
            "controlled_members": normalized_members,
        }

    def _build_current_turn_context_spellcasting(
        self,
        spellcasting: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not isinstance(spellcasting, dict):
            return {"summary": "当前无可用施法摘要。"}
        return {
            "summary": spellcasting.get("summary") or "当前无可用施法摘要。",
        }

    def _build_current_turn_context_resources(
        self,
        resources: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not isinstance(resources, dict):
            return {"summary": "无追踪资源"}
        return {
            "summary": resources.get("summary") or "无追踪资源",
        }

    def _build_current_turn_context_spells(
        self,
        entity: EncounterEntity,
    ) -> dict[str, list[dict[str, Any]]]:
        grouped_spells: dict[str, list[dict[str, Any]]] = {"cantrips": []}
        for spell in entity.spells:
            spell_level = spell.get("level", 0)
            group_key = "cantrips" if spell_level == 0 else f"level_{spell_level}_spells"
            grouped_spells.setdefault(group_key, [])
            range_feet = spell.get("range_feet")
            grouped_spells[group_key].append(
                {
                    "id": spell.get("spell_id"),
                    "name": self._localize_display_name(spell.get("name")),
                    "level": spell_level,
                    "range": f"{range_feet} 尺" if isinstance(range_feet, int) and range_feet > 0 else None,
                    "summary": spell.get("description"),
                    "damage_summary": self._format_spell_damage_summary(spell.get("damage", [])),
                    "requires_attack_roll": bool(spell.get("requires_attack_roll", False)),
                }
            )
        return grouped_spells

    def _format_spell_damage_summary(self, damage_parts: Any) -> str | None:
        if not isinstance(damage_parts, list):
            return None
        parts: list[str] = []
        for part in damage_parts:
            if not isinstance(part, dict):
                continue
            formula = part.get("formula")
            damage_type = part.get("type")
            if formula and damage_type:
                parts.append(f"{formula} {self._localize_damage_type(damage_type)}")
        if not parts:
            return None
        return " + ".join(parts)

    def _build_current_turn_context_weapon_attacks(
        self,
        weapons: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(weapons, list):
            return []
        projected: list[dict[str, Any]] = []
        for weapon in weapons:
            if not isinstance(weapon, dict):
                continue
            projected.append(
                {
                    "slot": weapon.get("slot"),
                    "weapon_id": weapon.get("weapon_id"),
                    "name": weapon.get("name"),
                    "damage": weapon.get("damage"),
                    "attack_bonus": weapon.get("bonus"),
                    "note": weapon.get("note"),
                }
            )
        return projected

    def _build_current_turn_context_traits(
        self,
        entity: EncounterEntity,
    ) -> list[dict[str, Any]]:
        projected: list[dict[str, Any]] = []
        for item in self._build_entity_traits_metadata(entity):
            projected.append(
                {
                    "trait_id": item.get("trait_id"),
                    "name_zh": item.get("name_zh"),
                    "summary": item.get("summary"),
                }
            )
        return projected

    def _build_current_turn_context_actions(
        self,
        encounter: Encounter,
        entity: EncounterEntity,
        source_key: str,
        id_key: str,
    ) -> list[dict[str, Any]]:
        projected: list[dict[str, Any]] = []
        for item in self._build_entity_action_metadata(encounter, entity, source_key, id_key):
            payload = {
                id_key: item.get(id_key),
                "name_zh": item.get("name_zh"),
                "summary": item.get("summary"),
                "execution": item.get("execution"),
                "available": item.get("available", True),
                "blocked_reasons": item.get("blocked_reasons", []),
            }
            for key in (
                "action_type",
                "category",
                "availability",
                "targeting",
                "resource_cost",
                "execution_steps",
                "ai_hints",
                "multiattack_sequences",
                "resolution",
            ):
                if key in item:
                    payload[key] = item.get(key)
            projected.append(payload)
        return projected

    def _build_current_turn_context_targeting(
        self,
        weapon_ranges: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(weapon_ranges, dict):
            return {
                "melee_range": "0 尺",
                "ranged_range": "0 尺",
                "melee_targets": [],
                "ranged_targets": [],
            }
        return {
            "melee_range": weapon_ranges.get("max_melee_range", "0 尺"),
            "ranged_range": weapon_ranges.get("max_ranged_range", "0 尺"),
            "melee_targets": weapon_ranges.get("targets_within_melee_range", []),
            "ranged_targets": weapon_ranges.get("targets_within_ranged_range", []),
        }

    def _build_battlemap_payload(
        self,
        encounter: Encounter,
        *,
        current_entity: EncounterEntity | None,
        battlemap_details: dict[str, Any],
        battlemap_view: dict[str, Any],
        map_notes: list[dict[str, Any]],
        recent_activity: list[dict[str, Any]],
        recent_forced_movement: dict[str, Any] | None,
        recent_turn_effects: list[dict[str, Any]],
        spell_area_overlays: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "map_id": encounter.map.map_id,
            "name": encounter.map.name,
            "description": encounter.map.description,
            "width": encounter.map.width,
            "height": encounter.map.height,
            "grid_size_feet": encounter.map.grid_size_feet,
            "details": battlemap_details,
            "terrain": encounter.map.terrain,
            "zones": encounter.map.zones,
            "auras": encounter.map.auras,
            "remains": encounter.map.remains,
            "entities": self._build_battlemap_entities(encounter, current_entity),
            "map_notes": map_notes,
            "recent_activity": recent_activity,
            "recent_forced_movement": recent_forced_movement,
            "recent_turn_effects": recent_turn_effects,
            "spell_area_overlays": spell_area_overlays,
            "rendered_view": battlemap_view,
        }

    def _build_interaction_payload(
        self,
        *,
        reaction_requests: list[dict[str, Any]],
        pending_reaction_window: dict[str, Any] | None,
        pending_movement: dict[str, Any] | None,
        retargetable_spell_actions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "reaction_requests": reaction_requests,
            "pending_reaction_window": pending_reaction_window,
            "pending_movement": pending_movement,
            "retargetable_spell_actions": retargetable_spell_actions,
            "command_hints": {
                "begin_move_encounter_entity": {
                    "required_args": ["encounter_id", "entity_id", "target_position"],
                    "optional_args": [
                        "count_movement",
                        "use_dash",
                        "allow_out_of_turn_actor",
                        "ignore_opportunity_attacks_for_this_move",
                        "movement_mode",
                    ],
                    "automatic_behavior": [
                        "后端会自动校验路径、地形、阻挡和移动距离。",
                        "若途中触发借机攻击，后端会自动进入反应窗口。",
                    ],
                },
                "execute_attack": {
                    "required_args": ["encounter_id", "actor_id", "target_id", "weapon_id"],
                    "optional_args": [
                        "attack_mode",
                        "grip_mode",
                        "vantage",
                        "description",
                        "zero_hp_intent",
                        "allow_out_of_turn_actor",
                        "consume_action",
                        "consume_reaction",
                        "damage_rolls",
                    ],
                    "automatic_behavior": [
                        "若不提供命中掷骰，后端会自动掷命中。",
                        "若不提供 damage_rolls，后端会自动掷伤害。",
                    ],
                    "limitations": [
                        "该命令用于武器攻击。",
                        "豁免型特殊动作通常需要专用动作或豁免接口，而不是 execute_attack。",
                    ],
                }
                ,
                "use_disengage": {
                    "required_args": ["encounter_id", "actor_id"],
                    "optional_args": [],
                    "automatic_behavior": [
                        "会消耗动作并给予本回合的撤离效果。",
                    ],
                },
            },
        }

    def _get_current_entity(self, encounter: Encounter) -> EncounterEntity | None:
        if encounter.current_entity_id is None:
            return None
        return encounter.entities.get(encounter.current_entity_id)

    def _build_current_turn_entity(
        self,
        encounter: Encounter,
        entity: EncounterEntity | None,
    ) -> dict[str, Any] | None:
        if entity is None:
            return None
        armor_profile = self.armor_profile_resolver.refresh_entity_armor_class(entity)
        effective_speed = self._resolve_effective_speed(entity, armor_profile=armor_profile)

        return {
            "id": entity.entity_id,
            "name": entity.name,
            "level": self._extract_level(entity),
            "hp": self._format_hp(entity),
            "class": entity.entity_def_id,
            "description": self._extract_description(entity),
            "position": self._format_position(entity),
            "movement_remaining": f"{entity.speed['remaining']} 尺",
            "ac": entity.ac,
            "speed": effective_speed,
            "effective_speed": effective_speed,
            "speed_penalty_feet": armor_profile["speed_penalty_feet"],
            "spell_save_dc": self._calculate_spell_save_dc(entity),
            "armor": armor_profile["armor"],
            "shield": armor_profile["shield"],
            "ac_breakdown": armor_profile["ac_breakdown"],
            "stealth_disadvantage_sources": armor_profile["stealth_disadvantage_sources"],
            "untrained_armor_penalties": {
                "str_dex_d20_disadvantage": armor_profile["wearing_untrained_armor"],
                "spellcasting_blocked": armor_profile["wearing_untrained_armor"],
            },
            "available_actions": {
                "weapons": self._build_weapons_view(entity),
                "spells": self._build_spells_view(entity),
                "spell_slots_available": self._build_spell_slots_view(entity),
            },
            "actions": self._build_actions(entity),
            "spellcasting": self._build_spellcasting_state(entity),
            "weapon_ranges": self._build_weapon_ranges(encounter, entity),
            "conditions": self._format_conditions(encounter, entity),
            "ongoing_effects": self._build_entity_ongoing_effects(encounter, entity),
            "resources": self._build_resources_view(encounter, entity),
            "death_saves": self._format_death_saves(entity),
        }

    def _build_turn_order(
        self,
        encounter: Encounter,
        current_entity: EncounterEntity | None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for entity_id in encounter.turn_order:
            entity = encounter.entities[entity_id]
            armor_profile = self.armor_profile_resolver.refresh_entity_armor_class(entity)
            items.append(
                {
                    "id": entity.entity_id,
                    "name": entity.name,
                    "initiative": entity.initiative,
                    "type": entity.side,
                    "hp": self._format_hp_status(entity),
                    "ac": entity.ac,
                    "armor": armor_profile["armor"],
                    "shield": armor_profile["shield"],
                    "position": self._format_position(entity),
                    "distance_from_current_turn_entity": self._format_distance_from_current(entity, current_entity),
                    "conditions": self._format_conditions(encounter, entity),
                    "ongoing_effects": self._build_entity_ongoing_effects(encounter, entity),
                }
            )
        return items

    def _build_current_turn_group(self, encounter: Encounter) -> dict[str, Any] | None:
        members = list_current_turn_group_members(encounter)
        if not members:
            return None
        owner = members[0]
        controlled_members: list[dict[str, Any]] = []
        for index, entity in enumerate(members):
            controlled_members.append(
                {
                    "entity_id": entity.entity_id,
                    "name": entity.name,
                    "relation": "owner" if index == 0 else "summon",
                }
            )
        return {
            "owner_entity_id": owner.entity_id,
            "owner_name": owner.name,
            "controlled_members": controlled_members,
        }

    def _build_battlemap_entities(
        self,
        encounter: Encounter,
        current_entity: EncounterEntity | None,
    ) -> list[dict[str, Any]]:
        ordered_entity_ids: list[str] = []
        for entity_id in encounter.turn_order:
            if entity_id not in ordered_entity_ids and entity_id in encounter.entities:
                ordered_entity_ids.append(entity_id)
        for entity_id in encounter.entities:
            if entity_id not in ordered_entity_ids:
                ordered_entity_ids.append(entity_id)

        items: list[dict[str, Any]] = []
        for entity_id in ordered_entity_ids:
            entity = encounter.entities[entity_id]
            source_ref = entity.source_ref if isinstance(entity.source_ref, dict) else {}
            items.append(
                {
                    "entity_id": entity.entity_id,
                    "name": entity.name,
                    "side": entity.side,
                    "category": entity.category,
                    "controller": entity.controller,
                    "is_current_turn": entity.entity_id == encounter.current_entity_id,
                    "position": dict(entity.position),
                    "hp": {
                        "current": int(entity.hp.get("current", 0) or 0),
                        "max": int(entity.hp.get("max", 0) or 0),
                        "temp": int(entity.hp.get("temp", 0) or 0),
                    },
                    "ac": entity.ac,
                    "speed": dict(entity.speed),
                    "distance_from_current_turn_entity": (
                        self._distance_feet(current_entity, entity) if current_entity is not None and entity.entity_id != current_entity.entity_id else None
                    ),
                    "conditions": list(entity.conditions),
                    "condition_labels": self._format_conditions(encounter, entity),
                    "special_senses": dict(source_ref.get("special_senses", {})) if isinstance(source_ref.get("special_senses"), dict) else {},
                    "languages": list(source_ref.get("languages", [])) if isinstance(source_ref.get("languages"), list) else [],
                    "weapons": self._build_weapons_view(entity),
                    "combat_profile": {
                        "state": self._build_entity_combat_profile_state(entity),
                        "traits": self._build_entity_traits_metadata(entity),
                        "actions": self._build_entity_action_metadata(encounter, entity, "actions_metadata", "action_id"),
                        "bonus_actions": self._build_entity_action_metadata(encounter, entity, "bonus_actions_metadata", "bonus_action_id"),
                        "legendary_actions": self._build_entity_action_metadata(
                            encounter,
                            entity,
                            "legendary_actions_metadata",
                            "legendary_action_id",
                        ),
                        "reactions": self._build_entity_action_metadata(encounter, entity, "reactions_metadata", "reaction_id"),
                    },
                }
            )
        return items

    def _build_entity_traits_metadata(self, entity: EncounterEntity) -> list[dict[str, Any]]:
        source_ref = entity.source_ref if isinstance(entity.source_ref, dict) else {}
        raw_items = source_ref.get("traits_metadata")
        if not isinstance(raw_items, list):
            return []

        items: list[dict[str, Any]] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            trait_id = str(raw_item.get("trait_id") or "").strip()
            items.append(
                {
                    "trait_id": trait_id or None,
                    "name_zh": raw_item.get("name_zh"),
                    "name_en": raw_item.get("name_en"),
                    "summary": raw_item.get("summary"),
                }
            )
        return items

    def _build_entity_action_metadata(
        self,
        encounter: Encounter,
        entity: EncounterEntity,
        source_key: str,
        id_key: str,
    ) -> list[dict[str, Any]]:
        source_ref = entity.source_ref if isinstance(entity.source_ref, dict) else {}
        raw_items = source_ref.get(source_key)
        if not isinstance(raw_items, list):
            return []

        items: list[dict[str, Any]] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            item_id = str(raw_item.get(id_key) or "").strip()
            availability_projection = evaluate_monster_action_availability(encounter, entity, raw_item)
            payload = {
                id_key: item_id or None,
                "name_zh": raw_item.get("name_zh"),
                "name_en": raw_item.get("name_en"),
                "summary": raw_item.get("summary"),
                "execution": self._build_action_execution_hint(
                    encounter=encounter,
                    entity=entity,
                    action_id=item_id,
                    bucket=source_key,
                ),
                "available": availability_projection.get("available", True),
                "blocked_reasons": availability_projection.get("blocked_reasons", []),
            }
            payload.update(self._build_action_metadata_passthrough(raw_item))
            items.append(payload)
        return items

    def _build_entity_combat_profile_state(self, entity: EncounterEntity) -> dict[str, Any]:
        source_ref = entity.source_ref if isinstance(entity.source_ref, dict) else {}
        combat_profile = source_ref.get("combat_profile")
        if not isinstance(combat_profile, dict):
            return {}
        payload: dict[str, Any] = {}
        for key in ("forms", "current_form", "passive_rules", "resources"):
            value = combat_profile.get(key)
            if value is not None:
                payload[key] = value
        return payload

    def _build_action_metadata_passthrough(
        self,
        raw_item: dict[str, Any],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key in (
            "action_type",
            "category",
            "availability",
            "targeting",
            "resource_cost",
            "execution_steps",
            "ai_hints",
            "multiattack_sequences",
            "resolution",
        ):
            value = raw_item.get(key)
            if value is not None:
                payload[key] = value
        return payload

    def _build_action_execution_hint(
        self,
        *,
        encounter: Encounter,
        entity: EncounterEntity,
        action_id: str,
        bucket: str,
    ) -> dict[str, Any] | None:
        normalized_action_id = str(action_id or "").strip()
        if not normalized_action_id:
            return None

        weapon_ids = {
            str(weapon.get("weapon_id") or "").strip()
            for weapon in entity.weapons
            if isinstance(weapon, dict) and str(weapon.get("weapon_id") or "").strip()
        }
        if normalized_action_id in weapon_ids:
            return {
                "mode": "weapon_attack",
                "command": "execute_attack",
                "required_args": ["encounter_id", "actor_id", "target_id", "weapon_id"],
                "preset_args": {
                    "encounter_id": encounter.encounter_id,
                    "actor_id": entity.entity_id,
                    "weapon_id": normalized_action_id,
                },
                "optional_args": [
                    "attack_mode",
                    "grip_mode",
                    "vantage",
                    "description",
                    "zero_hp_intent",
                    "allow_out_of_turn_actor",
                    "consume_action",
                    "consume_reaction",
                    "damage_rolls",
                ],
                "automatic_behavior": [
                    "若不提供命中掷骰，后端会自动掷命中。",
                    "若不提供 damage_rolls，后端会自动掷伤害。",
                ],
            }

        if bucket == "actions_metadata":
            return {
                "mode": "special_action",
                "command": None,
                "note": "不是标准武器攻击；通常需要专用动作或豁免接口。",
            }
        if bucket == "bonus_actions_metadata":
            return {
                "mode": "special_bonus_action",
                "command": None,
                "note": "这是附赠动作能力；是否可执行取决于专用动作接口与附赠动作是否可用。",
            }
        if bucket == "reactions_metadata":
            return {
                "mode": "reaction",
                "command": None,
                "note": "这是反应能力；通常依赖触发窗口，而不是主动直接调用 execute_attack。",
            }
        if bucket == "legendary_actions_metadata":
            return {
                "mode": "legendary_action",
                "command": None,
                "note": "这是传奇动作；通常在其他生物回合后、按传奇动作资源消耗执行。",
            }
        return None

    def _build_player_sheet_source(self, encounter: Encounter) -> dict[str, Any] | None:
        entity = self._select_player_sheet_entity(encounter)
        if entity is None:
            return None
        self._ensure_player_sheet_runtime(entity)
        return {
            "summary": {
                "name": entity.name,
                "class_name": self._localize_class_name(entity),
                "subclass_name": self._extract_subclass_name(entity),
                "level": self._resolve_player_sheet_level(entity),
                "hp_current": int(entity.hp.get("current", 0) or 0),
                "hp_max": int(entity.hp.get("max", 0) or 0),
                "ac": entity.ac,
                "speed": self._resolve_effective_speed(entity),
                "spell_save_dc": self._calculate_spell_save_dc(entity),
                "spell_attack_bonus": self._calculate_spell_attack_bonus(entity),
                "portrait_url": entity.source_ref.get("portrait_url"),
            },
            "abilities": self._build_player_sheet_abilities(entity),
            "tabs": {
                "skills": self._build_player_sheet_skills(entity),
                "equipment": self._build_player_sheet_equipment(entity),
                "extras": self._build_player_sheet_extras(entity),
            },
        }

    def _resolve_effective_speed(
        self,
        entity: EncounterEntity,
        *,
        armor_profile: dict[str, Any] | None = None,
    ) -> int:
        resolved_armor_profile = armor_profile or self.armor_profile_resolver.refresh_entity_armor_class(entity)
        return max(
            0,
            entity.speed["walk"]
            - get_weapon_mastery_speed_penalty(entity)
            - int(resolved_armor_profile.get("speed_penalty_feet", 0) or 0),
        )

    def _ensure_player_sheet_runtime(self, entity: EncounterEntity) -> None:
        source_ref = entity.source_ref if isinstance(entity.source_ref, dict) else {}
        class_name = source_ref.get("class_name")
        if not isinstance(class_name, str) or not class_name.strip():
            return
        normalized = class_name.strip().lower()
        level = self._extract_level(entity)
        if level is None:
            level = 0
        bucket = entity.class_features.setdefault(normalized, {})
        if isinstance(bucket, dict) and not isinstance(bucket.get("level"), int) and level > 0:
            bucket["level"] = level

        if normalized == "monk":
            ensure_monk_runtime(entity)
        elif normalized == "rogue":
            ensure_rogue_runtime(entity)
        elif normalized == "paladin":
            ensure_paladin_runtime(entity)
        elif normalized == "fighter":
            ensure_fighter_runtime(entity)
        elif normalized == "barbarian":
            ensure_barbarian_runtime(entity)
        elif normalized == "ranger":
            ensure_ranger_runtime(entity)
        elif normalized == "sorcerer":
            ensure_sorcerer_runtime(entity)
        elif normalized == "warlock":
            ensure_warlock_runtime(entity)
        elif normalized == "bard":
            ensure_bard_runtime(entity)

    def _resolve_player_sheet_class_key(self, entity: EncounterEntity) -> str | None:
        source_ref = entity.source_ref if isinstance(entity.source_ref, dict) else {}
        class_name = source_ref.get("class_name")
        if isinstance(class_name, str) and class_name.strip():
            return class_name.strip().lower()
        for class_key, value in entity.class_features.items():
            if isinstance(class_key, str) and class_key.strip() and isinstance(value, dict):
                return class_key.strip().lower()
        return None

    def _build_player_sheet_extras(self, entity: EncounterEntity) -> dict[str, Any]:
        class_key = self._resolve_player_sheet_class_key(entity)
        feature_definitions = PLAYER_SHEET_CLASS_FEATURES.get(class_key or "")
        if not isinstance(feature_definitions, list):
            return {
                "placeholder_title": "后续追加",
                "placeholder_body": "后续会加入特性、状态、资源与法术相关信息。",
            }

        current_level = int(self._resolve_player_sheet_level(entity) or 0)
        class_label = CLASS_NAME_MAP.get(class_key or "", class_key or "未知职业")
        class_features: list[dict[str, Any]] = []
        for feature in feature_definitions:
            feature_key = str(feature.get("key") or "").strip()
            if not feature_key:
                continue
            resolved_definition = self._resolve_player_sheet_feature_definition(class_key or "", feature)
            level = int(resolved_definition.get("level", 0) or 0)
            if current_level < level:
                continue
            class_features.append(
                {
                    "key": f"{class_key}.{feature_key}",
                    "level": level,
                    "label": resolved_definition.get("label") or feature_key,
                    "description": resolved_definition.get("description") or "",
                    "unlocked": True,
                }
            )

        return {
            "title": "职业特性",
            "class_name": class_key,
            "class_label": class_label,
            "current_level": current_level,
            "class_features": class_features,
        }

    def _resolve_player_sheet_feature_definition(self, class_key: str, feature: dict[str, Any]) -> dict[str, Any]:
        feature_key = str(feature.get("key") or "").strip()
        definition_id = f"{class_key}.{feature_key}" if class_key and feature_key else ""
        definition = self.class_feature_definition_repository.get(definition_id) if definition_id else None
        if not isinstance(definition, dict):
            return {
                "level": int(feature.get("level", 0) or 0),
                "label": feature.get("label") or feature_key,
                "description": feature.get("description") or "",
            }

        level = definition.get("level_required")
        label = definition.get("name_zh") or feature.get("label") or definition.get("name") or feature_key
        description = (
            definition.get("summary_zh")
            or feature.get("description")
            or definition.get("effect_summary")
            or ""
        )
        return {
            "level": int(level or feature.get("level", 0) or 0),
            "label": label,
            "description": description,
        }

    def _select_player_sheet_entity(self, encounter: Encounter) -> EncounterEntity | None:
        for entity_id in encounter.turn_order:
            entity = encounter.entities.get(entity_id)
            if entity is not None and entity.controller == "player" and entity.category == "pc":
                return entity
        for entity in encounter.entities.values():
            if entity.controller == "player" and entity.category == "pc":
                return entity
        for entity_id in encounter.turn_order:
            entity = encounter.entities.get(entity_id)
            if entity is not None and entity.side == "ally":
                return entity
        return self._get_current_entity(encounter)

    def _build_player_sheet_abilities(self, entity: EncounterEntity) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for key in ("str", "dex", "con", "int", "wis", "cha"):
            items.append(
                {
                    "key": key,
                    "label": PLAYER_SHEET_ABILITY_LABELS[key],
                    "score": entity.ability_scores.get(key, 10),
                    "save_bonus": self._calculate_save_bonus(entity, key),
                }
            )
        return items

    def _build_player_sheet_skills(self, entity: EncounterEntity) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for key, label in PLAYER_SHEET_SKILL_LABELS.items():
            ability_key = PLAYER_SHEET_SKILL_ABILITIES[key]
            training_state = self._resolve_player_sheet_skill_training(entity, key, 0, ability_key)
            modifier = self._resolve_player_sheet_skill_modifier(entity, key, ability_key, training_state)
            items.append({"key": key, "label": label, "modifier": modifier})
            items[-1]["ability_label"] = PLAYER_SHEET_ABILITY_LABELS[ability_key]
            items[-1]["training_state"] = training_state
            items[-1]["training_indicator"] = self._player_sheet_training_indicator(training_state)
        return items

    def _resolve_player_sheet_skill_training(
        self,
        entity: EncounterEntity,
        skill_key: str,
        modifier: int,
        ability_key: str,
    ) -> str:
        skill_training = getattr(entity, "skill_training", None)
        if not isinstance(skill_training, dict):
            return "none"
        value = skill_training.get(skill_key)
        if isinstance(value, str) and value in {"none", "proficient", "expertise"}:
            return value
        return "none"

    def _resolve_player_sheet_skill_modifier(
        self,
        entity: EncounterEntity,
        skill_key: str,
        ability_key: str,
        training_state: str,
    ) -> int:
        ability_modifier = int(entity.ability_mods.get(ability_key, 0) or 0)
        proficiency_bonus = int(entity.proficiency_bonus or 0)

        if training_state == "expertise":
            return ability_modifier + proficiency_bonus * 2
        if training_state == "proficient":
            return ability_modifier + proficiency_bonus
        if self._player_sheet_has_bard_jack_of_all_trades(entity):
            return ability_modifier + proficiency_bonus // 2

        modifier = entity.skill_modifiers.get(skill_key)
        if isinstance(modifier, int):
            return modifier
        return ability_modifier

    def _player_sheet_has_bard_jack_of_all_trades(self, entity: EncounterEntity) -> bool:
        source_ref = entity.source_ref if isinstance(entity.source_ref, dict) else {}
        class_name = str(source_ref.get("class_name") or "").strip().lower()
        class_features = entity.class_features if isinstance(entity.class_features, dict) else {}
        if class_name != "bard" and not isinstance(class_features.get("bard"), dict):
            return False
        bard = ensure_bard_runtime(entity)
        jack_of_all_trades = bard.get("jack_of_all_trades")
        return isinstance(jack_of_all_trades, dict) and bool(jack_of_all_trades.get("enabled"))

    def _player_sheet_training_indicator(self, training_state: str) -> str:
        if training_state == "expertise":
            return "🅞"
        if training_state == "proficient":
            return "O"
        return "X"

    def _build_player_sheet_equipment(self, entity: EncounterEntity) -> dict[str, Any]:
        return {
            "weapons": self._build_player_sheet_weapon_items(entity),
            "armor": self._build_player_sheet_armor_items(entity),
            "backpacks": self._build_player_sheet_backpacks(entity),
        }

    def _build_player_sheet_weapon_items(self, entity: EncounterEntity) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for weapon in entity.weapons:
            if not isinstance(weapon, dict):
                continue
            weapon_id = str(weapon.get("weapon_id") or "").strip()
            resolved_weapon = dict(weapon)
            if weapon_id:
                try:
                    resolved_weapon = self.weapon_profile_resolver.resolve(entity, weapon_id)
                except Exception:
                    resolved_weapon = dict(weapon)
            attack_bonus = self._resolve_player_sheet_weapon_attack_bonus(entity, resolved_weapon)
            attack_display = f"D20{self._format_signed_value(attack_bonus)}"
            damage_parts = resolved_weapon.get("damage", [])
            damage_formulas = [
                str(part.get("formula") or "").strip()
                for part in damage_parts
                if isinstance(part, dict) and str(part.get("formula") or "").strip()
            ]
            damage_types = [
                self._localize_damage_type(part.get("type"))
                for part in damage_parts
                if isinstance(part, dict) and part.get("type")
            ]
            properties_text = self._build_player_sheet_weapon_properties(resolved_weapon)
            is_proficient = bool(resolved_weapon.get("is_proficient", False))
            proficient_label = "O" if is_proficient else "X"
            items.append(
                {
                    "name": self._localize_display_name(resolved_weapon.get("name") or weapon.get("name") or weapon.get("weapon_id") or "武器"),
                    "properties": properties_text,
                    "proficient": proficient_label,
                    "attack_display": attack_display,
                    "damage_display": " + ".join(damage_formulas) or "--",
                    "damage_type": " / ".join(damage_types) or "--",
                    "mastery": self._localize_display_name(resolved_weapon.get("mastery") or weapon.get("mastery") or "--"),
                }
            )
        return items

    def _resolve_player_sheet_weapon_attack_bonus(self, entity: EncounterEntity, weapon: dict[str, Any]) -> int:
        attack_bonus_override = weapon.get("attack_bonus_override")
        explicit_attack_bonus = weapon.get("attack_bonus")
        if isinstance(attack_bonus_override, int):
            return attack_bonus_override
        if isinstance(explicit_attack_bonus, int):
            return explicit_attack_bonus
        modifier_name = self._resolve_player_sheet_weapon_modifier_name(entity, weapon)
        modifier_value = int(entity.ability_mods.get(modifier_name, 0) or 0)
        proficiency_bonus = entity.proficiency_bonus if bool(weapon.get("is_proficient", False)) else 0
        return modifier_value + proficiency_bonus

    def _resolve_player_sheet_weapon_modifier_name(self, entity: EncounterEntity, weapon: dict[str, Any]) -> str:
        if self.weapon_profile_resolver.is_monk_weapon(entity, weapon):
            return self.weapon_profile_resolver.resolve_monk_weapon_modifier_name(entity)
        properties = {
            str(entry).strip().lower()
            for entry in weapon.get("properties", [])
            if isinstance(entry, str) and entry.strip()
        }
        kind = str(weapon.get("kind") or "").strip().lower()
        normal_range = int(weapon.get("range", {}).get("normal", 0) or 0)
        if "finesse" in properties:
            str_mod = int(entity.ability_mods.get("str", 0) or 0)
            dex_mod = int(entity.ability_mods.get("dex", 0) or 0)
            return "dex" if dex_mod >= str_mod else "str"
        if kind == "ranged" or normal_range > 10:
            return "dex"
        return "str"

    def _build_player_sheet_weapon_properties(self, weapon: dict[str, Any]) -> str:
        properties: list[str] = []
        raw_properties = weapon.get("properties", [])
        if isinstance(raw_properties, list):
            for value in raw_properties:
                if not isinstance(value, str) or not value.strip():
                    continue
                normalized = value.strip().lower()
                if normalized == "thrown":
                    thrown_range = weapon.get("thrown_range", {})
                    normal = thrown_range.get("normal")
                    long = thrown_range.get("long")
                    if isinstance(normal, int) and isinstance(long, int):
                        properties.append(f"投掷（射程 {normal}/{long}）")
                    else:
                        properties.append("投掷")
                    continue
                properties.append(WEAPON_PROPERTY_MAP.get(normalized, self._localize_display_name(value)))
        return "，".join(properties) or "无"

    def _build_player_sheet_armor_items(self, entity: EncounterEntity) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        armor = self._resolve_player_sheet_armor(entity.equipped_armor)
        if armor is not None:
            armor_ac = armor.get("ac") if isinstance(armor.get("ac"), dict) else {}
            items.append(
                {
                    "name": self._localize_display_name(armor.get("name") or armor.get("armor_id") or "护甲"),
                    "category": self._localize_armor_category(armor.get("category")),
                    "ac": str(armor_ac.get("base", "--")),
                    "dex": self._build_armor_dex_display(entity, armor_ac),
                }
            )
        shield = self._resolve_player_sheet_armor(entity.equipped_shield)
        if shield is not None:
            shield_ac = shield.get("ac") if isinstance(shield.get("ac"), dict) else {}
            items.append(
                {
                    "name": self._localize_display_name(shield.get("name") or shield.get("armor_id") or "盾牌"),
                    "category": "無",
                    "ac": str(shield_ac.get("bonus", 0) or 0),
                    "dex": "0",
                }
            )
        return {"title": "穿戴护甲", "items": items}

    def _build_player_sheet_backpacks(self, entity: EncounterEntity) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for item in entity.inventory:
            if not isinstance(item, dict):
                continue
            quantity = item.get("quantity")
            quantity_label = f"×{quantity}" if isinstance(quantity, int) else str(item.get("quantity_label") or "×1")
            items.append(
                {
                    "name": self._localize_display_name(item.get("name") or item.get("item_id") or "未命名物品"),
                    "quantity": quantity_label,
                }
            )
        gold = entity.currency.get("gp", 0) if isinstance(entity.currency, dict) else 0
        return [{"name": "背包1", "gold": int(gold or 0), "items": items}]

    def _resolve_player_sheet_armor(self, runtime_item: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(runtime_item, dict):
            return None
        armor_id = runtime_item.get("armor_id")
        if not isinstance(armor_id, str) or not armor_id.strip():
            return None
        definition = self.armor_definition_repository.get(armor_id)
        if definition is None:
            return dict(runtime_item)
        resolved = dict(definition)
        resolved.update(runtime_item)
        return resolved

    def _build_armor_dex_display(self, entity: EncounterEntity, armor_ac: dict[str, Any]) -> str:
        if not isinstance(armor_ac, dict):
            return "0"
        if not bool(armor_ac.get("add_dex_modifier", False)):
            return "0"
        dex_mod = entity.ability_mods.get("dex", 0)
        if not isinstance(dex_mod, int):
            dex_mod = 0
        dex_cap = armor_ac.get("dex_cap")
        if isinstance(dex_cap, int):
            dex_mod = min(dex_mod, dex_cap)
        if dex_mod > 0:
            return f"+{dex_mod}"
        if dex_mod < 0:
            return str(dex_mod)
        return "0"

    def _localize_armor_category(self, value: Any) -> str:
        if not isinstance(value, str):
            return "未知"
        return {
            "light": "輕甲",
            "medium": "中甲",
            "heavy": "重甲",
            "shield": "盾牌",
        }.get(value.lower(), value)

    def _format_signed_value(self, value: int) -> str:
        if value > 0:
            return f"+{value}"
        if value < 0:
            return str(value)
        return "+0"

    def _resolve_player_sheet_level(self, entity: EncounterEntity) -> int | None:
        level = self._extract_level(entity)
        if level is not None:
            return level
        for value in entity.class_features.values():
            if isinstance(value, dict):
                candidate = value.get("level")
                if isinstance(candidate, int):
                    return candidate
                for key in ("fighter_level", "paladin_level", "ranger_level", "rogue_level", "warlock_level", "sorcerer_level"):
                    nested = value.get(key)
                    if isinstance(nested, int):
                        return nested
        return None

    def _calculate_save_bonus(self, entity: EncounterEntity, ability_key: str) -> int:
        base_modifier = int(entity.ability_mods.get(ability_key, 0) or 0)
        if ability_key in resolve_entity_save_proficiencies(entity):
            return base_modifier + entity.proficiency_bonus
        return base_modifier

    def _calculate_spell_attack_bonus(self, entity: EncounterEntity) -> int | None:
        spellcasting_ability = entity.source_ref.get("spellcasting_ability")
        if spellcasting_ability is None:
            return None
        ability_mod = entity.ability_mods.get(spellcasting_ability)
        if ability_mod is None:
            return None
        return entity.proficiency_bonus + ability_mod

    def _localize_class_name(self, entity: EncounterEntity) -> str | None:
        class_name = entity.source_ref.get("class_name")
        if not isinstance(class_name, str):
            return None
        return CLASS_NAME_MAP.get(class_name.lower(), class_name)

    def _extract_subclass_name(self, entity: EncounterEntity) -> str | None:
        for key in ("subclass_name", "subclass", "archetype"):
            value = entity.source_ref.get(key)
            if isinstance(value, str) and value.strip():
                return value
        for value in entity.class_features.values():
            if not isinstance(value, dict):
                continue
            for key in ("subclass_name", "subclass", "archetype"):
                nested_value = value.get(key)
                if isinstance(nested_value, str) and nested_value.strip():
                    return nested_value
        return None

    def _build_active_spell_summaries(self, encounter: Encounter) -> list[str]:
        summaries: list[str] = []
        for instance in encounter.spell_instances:
            lifecycle = instance.get("lifecycle", {})
            if lifecycle.get("status") != "active":
                continue

            concentration = instance.get("concentration", {})
            caster_name = instance.get("caster_name") or "未知施法者"
            spell_name = self._localize_display_name(instance.get("spell_name") or instance.get("spell_id") or "未知法术")
            if concentration.get("required") and concentration.get("active"):
                summaries.append(f"{caster_name}正在专注：{spell_name}")
            else:
                summaries.append(f"{caster_name}维持效果：{spell_name}")
        return summaries

    def _build_entity_ongoing_effects(self, encounter: Encounter, entity: EncounterEntity) -> list[str]:
        effect_labels: list[str] = []
        for instance in encounter.spell_instances:
            if not self._is_active_spell_instance(instance):
                continue
            for target in instance.get("targets", []):
                if target.get("entity_id") != entity.entity_id:
                    continue
                effect_labels.append(self._format_spell_source_label(instance))
        effect_labels.extend(build_weapon_mastery_effect_labels(entity))
        for effect in entity.turn_effects or []:
            if not isinstance(effect, dict):
                continue
            effect_type = str(effect.get("effect_type") or "").strip().lower()
            if effect_type == "disengage":
                effect_labels.append("脱离")
            elif effect_type == "dodge":
                effect_labels.append("闪避")
            elif effect_type == "help_attack":
                source_name = effect.get("source_name") or "未知角色"
                effect_labels.append(f"受到{source_name}的协助（攻击）")
            elif effect_type == "help_ability_check":
                source_name = effect.get("source_name") or "未知角色"
                help_check = effect.get("help_check") or {}
                check_key = help_check.get("check_key") or "未知检定"
                effect_labels.append(f"受到{source_name}的协助（{self._localize_check_key(check_key)}）")
        active_grapple = entity.combat_flags.get("active_grapple", {}) if isinstance(entity.combat_flags, dict) else {}
        target_id = active_grapple.get("target_entity_id")
        if isinstance(target_id, str):
            effect_labels.append(f"正在擒抱 {self._entity_name_or_fallback(encounter, target_id, '未知目标')}")
        return self._dedupe_preserve_order(effect_labels)

    def _build_retargetable_spell_actions(
        self,
        encounter: Encounter,
        *,
        current_entity: EncounterEntity | None,
    ) -> list[dict[str, Any]]:
        if current_entity is None:
            return []

        actions: list[dict[str, Any]] = []
        for instance in encounter.spell_instances:
            if not self._is_active_spell_instance(instance):
                continue
            if instance.get("caster_entity_id") != current_entity.entity_id:
                continue

            special_runtime = instance.get("special_runtime")
            if not isinstance(special_runtime, dict):
                continue
            if not bool(special_runtime.get("retargetable")):
                continue
            if not bool(special_runtime.get("retarget_available")):
                continue

            previous_target_id = self._extract_previous_target_id(instance)
            actions.append(
                {
                    "spell_instance_id": instance.get("instance_id"),
                    "spell_id": instance.get("spell_id"),
                    "spell_name": instance.get("spell_name"),
                    "caster_entity_id": instance.get("caster_entity_id"),
                    "caster_name": instance.get("caster_name"),
                    "previous_target_id": previous_target_id,
                    "previous_target_name": self._entity_name_or_fallback(encounter, previous_target_id, "未知目标"),
                    "activation": special_runtime.get("retarget_activation"),
                }
            )
        return actions

    def _build_battlemap_details(self, encounter: Encounter) -> dict[str, Any]:
        return {
            "name": encounter.map.name,
            "description": encounter.map.description,
            "dimensions": f"{encounter.map.width} x {encounter.map.height} 格",
            "grid_size": f"每格代表 {encounter.map.grid_size_feet} 尺",
        }

    def _build_reaction_requests(self, encounter: Encounter) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for request in encounter.reaction_requests:
            if not isinstance(request, dict):
                continue
            items.append(
                {
                    "request_id": request.get("request_id"),
                    "reaction_type": request.get("reaction_type"),
                    "trigger_type": request.get("trigger_type"),
                    "status": request.get("status"),
                    "actor_entity_id": request.get("actor_entity_id"),
                    "actor_name": request.get("actor_name"),
                    "target_entity_id": request.get("target_entity_id"),
                    "target_name": request.get("target_name"),
                    "ask_player": bool(request.get("ask_player")),
                    "auto_resolve": bool(request.get("auto_resolve")),
                    "source_event_type": request.get("source_event_type"),
                    "source_event_id": request.get("source_event_id"),
                    "payload": request.get("payload", {}),
                }
            )
        return items

    def _build_pending_movement(self, encounter: Encounter) -> dict[str, Any] | None:
        pending = encounter.pending_movement
        if not isinstance(pending, dict):
            return None
        return {
            "movement_id": pending.get("movement_id"),
            "entity_id": pending.get("entity_id"),
            "start_position": pending.get("start_position"),
            "target_position": pending.get("target_position"),
            "current_position": pending.get("current_position"),
            "remaining_path": pending.get("remaining_path", []),
            "count_movement": bool(pending.get("count_movement", True)),
            "use_dash": bool(pending.get("use_dash", False)),
            "status": pending.get("status"),
            "waiting_request_id": pending.get("waiting_request_id"),
        }

    def _build_pending_reaction_window(self, encounter: Encounter) -> dict[str, Any] | None:
        pending = encounter.pending_reaction_window
        if not isinstance(pending, dict):
            return None
        return {
            "window_id": pending.get("window_id"),
            "status": pending.get("status"),
            "trigger_event_id": pending.get("trigger_event_id"),
            "trigger_type": pending.get("trigger_type"),
            "blocking": pending.get("blocking"),
            "host_action_type": pending.get("host_action_type"),
            "host_action_id": pending.get("host_action_id"),
            "host_action_snapshot": pending.get("host_action_snapshot", {}),
            "choice_groups": pending.get("choice_groups", []),
            "resolved_group_ids": pending.get("resolved_group_ids", []),
        }

    def _build_spell_area_overlays(self, encounter: Encounter) -> list[dict[str, Any]]:
        overlays: list[dict[str, Any]] = []
        for note in encounter.encounter_notes:
            if not isinstance(note, dict) or note.get("type") != "spell_area_overlay":
                continue
            payload = note.get("payload")
            if isinstance(payload, dict):
                overlays.append(dict(payload))
        return overlays[-1:]

    def _build_recent_forced_movement(self, encounter: Encounter) -> dict[str, Any] | None:
        events = self._list_events_for_encounter(encounter.encounter_id)
        latest_event = None
        latest_index = None
        for index, event in enumerate(events):
            if event.event_type == "forced_movement_resolved":
                latest_event = event
                latest_index = index
        if latest_event is None:
            return None
        if latest_index is not None and latest_index < len(events) - 1:
            return None

        payload = latest_event.payload if isinstance(latest_event.payload, dict) else {}
        source_entity_id = payload.get("source_entity_id") or latest_event.actor_entity_id
        target_entity_id = latest_event.target_entity_id
        source_name = self._entity_name_or_fallback(encounter, source_entity_id, "未知单位")
        target_name = self._entity_name_or_fallback(encounter, target_entity_id, "未知单位")
        start_position = self._normalize_position(payload.get("from_position"))
        final_position = self._normalize_position(payload.get("to_position"))
        attempted_path = self._normalize_path(payload.get("attempted_path"))
        resolved_path = self._normalize_path(payload.get("resolved_path"))
        moved_feet = int(payload.get("moved_feet", 0) or 0)
        blocked = bool(payload.get("blocked", False))
        block_reason = payload.get("block_reason")
        reason = str(payload.get("reason") or "forced_movement")

        return {
            "reason": reason,
            "source_entity_id": source_entity_id,
            "source_name": source_name,
            "target_entity_id": target_entity_id,
            "target_name": target_name,
            "start_position": start_position,
            "final_position": final_position,
            "attempted_path": attempted_path,
            "resolved_path": resolved_path,
            "moved_feet": moved_feet,
            "blocked": blocked,
            "block_reason": block_reason,
            "summary": self._format_forced_movement_summary(
                reason=reason,
                target_name=target_name,
                moved_feet=moved_feet,
                final_position=final_position,
                blocked=blocked,
                block_reason=block_reason,
            ),
        }

    def _build_recent_turn_effects(self, encounter: Encounter) -> list[dict[str, Any]]:
        events = self._list_events_for_encounter(encounter.encounter_id)
        if not events:
            return []
        if events[-1].event_type != "turn_effect_resolved":
            return []

        recent_events: list[Any] = []
        for event in reversed(events):
            if event.event_type != "turn_effect_resolved":
                break
            recent_events.append(event)
        recent_events.reverse()

        items: list[dict[str, Any]] = []
        for event in recent_events:
            payload = event.payload if isinstance(event.payload, dict) else {}
            source_entity_id = payload.get("source_entity_id") or event.actor_entity_id
            target_entity_id = payload.get("target_entity_id") or event.target_entity_id
            name = str(payload.get("name") or "持续效果")
            trigger = str(payload.get("trigger") or "")
            source_name = self._entity_name_or_fallback(encounter, source_entity_id, "未知来源")
            target_name = self._entity_name_or_fallback(encounter, target_entity_id, "未知目标")

            items.append(
                {
                    "effect_id": payload.get("effect_id"),
                    "name": name,
                    "trigger": trigger,
                    "source_entity_id": source_entity_id,
                    "source_name": source_name,
                    "target_entity_id": target_entity_id,
                    "target_name": target_name,
                    "save": payload.get("save"),
                    "condition_updates": payload.get("condition_updates", []),
                    "effect_removed": bool(payload.get("effect_removed", False)),
                    "summary": self._format_turn_effect_summary(
                        name=name,
                        trigger=trigger,
                        source_name=source_name,
                        target_name=target_name,
                        save=payload.get("save"),
                        trigger_damage_resolution=payload.get("trigger_damage_resolution"),
                        success_damage_resolution=payload.get("success_damage_resolution"),
                        failure_damage_resolution=payload.get("failure_damage_resolution"),
                        condition_updates=payload.get("condition_updates"),
                        effect_removed=bool(payload.get("effect_removed", False)),
                    ),
                }
            )
        return items

    def _build_recent_activity(self, encounter: Encounter) -> list[dict[str, Any]]:
        events = self._list_events_for_encounter(encounter.encounter_id)
        items: list[dict[str, Any]] = []
        for event in reversed(events):
            item = self._build_recent_activity_item(encounter, event)
            if item is None:
                continue
            items.append(item)
            if len(items) >= 6:
                break
        return items

    def _build_recent_activity_item(self, encounter: Encounter, event: Any) -> dict[str, Any] | None:
        event_type = getattr(event, "event_type", None)
        if not isinstance(event_type, str):
            return None

        payload = event.payload if isinstance(event.payload, dict) else {}
        actor_name = self._entity_name_or_fallback(encounter, event.actor_entity_id, "未知单位")
        target_name = self._entity_name_or_fallback(encounter, event.target_entity_id, "未知目标")
        summary = self._format_recent_activity_summary(
            encounter=encounter,
            event_type=event_type,
            payload=payload,
            actor_name=actor_name,
            target_name=target_name,
        )
        if summary is None:
            return None

        return {
            "event_id": event.event_id,
            "event_type": event_type,
            "round": event.round,
            "actor_entity_id": event.actor_entity_id,
            "actor_name": actor_name,
            "target_entity_id": event.target_entity_id,
            "target_name": target_name,
            "summary": summary,
        }

    def _format_recent_activity_summary(
        self,
        *,
        encounter: Encounter,
        event_type: str,
        payload: dict[str, Any],
        actor_name: str,
        target_name: str,
    ) -> str | None:
        if event_type == "movement_resolved":
            from_position = self._format_compact_position(self._normalize_position(payload.get("from_position")))
            to_position = self._format_compact_position(self._normalize_position(payload.get("to_position")))
            feet_cost = payload.get("feet_cost")
            dash_text = "，使用了疾跑" if bool(payload.get("used_dash")) else ""
            cost_text = f"，消耗 {feet_cost} 尺移动力" if isinstance(feet_cost, int) else ""
            return f"{actor_name}从 {from_position} 移动到 {to_position}{cost_text}{dash_text}。"
        if event_type == "attack_resolved":
            attack_name = self._localize_display_name(payload.get("attack_name") or "攻击")
            final_total = payload.get("final_total")
            target_ac = payload.get("target_ac")
            if bool(payload.get("hit")):
                critical_text = "，造成重击" if bool(payload.get("is_critical_hit")) else ""
                return f"{actor_name}用{attack_name}命中{target_name}（{final_total} 对 AC {target_ac}）{critical_text}。"
            return f"{actor_name}用{attack_name}攻击{target_name}未命中（{final_total} 对 AC {target_ac}）。"
        if event_type == "damage_applied":
            hp_change = payload.get("hp_change")
            reason = self._localize_display_name(payload.get("reason") or "伤害")
            if isinstance(hp_change, int):
                return f"{actor_name}对{target_name}造成 {hp_change} 点伤害（{reason}）。"
            return f"{target_name}受到伤害（{reason}）。"
        if event_type == "healing_applied":
            hp_change = payload.get("hp_change")
            reason = self._localize_display_name(payload.get("reason") or "治疗")
            if isinstance(hp_change, int):
                return f"{actor_name}为{target_name}恢复 {abs(hp_change)} 点生命（{reason}）。"
            return f"{target_name}恢复了生命值（{reason}）。"
        if event_type == "spell_declared":
            spell_name = self._localize_display_name(payload.get("spell_name") or payload.get("spell_id") or "法术")
            target_ids = payload.get("target_ids")
            target_label = ""
            if isinstance(target_ids, list) and target_ids:
                target_names = [
                    self._entity_name_or_fallback(encounter, target_id, "未知目标")
                    for target_id in target_ids
                    if isinstance(target_id, str)
                ]
                if target_names:
                    target_label = f"，目标：{'、'.join(target_names)}"
            cast_level = payload.get("cast_level")
            cast_level_text = f"（{cast_level}环）" if isinstance(cast_level, int) and cast_level > 0 else ""
            return f"{actor_name}施放了{spell_name}{cast_level_text}{target_label}。"
        if event_type == "saving_throw_resolved":
            spell_name = self._localize_display_name(payload.get("spell_name") or payload.get("spell_id") or "法术效果")
            save_ability = str(payload.get("save_ability") or "").upper()
            final_total = payload.get("final_total")
            save_dc = payload.get("save_dc")
            result = "成功" if bool(payload.get("success")) else "失败"
            if save_ability:
                return f"{target_name}对{spell_name}进行 {save_ability} 豁免，结果 {final_total} 对 DC {save_dc}，{result}。"
            return f"{target_name}对{spell_name}进行豁免，结果 {result}。"
        if event_type == "forced_movement_resolved":
            source_entity_id = payload.get("source_entity_id")
            target_entity_id = payload.get("target_entity_id")
            source_name = self._entity_name_or_fallback(encounter, source_entity_id, actor_name)
            forced_target_name = self._entity_name_or_fallback(encounter, target_entity_id, target_name)
            return self._format_forced_movement_summary(
                reason=str(payload.get("reason") or "forced_movement"),
                target_name=forced_target_name,
                moved_feet=int(payload.get("moved_feet", 0) or 0),
                final_position=self._normalize_position(payload.get("to_position")),
                blocked=bool(payload.get("blocked", False)),
                block_reason=payload.get("block_reason"),
            ).replace(forced_target_name, forced_target_name, 1)
        if event_type == "zone_effect_resolved":
            zone_name = str(payload.get("zone_name") or payload.get("zone_id") or "区域效果")
            zone_target_name = self._entity_name_or_fallback(encounter, payload.get("target_entity_id"), target_name)
            damage_text = self._format_damage_resolution_summary(payload.get("damage_resolution"))
            condition_text = self._format_turn_effect_condition_summary(payload.get("condition_updates"))
            trigger_label = {
                "enter": "进入区域时",
                "start_of_turn_inside": "回合开始时",
                "end_of_turn_inside": "回合结束时",
            }.get(str(payload.get("trigger") or ""), "区域触发时")
            parts = [f"{zone_target_name}{trigger_label}触发了{zone_name}。"]
            if damage_text is not None:
                parts.append(damage_text)
            if condition_text is not None:
                parts.append(condition_text)
            return " ".join(parts)
        if event_type == "turn_effect_resolved":
            return self._format_turn_effect_summary(
                name=str(payload.get("name") or "持续效果"),
                trigger=str(payload.get("trigger") or ""),
                source_name=self._entity_name_or_fallback(encounter, payload.get("source_entity_id"), actor_name),
                target_name=self._entity_name_or_fallback(encounter, payload.get("target_entity_id"), target_name),
                save=payload.get("save"),
                trigger_damage_resolution=payload.get("trigger_damage_resolution"),
                success_damage_resolution=payload.get("success_damage_resolution"),
                failure_damage_resolution=payload.get("failure_damage_resolution"),
                condition_updates=payload.get("condition_updates"),
                effect_removed=bool(payload.get("effect_removed", False)),
            )
        if event_type == "turn_ended":
            return f"{actor_name}结束了自己的回合。"
        if event_type == "spell_retargeted":
            spell_name = self._localize_display_name(payload.get("spell_name") or payload.get("spell_id") or "标记法术")
            previous_target_name = self._entity_name_or_fallback(encounter, payload.get("previous_target_id"), "未知目标")
            new_target_name = self._entity_name_or_fallback(encounter, payload.get("new_target_id"), "未知目标")
            return f"{actor_name}将{spell_name}从{previous_target_name}转移到了{new_target_name}。"
        return None

    def _build_weapons_view(self, entity: EncounterEntity) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for index, weapon in enumerate(entity.weapons):
            damage_parts = weapon.get("damage", [])
            damage_text = " + ".join(
                f"{part['formula']} {self._localize_damage_type(part['type'])}"
                for part in damage_parts
                if "formula" in part and "type" in part
            )
            items.append(
                {
                    "slot": weapon.get("slot", f"weapon_{index + 1}"),
                    "weapon_id": weapon.get("weapon_id"),
                    "name": self._localize_display_name(weapon.get("name")),
                    "damage": damage_text,
                    "properties": weapon.get("properties", []),
                    "bonus": self._format_weapon_bonus(weapon),
                    "note": weapon.get("note"),
                }
            )
        return items

    def _build_spells_view(self, entity: EncounterEntity) -> dict[str, list[dict[str, Any]]]:
        grouped_spells: dict[str, list[dict[str, Any]]] = {"cantrips": []}
        for spell in entity.spells:
            spell_level = spell.get("level", 0)
            if spell_level == 0:
                group_key = "cantrips"
            else:
                group_key = f"level_{spell_level}_spells"
                grouped_spells.setdefault(group_key, [])

            grouped_spells[group_key].append(
                {
                    "id": spell.get("spell_id"),
                    "name": self._localize_display_name(spell.get("name")),
                    "description": spell.get("description"),
                    "damage": spell.get("damage", []),
                    "requires_attack_roll": spell.get("requires_attack_roll", False),
                    "at_higher_levels": spell.get("at_higher_levels"),
                }
            )
        return grouped_spells

    def _build_spell_slots_view(self, entity: EncounterEntity) -> dict[str, int]:
        return build_available_spell_slots_view(entity)

    def _build_weapon_ranges(self, encounter: Encounter, entity: EncounterEntity) -> dict[str, Any]:
        max_melee_range = self._max_melee_range(entity)
        max_ranged_range = self._max_ranged_range(entity)
        enemy_targets = [
            other_entity
            for other_entity in encounter.entities.values()
            if other_entity.entity_id != entity.entity_id and other_entity.side != entity.side
        ]

        return {
            "max_melee_range": f"{max_melee_range} 尺" if max_melee_range else "0 尺",
            "max_ranged_range": f"{max_ranged_range} 尺" if max_ranged_range else "0 尺",
            "targets_within_melee_range": self._filter_targets_by_range(entity, enemy_targets, max_melee_range),
            "targets_within_ranged_range": self._filter_targets_by_range(entity, enemy_targets, max_ranged_range),
        }

    def _build_actions(self, entity: EncounterEntity) -> dict[str, bool]:
        action_economy = entity.action_economy or {}
        return {
            "action_used": bool(action_economy.get("action_used")),
            "bonus_action_used": bool(action_economy.get("bonus_action_used")),
            "reaction_used": bool(action_economy.get("reaction_used")),
            "free_interaction_used": bool(action_economy.get("free_interaction_used")),
        }

    def _build_spellcasting_state(self, entity: EncounterEntity) -> dict[str, Any]:
        action_economy = entity.action_economy or {}
        spell_slot_cast_used_this_turn = bool(action_economy.get("spell_slot_cast_used_this_turn"))
        return {
            "spell_slot_cast_used_this_turn": spell_slot_cast_used_this_turn,
            "spell_slot_cast_available_this_turn": not spell_slot_cast_used_this_turn,
            "reaction_spell_exception": True,
            "item_cast_exception": True,
            "non_slot_cast_exception": True,
            "summary": (
                "本回合已通过自身施法消耗过一次法术位；动作/附赠动作的再次耗位施法受限，反应法术、物品施法与其他不消耗法术位的施法例外。"
                if spell_slot_cast_used_this_turn
                else "本回合还可以通过自身施法消耗一次法术位。"
            ),
        }

    def _filter_targets_by_range(
        self,
        source_entity: EncounterEntity,
        targets: list[EncounterEntity],
        max_range_feet: int,
    ) -> list[dict[str, str]]:
        if max_range_feet <= 0:
            return []

        visible_targets: list[dict[str, str]] = []
        for target in targets:
            distance_feet = self._distance_feet(source_entity, target)
            if distance_feet <= max_range_feet:
                visible_targets.append(
                    {
                        "entity_id": target.entity_id,
                        "name": target.name,
                        "distance": f"{distance_feet} 尺",
                    }
                )
        return visible_targets

    def _build_enemy_tactical_brief(
        self,
        encounter: Encounter,
        actor: EncounterEntity,
    ) -> dict[str, Any] | None:
        if actor.controller != "gm" or actor.side != "enemy":
            return None

        max_melee_range = self._max_melee_range(actor)
        if max_melee_range <= 0:
            return None

        potential_targets = self._list_enemy_tactical_targets(encounter, actor)
        in_range_targets = [target for target in potential_targets if self._distance_feet(actor, target) <= max_melee_range]
        candidate_lowest_ac = min((target.ac for target in in_range_targets), default=None)
        candidate_targets: list[dict[str, Any]] = []
        for target in in_range_targets:
            distance_feet = self._distance_feet(actor, target)
            score = self._score_enemy_tactical_target(target, candidate_lowest_ac)
            has_active_concentration = self._has_active_concentration(target)
            attack_has_advantage = self._attack_has_advantage_against_target(target)
            candidate_targets.append(
                {
                    "entity_id": target.entity_id,
                    "in_attack_range": True,
                    "score": score,
                    "attack_has_advantage": attack_has_advantage,
                    "priority_reason": self._build_enemy_tactical_priority_reason(target, candidate_lowest_ac),
                    "_has_active_concentration": has_active_concentration,
                    "_distance_feet": distance_feet,
                }
            )

        top_score = max((float(item["score"]) for item in candidate_targets), default=0.0)

        candidate_targets.sort(
            key=lambda item: (
                0
                if bool(item["_has_active_concentration"])
                and (top_score - float(item["score"])) <= ENEMY_TACTICAL_BRIEF_CLOSE_SCORE_WINDOW
                else 1,
                -float(item["score"]),
                int(item["_distance_feet"]),
                str(item["entity_id"]),
            )
        )
        top_candidates: list[dict[str, Any]] = []
        for item in candidate_targets[:2]:
            top_candidates.append(
                {
                    "entity_id": item["entity_id"],
                    "in_attack_range": item["in_attack_range"],
                    "score": item["score"],
                    "attack_has_advantage": item["attack_has_advantage"],
                    "priority_reason": item["priority_reason"],
                }
            )
        reachable_targets = build_enemy_reachable_targets(
            encounter,
            actor,
            targets=potential_targets,
            max_melee_range=max_melee_range,
            score_target=self._score_enemy_tactical_target,
        )
        return {
            "candidate_targets": top_candidates,
            "reachable_targets": reachable_targets,
            "recommended_tactic": self._build_enemy_melee_recommended_tactic(
                encounter=encounter,
                actor=actor,
                candidates=top_candidates,
                reachable_targets=reachable_targets,
            ),
        }

    def _build_enemy_ranged_tactical_brief(
        self,
        encounter: Encounter,
        actor: EncounterEntity,
    ) -> dict[str, Any] | None:
        if actor.controller != "gm" or actor.side != "enemy":
            return None

        max_melee_range = self._max_melee_range(actor)
        max_ranged_range = self._max_ranged_range(actor)
        if max_ranged_range <= 0 or max_melee_range > 0:
            return None

        threat_sources = self._list_enemy_ranged_threat_sources(encounter, actor)
        bloodied = self._is_bloodied(actor)
        projected_candidates = self._build_enemy_ranged_candidate_targets(
            encounter,
            actor,
            attack_disadvantage=bool(threat_sources),
        )

        fallback_options = self._build_enemy_ranged_fallback_options(
            encounter,
            actor,
            threat_sources=threat_sources,
            targets=[
                target
                for target in self._list_enemy_tactical_targets(encounter, actor)
                if self._distance_feet(actor, target) <= max_ranged_range
            ],
            max_ranged_range=max_ranged_range,
        )
        return {
            "candidate_targets": projected_candidates,
            "pressure_state": {
                "threatened_in_melee": bool(threat_sources),
                "threat_source_ids": [source.entity_id for source in threat_sources],
                "bloodied": bloodied,
                "stay_and_shoot_penalty": self._build_enemy_ranged_penalty_label(
                    threatened_in_melee=bool(threat_sources),
                    bloodied=bloodied,
                ),
            },
            "fallback_options": fallback_options,
            "recommended_tactic": self._build_enemy_ranged_recommended_tactic(
                encounter=encounter,
                actor=actor,
                candidates=projected_candidates,
                threatened_in_melee=bool(threat_sources),
                bloodied=bloodied,
                fallback_options=fallback_options,
            ),
        }

    def _build_enemy_hybrid_tactical_brief(
        self,
        encounter: Encounter,
        actor: EncounterEntity,
    ) -> dict[str, Any] | None:
        if actor.controller != "gm" or actor.side != "enemy":
            return None

        melee_weapons = self._list_weapons_by_kind(actor, kind="melee")
        ranged_weapons = self._list_weapons_by_kind(actor, kind="ranged")
        save_actions = self._list_hybrid_save_actions(actor)
        if not melee_weapons or not ranged_weapons or not save_actions:
            return None

        melee_brief = self._build_enemy_tactical_brief(encounter, actor)
        ranged_candidates = self._build_enemy_ranged_candidate_targets(
            encounter,
            actor,
            attack_disadvantage=False,
        )
        save_target = self._select_hybrid_save_action_target(encounter, actor)

        available_modes: list[str] = []
        if melee_brief is not None and melee_brief.get("candidate_targets"):
            available_modes.append("melee_attack")
        if ranged_candidates:
            available_modes.append("ranged_attack")
        if save_target is not None:
            available_modes.append("save_action")
        if not available_modes:
            return None

        if "melee_attack" in available_modes:
            melee_target_id = str(melee_brief["candidate_targets"][0]["entity_id"])
            melee_target = encounter.entities.get(melee_target_id)
            melee_weapon = self._select_best_weapon_for_target(actor, melee_target, kind="melee")
            melee_hit_chance = self._estimate_weapon_hit_chance(melee_weapon, melee_target)
            preferred_melee_sequence = self._select_multiattack_sequence_for_mode(
                encounter=encounter,
                actor=actor,
                target=melee_target,
                mode="melee",
                prefer_high_ac=melee_hit_chance <= ENEMY_HYBRID_LOW_HIT_CHANCE_THRESHOLD,
            )
            if (
                melee_hit_chance <= ENEMY_HYBRID_LOW_HIT_CHANCE_THRESHOLD
                and "save_action" in available_modes
                and preferred_melee_sequence is not None
                and self._multiattack_sequence_contains_special_action(preferred_melee_sequence)
            ):
                return {
                    "available_modes": available_modes,
                    "recommended_mode": "multiattack",
                    "reason": "目标甲高，先用吸取生命压制再补一击",
                    "target_entity_id": save_target["target_entity_id"],
                    "selected_weapon_id": self._extract_primary_weapon_id_from_multiattack_sequence(preferred_melee_sequence),
                    "selected_action_id": self._extract_primary_special_action_id_from_multiattack_sequence(preferred_melee_sequence),
                    "recommended_tactic": {
                        "action": "multiattack",
                        "target_entity_id": save_target["target_entity_id"],
                        "selected_weapon_id": self._extract_primary_weapon_id_from_multiattack_sequence(preferred_melee_sequence),
                        "selected_action_id": self._extract_primary_special_action_id_from_multiattack_sequence(preferred_melee_sequence),
                        "reason": "目标甲高，先用吸取生命压制再补一击",
                        "execution_plan": self._build_multiattack_sequence_execution_plan(
                            encounter=encounter,
                            actor=actor,
                            target_entity_id=melee_target_id,
                            sequence=preferred_melee_sequence,
                        ),
                    },
                }
            if preferred_melee_sequence is not None:
                return {
                    "available_modes": available_modes,
                    "recommended_mode": "multiattack",
                    "reason": "已贴近目标，优先用多重攻击施压",
                    "target_entity_id": melee_target_id,
                    "selected_weapon_id": self._extract_primary_weapon_id_from_multiattack_sequence(preferred_melee_sequence),
                    "selected_action_id": self._extract_primary_special_action_id_from_multiattack_sequence(preferred_melee_sequence),
                    "recommended_tactic": {
                        "action": "multiattack",
                        "target_entity_id": melee_target_id,
                        "selected_weapon_id": self._extract_primary_weapon_id_from_multiattack_sequence(preferred_melee_sequence),
                        "selected_action_id": self._extract_primary_special_action_id_from_multiattack_sequence(preferred_melee_sequence),
                        "reason": "已贴近目标，优先用多重攻击施压",
                        "execution_plan": self._build_multiattack_sequence_execution_plan(
                            encounter=encounter,
                            actor=actor,
                            target_entity_id=melee_target_id,
                            sequence=preferred_melee_sequence,
                        ),
                    },
                }
            return {
                "available_modes": available_modes,
                "recommended_mode": "melee_attack",
                "reason": "已贴近目标，先用近战施压",
                "target_entity_id": melee_target_id,
                "selected_weapon_id": None if melee_weapon is None else melee_weapon.get("weapon_id"),
                "selected_action_id": None,
                "recommended_tactic": {
                    "action": "melee_attack",
                    "target_entity_id": melee_target_id,
                    "selected_weapon_id": None if melee_weapon is None else melee_weapon.get("weapon_id"),
                    "selected_action_id": None,
                    "reason": "已贴近目标，先用近战施压",
                    "execution_plan": []
                    if melee_weapon is None
                    else [
                        self._build_execute_attack_step(
                            encounter_id=encounter.encounter_id,
                            actor_id=actor.entity_id,
                            target_id=melee_target_id,
                            weapon_id=str(melee_weapon.get("weapon_id")),
                        )
                    ],
                },
            }

        if "ranged_attack" in available_modes:
            ranged_target_id = str(ranged_candidates[0]["entity_id"])
            ranged_target = encounter.entities.get(ranged_target_id)
            ranged_weapon = self._select_best_weapon_for_target(actor, ranged_target, kind="ranged")
            preferred_ranged_sequence = self._select_multiattack_sequence_for_mode(
                encounter=encounter,
                actor=actor,
                target=ranged_target,
                mode="ranged",
                prefer_high_ac=False,
            )
            if preferred_ranged_sequence is not None:
                return {
                    "available_modes": available_modes,
                    "recommended_mode": "multiattack",
                    "reason": "暂时接不上近战，优先用死灵弓多重压制",
                    "target_entity_id": ranged_target_id,
                    "selected_weapon_id": self._extract_primary_weapon_id_from_multiattack_sequence(preferred_ranged_sequence),
                    "selected_action_id": self._extract_primary_special_action_id_from_multiattack_sequence(preferred_ranged_sequence),
                    "recommended_tactic": {
                        "action": "multiattack",
                        "target_entity_id": ranged_target_id,
                        "selected_weapon_id": self._extract_primary_weapon_id_from_multiattack_sequence(preferred_ranged_sequence),
                        "selected_action_id": self._extract_primary_special_action_id_from_multiattack_sequence(preferred_ranged_sequence),
                        "reason": "暂时接不上近战，优先用死灵弓多重压制",
                        "execution_plan": self._build_multiattack_sequence_execution_plan(
                            encounter=encounter,
                            actor=actor,
                            target_entity_id=ranged_target_id,
                            sequence=preferred_ranged_sequence,
                        ),
                    },
                }
            return {
                "available_modes": available_modes,
                "recommended_mode": "ranged_attack",
                "reason": "暂时接不上近战，先用远程压制",
                "target_entity_id": ranged_target_id,
                "selected_weapon_id": None if ranged_weapon is None else ranged_weapon.get("weapon_id"),
                "selected_action_id": None,
                "recommended_tactic": {
                    "action": "ranged_attack",
                    "target_entity_id": ranged_target_id,
                    "selected_weapon_id": None if ranged_weapon is None else ranged_weapon.get("weapon_id"),
                    "selected_action_id": None,
                    "reason": "暂时接不上近战，先用远程压制",
                    "execution_plan": []
                    if ranged_weapon is None
                    else [
                        self._build_execute_attack_step(
                            encounter_id=encounter.encounter_id,
                            actor_id=actor.entity_id,
                            target_id=ranged_target_id,
                            weapon_id=str(ranged_weapon.get("weapon_id")),
                        )
                    ],
                },
            }

        return {
            "available_modes": available_modes,
            "recommended_mode": "save_action",
            "reason": "当前以豁免动作最合适",
            "target_entity_id": save_target["target_entity_id"],
            "selected_weapon_id": None,
            "selected_action_id": save_target["action_id"],
            "recommended_tactic": {
                "action": "save_action",
                "target_entity_id": save_target["target_entity_id"],
                "selected_weapon_id": None,
                "selected_action_id": save_target["action_id"],
                "reason": "当前以豁免动作最合适",
                "execution_plan": [
                    self._build_special_action_execution_step(
                        encounter=encounter,
                        actor=actor,
                        action_id=save_target["action_id"],
                        target_entity_id=save_target["target_entity_id"],
                    )
                ],
            },
        }

    def _has_multiattack_action(
        self,
        actor: EncounterEntity,
    ) -> bool:
        source_ref = actor.source_ref if isinstance(actor.source_ref, dict) else {}
        raw_items = source_ref.get("actions_metadata")
        if not isinstance(raw_items, list):
            return False
        return any(
            isinstance(item, dict) and str(item.get("action_id") or "").strip() == "multiattack"
            for item in raw_items
        )

    def _get_multiattack_sequences(
        self,
        actor: EncounterEntity,
        *,
        mode: str | None = None,
    ) -> list[dict[str, Any]]:
        source_ref = actor.source_ref if isinstance(actor.source_ref, dict) else {}
        raw_items = source_ref.get("actions_metadata")
        if not isinstance(raw_items, list):
            return []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            if str(item.get("action_id") or "").strip() != "multiattack":
                continue
            raw_sequences = item.get("multiattack_sequences")
            if not isinstance(raw_sequences, list):
                return []
            sequences = [sequence for sequence in raw_sequences if isinstance(sequence, dict)]
            if mode is None:
                return sequences
            return [sequence for sequence in sequences if str(sequence.get("mode") or "").strip() == mode]
        return []

    def _select_multiattack_sequence_for_mode(
        self,
        *,
        encounter: Encounter,
        actor: EncounterEntity,
        target: EncounterEntity | None,
        mode: str,
        prefer_high_ac: bool,
    ) -> dict[str, Any] | None:
        if target is None:
            return None
        candidates: list[dict[str, Any]] = []
        for sequence in self._get_multiattack_sequences(actor, mode=mode):
            if not self._multiattack_sequence_can_target(
                encounter=encounter,
                actor=actor,
                target=target,
                sequence=sequence,
            ):
                continue
            candidates.append(sequence)
        if not candidates:
            return None
        candidates.sort(
            key=lambda sequence: (
                0 if self._multiattack_sequence_matches_preference(sequence, prefer_high_ac=prefer_high_ac) else 1,
                0 if self._multiattack_sequence_contains_special_action(sequence) else 1,
                -len(sequence.get("steps", [])) if isinstance(sequence.get("steps"), list) else 0,
                str(sequence.get("sequence_id") or ""),
            )
        )
        return candidates[0]

    def _multiattack_sequence_matches_preference(
        self,
        sequence: dict[str, Any],
        *,
        prefer_high_ac: bool,
    ) -> bool:
        tags = {
            str(tag).strip()
            for tag in sequence.get("tags", [])
            if str(tag).strip()
        } if isinstance(sequence.get("tags"), list) else set()
        tagged_for_high_ac = "prefer_high_ac" in tags
        return tagged_for_high_ac if prefer_high_ac else not tagged_for_high_ac

    def _multiattack_sequence_contains_special_action(
        self,
        sequence: dict[str, Any],
    ) -> bool:
        steps = sequence.get("steps")
        if not isinstance(steps, list):
            return False
        return any(
            isinstance(step, dict) and str(step.get("type") or "").strip() == "special_action"
            for step in steps
        )

    def _extract_primary_weapon_id_from_multiattack_sequence(
        self,
        sequence: dict[str, Any],
    ) -> str | None:
        steps = sequence.get("steps")
        if not isinstance(steps, list):
            return None
        for step in steps:
            if not isinstance(step, dict):
                continue
            if str(step.get("type") or "").strip() != "weapon":
                continue
            weapon_id = str(step.get("weapon_id") or "").strip()
            if weapon_id:
                return weapon_id
        return None

    def _extract_primary_special_action_id_from_multiattack_sequence(
        self,
        sequence: dict[str, Any],
    ) -> str | None:
        steps = sequence.get("steps")
        if not isinstance(steps, list):
            return None
        for step in steps:
            if not isinstance(step, dict):
                continue
            if str(step.get("type") or "").strip() != "special_action":
                continue
            action_id = str(step.get("action_id") or "").strip()
            if action_id:
                return action_id
        return None

    def _multiattack_sequence_can_target(
        self,
        *,
        encounter: Encounter,
        actor: EncounterEntity,
        target: EncounterEntity,
        sequence: dict[str, Any],
    ) -> bool:
        steps = sequence.get("steps")
        if not isinstance(steps, list) or not steps:
            return False
        for step in steps:
            if not isinstance(step, dict):
                return False
            step_type = str(step.get("type") or "").strip()
            if step_type == "weapon":
                weapon_id = str(step.get("weapon_id") or "").strip()
                weapon = next(
                    (
                        weapon_candidate
                        for weapon_candidate in actor.weapons
                        if isinstance(weapon_candidate, dict)
                        and str(weapon_candidate.get("weapon_id") or "").strip() == weapon_id
                    ),
                    None,
                )
                if weapon is None or self._distance_feet(actor, target) > self._resolve_weapon_max_range(weapon):
                    return False
                continue
            if step_type == "special_action":
                action_id = str(step.get("action_id") or "").strip()
                action = self._find_action_metadata(actor, action_id)
                if action is None:
                    return False
                range_feet = int(action.get("range_feet", 0) or 0)
                if range_feet > 0 and self._distance_feet(actor, target) > range_feet:
                    return False
                continue
            return False
        return True

    def _find_action_metadata(
        self,
        actor: EncounterEntity,
        action_id: str,
    ) -> dict[str, Any] | None:
        source_ref = actor.source_ref if isinstance(actor.source_ref, dict) else {}
        raw_items = source_ref.get("actions_metadata")
        if not isinstance(raw_items, list):
            return None
        normalized_action_id = str(action_id or "").strip()
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            if str(item.get("action_id") or "").strip() == normalized_action_id:
                return item
        return None

    def _build_multiattack_sequence_execution_plan(
        self,
        *,
        encounter: Encounter,
        actor: EncounterEntity,
        target_entity_id: str,
        sequence: dict[str, Any],
    ) -> list[dict[str, Any]]:
        plan: list[dict[str, Any]] = []
        steps = sequence.get("steps")
        if not isinstance(steps, list):
            return plan
        for step in steps:
            if not isinstance(step, dict):
                continue
            step_type = str(step.get("type") or "").strip()
            if step_type == "special_action":
                action_id = str(step.get("action_id") or "").strip()
                if not action_id:
                    continue
                plan.append(
                    self._build_special_action_execution_step(
                        encounter=encounter,
                        actor=actor,
                        action_id=action_id,
                        target_entity_id=target_entity_id,
                    )
                )
                continue
            if step_type == "weapon":
                weapon_id = str(step.get("weapon_id") or "").strip()
                if not weapon_id:
                    continue
                plan.append(
                    self._build_execute_attack_step(
                        encounter_id=encounter.encounter_id,
                        actor_id=actor.entity_id,
                        target_id=target_entity_id,
                        weapon_id=weapon_id,
                    )
                )
        return plan

    def _build_enemy_ranged_candidate_targets(
        self,
        encounter: Encounter,
        actor: EncounterEntity,
        *,
        attack_disadvantage: bool,
    ) -> list[dict[str, Any]]:
        max_ranged_range = self._max_ranged_range(actor)
        if max_ranged_range <= 0:
            return []

        potential_targets = self._list_enemy_tactical_targets(encounter, actor)
        candidate_targets = [target for target in potential_targets if self._distance_feet(actor, target) <= max_ranged_range]
        lowest_ac = min((target.ac for target in candidate_targets), default=None)
        scored_candidates: list[dict[str, Any]] = []
        for target in candidate_targets:
            scored_candidates.append(
                {
                    "entity_id": target.entity_id,
                    "score": self._score_enemy_ranged_tactical_target(target, lowest_ac),
                    "in_effective_range": True,
                    "attack_disadvantage": attack_disadvantage,
                    "priority_reason": self._build_enemy_ranged_priority_reason(target, lowest_ac),
                    "_distance_feet": self._distance_feet(actor, target),
                    "_has_active_concentration": self._has_active_concentration(target),
                }
            )

        top_score = max((float(item["score"]) for item in scored_candidates), default=0.0)
        scored_candidates.sort(
            key=lambda item: (
                0
                if bool(item["_has_active_concentration"])
                and (top_score - float(item["score"])) <= ENEMY_TACTICAL_BRIEF_CLOSE_SCORE_WINDOW
                else 1,
                -float(item["score"]),
                int(item["_distance_feet"]),
                str(item["entity_id"]),
            )
        )
        return [
            {
                "entity_id": item["entity_id"],
                "score": item["score"],
                "in_effective_range": item["in_effective_range"],
                "attack_disadvantage": item["attack_disadvantage"],
                "priority_reason": item["priority_reason"],
            }
            for item in scored_candidates[:2]
        ]

    def _score_enemy_tactical_target(self, target: EncounterEntity, lowest_ac_in_pool: int | None = None) -> float:
        return self._score_enemy_target_value(
            target,
            lowest_ac_in_pool=lowest_ac_in_pool,
            advantage_bonus=1.0,
            low_hp_threshold_bonus=2.0,
            low_hp_ratio_bonus_scale=4.0,
            bloodied_bonus=0.0,
            critical_hp_bonus=0.0,
        )

    def _score_enemy_ranged_tactical_target(self, target: EncounterEntity, lowest_ac_in_pool: int | None = None) -> float:
        return self._score_enemy_target_value(
            target,
            lowest_ac_in_pool=lowest_ac_in_pool,
            advantage_bonus=2.0,
            low_hp_threshold_bonus=0.0,
            low_hp_ratio_bonus_scale=0.0,
            bloodied_bonus=1.5,
            critical_hp_bonus=1.0,
        )

    def _build_enemy_tactical_priority_reason(self, target: EncounterEntity, lowest_ac_in_pool: int | None = None) -> str:
        return self._build_enemy_target_priority_reason(
            target,
            lowest_ac_in_pool=lowest_ac_in_pool,
            prefer_low_ac_before_advantage=False,
            low_hp_if_threshold=True,
            low_hp_if_bloodied=True,
        )

    def _build_enemy_ranged_priority_reason(self, target: EncounterEntity, lowest_ac_in_pool: int | None = None) -> str:
        return self._build_enemy_target_priority_reason(
            target,
            lowest_ac_in_pool=lowest_ac_in_pool,
            prefer_low_ac_before_advantage=True,
            low_hp_if_threshold=False,
            low_hp_if_bloodied=True,
        )

    def _score_enemy_target_value(
        self,
        target: EncounterEntity,
        *,
        lowest_ac_in_pool: int | None,
        advantage_bonus: float,
        low_hp_threshold_bonus: float,
        low_hp_ratio_bonus_scale: float,
        bloodied_bonus: float,
        critical_hp_bonus: float,
    ) -> float:
        score = 0.0

        if self._has_active_concentration(target):
            score += 4.0
        if lowest_ac_in_pool is not None and target.ac == lowest_ac_in_pool:
            score += 3.0
        if self._attack_has_advantage_against_target(target):
            score += advantage_bonus

        max_hp = max(target.hp.get("max", 0), 1)
        current_hp = min(max(target.hp.get("current", 0), 0), max_hp)
        hp_ratio = current_hp / max_hp
        if low_hp_ratio_bonus_scale > 0:
            score += (1.0 - hp_ratio) * low_hp_ratio_bonus_scale
        if low_hp_threshold_bonus > 0 and max_hp <= 20:
            score += low_hp_threshold_bonus
        if bloodied_bonus > 0 and hp_ratio <= 0.5:
            score += bloodied_bonus
        if critical_hp_bonus > 0 and hp_ratio <= 0.25:
            score += critical_hp_bonus

        if target.category == "summon":
            score -= 100.0

        return round(score, 2)

    def _build_enemy_target_priority_reason(
        self,
        target: EncounterEntity,
        *,
        lowest_ac_in_pool: int | None,
        prefer_low_ac_before_advantage: bool,
        low_hp_if_threshold: bool,
        low_hp_if_bloodied: bool,
    ) -> str:
        if self._has_active_concentration(target):
            return "目标正在维持专注，优先打断"
        if prefer_low_ac_before_advantage:
            if lowest_ac_in_pool is not None and target.ac == lowest_ac_in_pool:
                return "目标甲低，更容易打穿"
            if self._attack_has_advantage_against_target(target):
                return "对其出手占优，适合先压"
        else:
            if self._attack_has_advantage_against_target(target):
                return "对其出手占优，适合先压"
            if lowest_ac_in_pool is not None and target.ac == lowest_ac_in_pool:
                return "目标甲低，更容易打穿"

        max_hp = max(target.hp.get("max", 0), 1)
        current_hp = min(max(target.hp.get("current", 0), 0), max_hp)
        hp_ratio = current_hp / max_hp
        if (low_hp_if_threshold and max_hp <= 20) or (low_hp_if_bloodied and hp_ratio <= 0.5):
            return "目标已残，适合追击"

        return "当前压制价值最高"

    def _list_enemy_tactical_targets(
        self,
        encounter: Encounter,
        actor: EncounterEntity,
    ) -> list[EncounterEntity]:
        targets: list[EncounterEntity] = []
        for target in encounter.entities.values():
            if target.entity_id == actor.entity_id or target.side == actor.side:
                continue
            if self._is_excluded_enemy_tactical_target(target):
                continue
            targets.append(target)
        return targets

    def _is_excluded_enemy_tactical_target(self, target: EncounterEntity) -> bool:
        if target.controller != "player" or target.category != "pc":
            return False
        if bool(target.combat_flags.get("is_dead")):
            return True
        return int(target.hp.get("current", 0) or 0) == 0

    def _list_enemy_ranged_threat_sources(
        self,
        encounter: Encounter,
        actor: EncounterEntity,
    ) -> list[EncounterEntity]:
        threat_sources: list[EncounterEntity] = []
        for candidate in encounter.entities.values():
            if candidate.entity_id == actor.entity_id or candidate.side == actor.side:
                continue
            if self._is_excluded_enemy_tactical_target(candidate):
                continue
            if int(candidate.hp.get("current", 0) or 0) <= 0:
                continue
            if "unconscious" in {str(condition).lower() for condition in candidate.conditions}:
                continue
            melee_range = self._max_melee_range(candidate)
            if melee_range <= 0:
                continue
            if self._distance_feet(actor, candidate) <= melee_range:
                threat_sources.append(candidate)
        threat_sources.sort(key=lambda entity: (self._distance_feet(actor, entity), entity.entity_id))
        return threat_sources

    def _is_bloodied(self, entity: EncounterEntity) -> bool:
        maximum = max(int(entity.hp.get("max", 0) or 0), 1)
        current = min(max(int(entity.hp.get("current", 0) or 0), 0), maximum)
        return (current / maximum) <= 0.5

    def _build_enemy_ranged_penalty_label(
        self,
        *,
        threatened_in_melee: bool,
        bloodied: bool,
    ) -> str:
        if not threatened_in_melee:
            return "无"
        if bloodied:
            return "中"
        return "小"

    def _build_unified_enemy_turn_recommendation(
        self,
        *,
        enemy_tactical_brief: dict[str, Any] | None,
        enemy_ranged_tactical_brief: dict[str, Any] | None,
        enemy_hybrid_tactical_brief: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if enemy_hybrid_tactical_brief is not None:
            recommended = enemy_hybrid_tactical_brief.get("recommended_tactic")
            if isinstance(recommended, dict):
                payload = dict(recommended)
                payload["source"] = "enemy_hybrid_tactical_brief"
                return {
                    "recommended_tactic": payload,
                    "contingencies": {
                        "alternative_targets": [],
                        "reachable_options": [],
                        "fallback_options": [],
                        "alternate_modes": [
                            mode
                            for mode in enemy_hybrid_tactical_brief.get("available_modes", [])
                            if mode != enemy_hybrid_tactical_brief.get("recommended_mode")
                        ],
                    },
                }

        if enemy_ranged_tactical_brief is not None:
            recommended = enemy_ranged_tactical_brief.get("recommended_tactic")
            if isinstance(recommended, dict):
                payload = dict(recommended)
                payload["source"] = "enemy_ranged_tactical_brief"
                return {
                    "recommended_tactic": payload,
                    "contingencies": {
                        "alternative_targets": list(enemy_ranged_tactical_brief.get("candidate_targets", [])[1:]),
                        "reachable_options": [],
                        "fallback_options": list(enemy_ranged_tactical_brief.get("fallback_options", [])),
                        "alternate_modes": [],
                    },
                }

        if enemy_tactical_brief is not None:
            recommended = enemy_tactical_brief.get("recommended_tactic")
            if isinstance(recommended, dict):
                payload = dict(recommended)
                payload["source"] = "enemy_tactical_brief"
                return {
                    "recommended_tactic": payload,
                    "contingencies": {
                        "alternative_targets": list(enemy_tactical_brief.get("candidate_targets", [])[1:]),
                        "reachable_options": list(enemy_tactical_brief.get("reachable_targets", [])[1:]),
                        "fallback_options": [],
                        "alternate_modes": [],
                    },
                }

        return None

    def _build_enemy_ranged_fallback_options(
        self,
        encounter: Encounter,
        actor: EncounterEntity,
        *,
        threat_sources: list[EncounterEntity],
        targets: list[EncounterEntity],
        max_ranged_range: int,
    ) -> list[dict[str, Any]]:
        if not threat_sources:
            return []
        movement_budget = max(0, int(actor.speed.get("remaining", 0) or 0))
        if movement_budget <= 0:
            return []

        current_ally_distance = self._distance_to_nearest_ally(encounter, actor, actor.position)
        options: list[dict[str, Any]] = []
        for x in range(int(encounter.map.width)):
            for y in range(int(encounter.map.height)):
                anchor = {"x": x, "y": y}
                if anchor == actor.position:
                    continue
                try:
                    movement = validate_movement_path(
                        encounter,
                        actor.entity_id,
                        anchor,
                        count_movement=False,
                        use_dash=False,
                    )
                except ValueError:
                    continue
                feet_cost = int(movement.feet_cost)
                if feet_cost > movement_budget:
                    continue
                remaining_threats = [source for source in threat_sources if self._distance_feet_from_anchor(anchor, source) <= self._max_melee_range(source)]
                closer_to_allies = self._distance_to_nearest_ally(encounter, actor, anchor) < current_ally_distance
                keeps_future_shot = any(self._distance_feet_from_anchor(anchor, target) <= max_ranged_range for target in targets)
                breaks_all_melee_threat = not remaining_threats
                options.append(
                    {
                        "position": dict(anchor),
                        "movement_cost_feet": feet_cost,
                        "requires_disengage": True,
                        "breaks_all_melee_threat": breaks_all_melee_threat,
                        "closer_to_allies": closer_to_allies,
                        "keeps_future_shot": keeps_future_shot,
                        "safety_reason": self._build_enemy_ranged_safety_reason(
                            breaks_all_melee_threat=breaks_all_melee_threat,
                            closer_to_allies=closer_to_allies,
                            keeps_future_shot=keeps_future_shot,
                        ),
                    }
                )

        options.sort(
            key=lambda item: (
                0 if bool(item["breaks_all_melee_threat"]) else 1,
                0 if bool(item["closer_to_allies"]) else 1,
                0 if bool(item["keeps_future_shot"]) else 1,
                int(item["movement_cost_feet"]),
                int(item["position"]["x"]),
                int(item["position"]["y"]),
            )
        )
        return options[:2]

    def _distance_to_nearest_ally(
        self,
        encounter: Encounter,
        actor: EncounterEntity,
        anchor: dict[str, int],
    ) -> int:
        distances = [
            self._distance_feet_from_anchor(anchor, entity)
            for entity in encounter.entities.values()
            if entity.entity_id != actor.entity_id and entity.side == actor.side
        ]
        if not distances:
            return 9999
        return min(distances)

    def _distance_feet_from_anchor(
        self,
        anchor: dict[str, int],
        target: EncounterEntity,
    ) -> int:
        dx = abs(int(anchor["x"]) - int(target.position["x"]))
        dy = abs(int(anchor["y"]) - int(target.position["y"]))
        return max(dx, dy) * 5

    def _build_enemy_ranged_safety_reason(
        self,
        *,
        breaks_all_melee_threat: bool,
        closer_to_allies: bool,
        keeps_future_shot: bool,
    ) -> str:
        if breaks_all_melee_threat and closer_to_allies:
            return "脱离近战并靠近友军"
        if breaks_all_melee_threat:
            return "脱离近战"
        if closer_to_allies:
            return "更靠近友军"
        if keeps_future_shot:
            return "保留后续输出"
        return "降低近战压力"

    def _build_enemy_ranged_recommended_tactic(
        self,
        *,
        encounter: Encounter,
        actor: EncounterEntity,
        candidates: list[dict[str, Any]],
        threatened_in_melee: bool,
        bloodied: bool,
        fallback_options: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if threatened_in_melee and bloodied and fallback_options:
            return {
                "action": "disengage_and_fallback",
                "target_entity_id": None,
                "fallback_position": fallback_options[0]["position"],
                "reason": "已被贴身且状态不稳，先撤开再打",
                "execution_plan": [
                    self._build_use_disengage_step(
                        encounter_id=encounter.encounter_id,
                        actor_id=actor.entity_id,
                    ),
                    self._build_begin_move_step(
                        encounter_id=encounter.encounter_id,
                        entity_id=actor.entity_id,
                        target_position=fallback_options[0]["position"],
                    ),
                ],
            }
        if candidates:
            target_id = str(candidates[0]["entity_id"])
            target = encounter.entities.get(target_id)
            sequence = self._select_multiattack_sequence_for_mode(
                encounter=encounter,
                actor=actor,
                target=target,
                mode="ranged",
                prefer_high_ac=False,
            )
            if sequence is not None:
                return {
                    "action": "multiattack",
                    "target_entity_id": target_id,
                    "fallback_position": None,
                    "reason": (
                        "虽被贴身但仍可承压，先顶着压力多重射击"
                        if threatened_in_melee
                        else "未被贴身，优先用多重射击压制"
                    ),
                    "execution_plan": self._build_multiattack_sequence_execution_plan(
                        encounter=encounter,
                        actor=actor,
                        target_entity_id=target_id,
                        sequence=sequence,
                    ),
                }
            weapon = self._select_best_weapon_for_target(actor, target, kind="ranged")
            return {
                "action": "attack",
                "target_entity_id": target_id,
                "fallback_position": None,
                "reason": (
                    "虽被贴身但仍可承压，先顶着压力射击"
                    if threatened_in_melee
                    else "未被贴身，优先点杀高价值目标"
                ),
                "execution_plan": []
                if weapon is None
                else [
                    self._build_execute_attack_step(
                        encounter_id=encounter.encounter_id,
                        actor_id=actor.entity_id,
                        target_id=str(candidates[0]["entity_id"]),
                        weapon_id=str(weapon.get("weapon_id")),
                    )
                ],
            }
        if fallback_options:
            return {
                "action": "disengage_and_fallback",
                "target_entity_id": None,
                "fallback_position": fallback_options[0]["position"],
                "reason": "暂时没有好角度，先拉开重整射线",
                "execution_plan": [
                    self._build_use_disengage_step(
                        encounter_id=encounter.encounter_id,
                        actor_id=actor.entity_id,
                    ),
                    self._build_begin_move_step(
                        encounter_id=encounter.encounter_id,
                        entity_id=actor.entity_id,
                        target_position=fallback_options[0]["position"],
                    ),
                ],
            }
        return {
            "action": "hold_position",
            "target_entity_id": None,
            "fallback_position": None,
            "reason": "暂时观望，等待更好出手机会",
            "execution_plan": [],
        }

    def _build_enemy_melee_recommended_tactic(
        self,
        *,
        encounter: Encounter,
        actor: EncounterEntity,
        candidates: list[dict[str, Any]],
        reachable_targets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if candidates:
            target_id = candidates[0]["entity_id"]
            target = encounter.entities.get(str(target_id))
            sequence = self._select_multiattack_sequence_for_mode(
                encounter=encounter,
                actor=actor,
                target=target,
                mode="melee",
                prefer_high_ac=False,
            )
            if sequence is not None:
                return {
                    "action": "multiattack",
                    "target_entity_id": target_id,
                    "engage_mode": "already_in_range",
                    "movement_cost_feet": 0,
                    "opportunity_attack_risk": False,
                    "reason": "已经贴住目标，优先用多重攻击施压",
                    "execution_plan": self._build_multiattack_sequence_execution_plan(
                        encounter=encounter,
                        actor=actor,
                        target_entity_id=str(target_id),
                        sequence=sequence,
                    ),
                }
            weapon = self._select_best_weapon_for_target(actor, target, kind="melee")
            return {
                "action": "attack",
                "target_entity_id": target_id,
                "engage_mode": "already_in_range",
                "movement_cost_feet": 0,
                "opportunity_attack_risk": False,
                "reason": "已经贴住目标，直接近战施压",
                "execution_plan": []
                if weapon is None
                else [
                    self._build_execute_attack_step(
                        encounter_id=encounter.encounter_id,
                        actor_id=actor.entity_id,
                        target_id=str(target_id),
                        weapon_id=str(weapon.get("weapon_id")),
                    )
                ],
            }

        if reachable_targets:
            primary = reachable_targets[0]
            engage_mode = str(primary.get("engage_mode") or "")
            target_id = str(primary.get("entity_id"))
            target = encounter.entities.get(target_id)
            sequence = self._select_multiattack_sequence_for_mode(
                encounter=encounter,
                actor=actor,
                target=target,
                mode="melee",
                prefer_high_ac=False,
            )
            weapon = self._select_preferred_weapon_by_kind(actor, kind="melee")
            if engage_mode == "move_and_attack":
                return {
                    "action": "move_and_attack",
                    "target_entity_id": primary.get("entity_id"),
                    "engage_mode": engage_mode,
                    "movement_cost_feet": primary.get("movement_cost_feet"),
                    "opportunity_attack_risk": bool(primary.get("opportunity_attack_risk")),
                    "reason": "可以直接贴上目标，本回合就近战施压",
                    "execution_plan": []
                    if weapon is None and sequence is None
                    else [
                        self._build_begin_move_step(
                            encounter_id=encounter.encounter_id,
                            entity_id=actor.entity_id,
                            target_position=primary.get("destination_position"),
                        ),
                        *(
                            self._build_multiattack_sequence_execution_plan(
                                encounter=encounter,
                                actor=actor,
                                target_entity_id=target_id,
                                sequence=sequence,
                            )
                            if sequence is not None
                            else [
                                self._build_execute_attack_step(
                                    encounter_id=encounter.encounter_id,
                                    actor_id=actor.entity_id,
                                    target_id=target_id,
                                    weapon_id=str(weapon.get("weapon_id")),
                                )
                            ]
                        ),
                    ],
                }
            if engage_mode == "dash_to_engage":
                return {
                    "action": "dash_to_engage",
                    "target_entity_id": primary.get("entity_id"),
                    "engage_mode": engage_mode,
                    "movement_cost_feet": primary.get("movement_cost_feet"),
                    "opportunity_attack_risk": bool(primary.get("opportunity_attack_risk")),
                    "reason": "本回合够不到，先冲上去抢近战位置",
                    "execution_plan": [
                        self._build_begin_move_step(
                            encounter_id=encounter.encounter_id,
                            entity_id=actor.entity_id,
                            target_position=primary.get("destination_position"),
                            use_dash=True,
                        )
                    ],
                }
            if engage_mode == "disengage_to_engage":
                return {
                    "action": "disengage_to_engage",
                    "target_entity_id": primary.get("entity_id"),
                    "engage_mode": engage_mode,
                    "movement_cost_feet": primary.get("movement_cost_feet"),
                    "opportunity_attack_risk": False,
                    "reason": "直接转压会吃借机，先脱离再换目标",
                    "execution_plan": [
                        self._build_use_disengage_step(
                            encounter_id=encounter.encounter_id,
                            actor_id=actor.entity_id,
                        ),
                        self._build_begin_move_step(
                            encounter_id=encounter.encounter_id,
                            entity_id=actor.entity_id,
                            target_position=primary.get("destination_position"),
                        ),
                    ],
                }

        return {
            "action": "hold_position",
            "target_entity_id": None,
            "engage_mode": None,
            "movement_cost_feet": None,
            "opportunity_attack_risk": False,
            "reason": "暂时压不上去，先维持位置等待机会",
            "execution_plan": [],
        }

    def _build_execute_attack_step(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        target_id: str,
        weapon_id: str,
    ) -> dict[str, Any]:
        return {
            "command": "execute_attack",
            "args": {
                "encounter_id": encounter_id,
                "actor_id": actor_id,
                "target_id": target_id,
                "weapon_id": weapon_id,
            },
        }

    def _build_begin_move_step(
        self,
        *,
        encounter_id: str,
        entity_id: str,
        target_position: Any,
        use_dash: bool = False,
    ) -> dict[str, Any]:
        position = target_position if isinstance(target_position, dict) else {"x": 0, "y": 0}
        return {
            "command": "begin_move_encounter_entity",
            "args": {
                "encounter_id": encounter_id,
                "entity_id": entity_id,
                "target_position": {
                    "x": int(position.get("x", 0) or 0),
                    "y": int(position.get("y", 0) or 0),
                },
                **({"use_dash": True} if use_dash else {}),
            },
        }

    def _build_use_disengage_step(
        self,
        *,
        encounter_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        return {
            "command": "use_disengage",
            "args": {
                "encounter_id": encounter_id,
                "actor_id": actor_id,
            },
        }

    def _build_special_action_execution_step(
        self,
        *,
        encounter: Encounter,
        actor: EncounterEntity,
        action_id: str,
        target_entity_id: str,
    ) -> dict[str, Any]:
        hint = self._build_action_execution_hint(
            encounter=encounter,
            entity=actor,
            action_id=action_id,
            bucket="actions_metadata",
        ) or {}
        command = hint.get("command")
        if isinstance(command, str) and command:
            args = dict(hint.get("preset_args", {})) if isinstance(hint.get("preset_args"), dict) else {}
            if "target_id" in hint.get("required_args", []):
                args["target_id"] = target_entity_id
            return {"command": command, "args": args}
        return {
            "command": None,
            "mode": hint.get("mode"),
            "action_id": action_id,
            "target_id": target_entity_id,
            "note": hint.get("note"),
        }

    def _list_weapons_by_kind(
        self,
        entity: EncounterEntity,
        *,
        kind: str,
    ) -> list[dict[str, Any]]:
        normalized_kind = kind.strip().lower()
        weapons: list[dict[str, Any]] = []
        for weapon in entity.weapons:
            if not isinstance(weapon, dict):
                continue
            if str(weapon.get("kind", "")).strip().lower() != normalized_kind:
                continue
            weapons.append(weapon)
        return weapons

    def _list_hybrid_save_actions(
        self,
        entity: EncounterEntity,
    ) -> list[dict[str, Any]]:
        source_ref = entity.source_ref if isinstance(entity.source_ref, dict) else {}
        raw_items = source_ref.get("actions_metadata")
        if not isinstance(raw_items, list):
            return []

        items: list[dict[str, Any]] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            action_id = str(raw_item.get("action_id") or "").strip()
            save_ability = str(raw_item.get("save_ability") or "").strip().lower()
            range_feet = raw_item.get("range_feet")
            if not action_id or not save_ability or not isinstance(range_feet, int) or range_feet <= 0:
                continue
            items.append(
                {
                    "action_id": action_id,
                    "range_feet": range_feet,
                    "save_ability": save_ability,
                }
            )
        return items

    def _select_hybrid_save_action_target(
        self,
        encounter: Encounter,
        actor: EncounterEntity,
    ) -> dict[str, Any] | None:
        save_actions = self._list_hybrid_save_actions(actor)
        if not save_actions:
            return None

        targets = self._list_enemy_tactical_targets(encounter, actor)
        best_choice: dict[str, Any] | None = None
        for action in save_actions:
            in_range_targets = [
                target
                for target in targets
                if self._distance_feet(actor, target) <= int(action["range_feet"])
            ]
            lowest_ac = min((target.ac for target in in_range_targets), default=None)
            for target in in_range_targets:
                score = self._score_enemy_tactical_target(target, lowest_ac)
                choice = {
                    "action_id": action["action_id"],
                    "target_entity_id": target.entity_id,
                    "score": score,
                    "_distance_feet": self._distance_feet(actor, target),
                }
                if best_choice is None or self._hybrid_choice_sort_key(choice) < self._hybrid_choice_sort_key(best_choice):
                    best_choice = choice
        return best_choice

    def _hybrid_choice_sort_key(
        self,
        choice: dict[str, Any],
    ) -> tuple[float, int, str, str]:
        return (
            -float(choice["score"]),
            int(choice["_distance_feet"]),
            str(choice["target_entity_id"]),
            str(choice["action_id"]),
        )

    def _select_best_weapon_for_target(
        self,
        actor: EncounterEntity,
        target: EncounterEntity | None,
        *,
        kind: str,
    ) -> dict[str, Any] | None:
        if target is None:
            return None
        candidates: list[dict[str, Any]] = []
        for weapon in self._list_weapons_by_kind(actor, kind=kind):
            if self._distance_feet(actor, target) > self._resolve_weapon_max_range(weapon):
                continue
            candidates.append(weapon)
        if not candidates:
            return None
        candidates.sort(
            key=lambda weapon: (
                -int(weapon.get("attack_bonus", 0) or 0),
                str(weapon.get("weapon_id") or ""),
            )
        )
        return candidates[0]

    def _select_preferred_weapon_by_kind(
        self,
        actor: EncounterEntity,
        *,
        kind: str,
    ) -> dict[str, Any] | None:
        candidates = list(self._list_weapons_by_kind(actor, kind=kind))
        if not candidates:
            return None
        candidates.sort(
            key=lambda weapon: (
                -int(weapon.get("attack_bonus", 0) or 0),
                -self._resolve_weapon_max_range(weapon),
                str(weapon.get("weapon_id") or ""),
            )
        )
        return candidates[0]

    def _resolve_weapon_max_range(
        self,
        weapon: dict[str, Any],
    ) -> int:
        weapon_range = weapon.get("range", {})
        if not isinstance(weapon_range, dict):
            return 0
        normal_range = int(weapon_range.get("normal", 0) or 0)
        long_range = int(weapon_range.get("long", 0) or 0)
        return max(normal_range, long_range)

    def _estimate_weapon_hit_chance(
        self,
        weapon: dict[str, Any] | None,
        target: EncounterEntity | None,
    ) -> float:
        if weapon is None or target is None:
            return 0.0
        attack_bonus = int(weapon.get("attack_bonus", 0) or 0)
        required_roll = int(target.ac) - attack_bonus
        success_count = 21 - required_roll
        success_count = max(1, min(19, success_count))
        return round(success_count / 20.0, 2)

    def _has_active_concentration(self, target: EncounterEntity) -> bool:
        concentration_state = target.combat_flags.get("concentration")
        if isinstance(concentration_state, dict) and bool(concentration_state.get("active")):
            return True
        return any(
            isinstance(effect, dict) and effect.get("effect_type") == "concentration"
            for effect in target.turn_effects
        )

    def _attack_has_advantage_against_target(self, target: EncounterEntity) -> bool:
        target_conditions = {str(condition).lower() for condition in target.conditions}
        return "restrained" in target_conditions or "paralyzed" in target_conditions

    def _max_melee_range(self, entity: EncounterEntity) -> int:
        melee_ranges: list[int] = []
        for weapon in entity.weapons:
            kind = str(weapon.get("kind", "")).lower()
            weapon_range = weapon.get("range", {})
            normal_range = weapon_range.get("normal", 0)
            long_range = weapon_range.get("long", normal_range)
            if not isinstance(normal_range, int) or normal_range <= 0:
                continue
            # Conservative fallback: only accept unknown kind with very short
            # normal/long range to avoid classifying ranged weapons as melee.
            kind_missing = kind == ""
            if kind == "melee" or (kind_missing and isinstance(long_range, int) and long_range <= 10 and normal_range <= 10):
                melee_ranges.append(normal_range)
        return max(melee_ranges, default=0)

    def _max_ranged_range(self, entity: EncounterEntity) -> int:
        ranges: list[int] = []
        for weapon in entity.weapons:
            weapon_range = weapon.get("range", {})
            normal_range = weapon_range.get("normal", 0)
            long_range = weapon_range.get("long", 0)
            if normal_range and normal_range > 10:
                ranges.append(max(normal_range, long_range))
        for spell in entity.spells:
            range_feet = spell.get("range_feet", 0)
            if isinstance(range_feet, int) and range_feet > 0:
                ranges.append(range_feet)
        return max(ranges, default=0)

    def _distance_feet(self, source: EncounterEntity, target: EncounterEntity) -> int:
        dx = abs(source.position["x"] - target.position["x"])
        dy = abs(source.position["y"] - target.position["y"])
        return max(dx, dy) * 5

    def _format_distance_from_current(
        self,
        entity: EncounterEntity,
        current_entity: EncounterEntity | None,
    ) -> str | None:
        if current_entity is None or entity.entity_id == current_entity.entity_id:
            return None
        return f"{self._distance_feet(current_entity, entity)} 尺"

    def _format_hp(self, entity: EncounterEntity) -> str:
        return f"{entity.hp['current']} / {entity.hp['max']} HP"

    def _format_hp_status(self, entity: EncounterEntity) -> str:
        current_hp = entity.hp["current"]
        max_hp = entity.hp["max"]
        percent = 0 if max_hp == 0 else round((current_hp / max_hp) * 100)
        if current_hp <= 0:
            status = "DOWN"
        elif percent >= 75:
            status = "HEALTHY"
        elif percent >= 35:
            status = "WOUNDED"
        else:
            status = "BLOODIED"
        return f"{current_hp}/{max_hp} HP ({percent}%) [{HP_STATUS_MAP.get(status, status)}]"

    def _format_position(self, entity: EncounterEntity) -> str:
        return f"({entity.position['x']}, {entity.position['y']})"

    def _format_conditions(self, encounter: Encounter, entity: EncounterEntity) -> str | list[str]:
        effect_labels = self._build_entity_ongoing_effects(encounter, entity)
        if not entity.conditions and not effect_labels:
            return "无状态"
        localized_conditions = [self._localize_condition_label(encounter, condition) for condition in entity.conditions]
        if not effect_labels:
            return ", ".join(localized_conditions)
        return self._dedupe_preserve_order([*localized_conditions, *effect_labels])

    def _build_resources_view(self, encounter: Encounter, entity: EncounterEntity) -> dict[str, Any]:
        spell_slots = self._build_spell_slots_resource_view(entity)
        pact_magic_slots = self._build_pact_magic_slots_resource_view(entity)
        feature_uses = self._build_feature_uses_resource_view(entity)
        class_features = self._build_class_feature_resource_view(encounter, entity)
        return {
            "summary": self._format_resources_summary(entity),
            "spell_slots": spell_slots,
            "pact_magic_slots": pact_magic_slots,
            "feature_uses": feature_uses,
            "class_features": class_features,
        }

    def _format_resources_summary(self, entity: EncounterEntity) -> str:
        ensure_spell_slots_runtime(entity)
        parts: list[str] = []

        spell_slots = entity.resources.get("spell_slots", {})
        if spell_slots:
            slot_parts = []
            for level, slot_data in sorted(spell_slots.items(), key=lambda item: item[0]):
                if isinstance(slot_data, dict) and "remaining" in slot_data and "max" in slot_data:
                    slot_parts.append(f"{self._format_spell_level_label(level)} {slot_data['remaining']}/{slot_data['max']}")
            if slot_parts:
                parts.append("法术位：" + ", ".join(slot_parts))

        pact_magic_slots = entity.resources.get("pact_magic_slots", {})
        if isinstance(pact_magic_slots, dict):
            slot_level = pact_magic_slots.get("slot_level")
            remaining = pact_magic_slots.get("remaining")
            maximum = pact_magic_slots.get("max")
            if isinstance(slot_level, int) and isinstance(remaining, int) and isinstance(maximum, int):
                parts.append(f"契约魔法：{self._format_spell_level_label(slot_level)} {remaining}/{maximum}")

        feature_uses = entity.resources.get("feature_uses", {})
        if feature_uses:
            feature_parts = []
            for name, use_data in feature_uses.items():
                if isinstance(use_data, dict) and "remaining" in use_data and "max" in use_data:
                    feature_parts.append(f"{name}: {use_data['remaining']}/{use_data['max']}")
            if feature_parts:
                parts.append(", ".join(feature_parts))

        if not parts:
            return "无追踪资源"
        return " | ".join(parts)

    def _build_spell_slots_resource_view(self, entity: EncounterEntity) -> dict[str, dict[str, int]]:
        ensure_spell_slots_runtime(entity)
        spell_slots = entity.resources.get("spell_slots", {})
        if not isinstance(spell_slots, dict):
            return {}

        projected: dict[str, dict[str, int]] = {}
        for level, slot_data in spell_slots.items():
            if not isinstance(slot_data, dict):
                continue
            remaining = slot_data.get("remaining")
            maximum = slot_data.get("max")
            if not isinstance(remaining, int) or not isinstance(maximum, int):
                continue
            projected[str(level)] = {
                "remaining": remaining,
                "max": maximum,
            }
        return projected

    def _build_pact_magic_slots_resource_view(self, entity: EncounterEntity) -> dict[str, int]:
        ensure_spell_slots_runtime(entity)
        pact_magic_slots = entity.resources.get("pact_magic_slots", {})
        if not isinstance(pact_magic_slots, dict):
            return {}
        slot_level = pact_magic_slots.get("slot_level")
        remaining = pact_magic_slots.get("remaining")
        maximum = pact_magic_slots.get("max")
        if not isinstance(slot_level, int) or not isinstance(remaining, int) or not isinstance(maximum, int):
            return {}
        return {
            "slot_level": slot_level,
            "remaining": remaining,
            "max": maximum,
        }

    def _build_feature_uses_resource_view(self, entity: EncounterEntity) -> dict[str, dict[str, int]]:
        feature_uses = entity.resources.get("feature_uses", {})
        if not isinstance(feature_uses, dict):
            return {}

        projected: dict[str, dict[str, int]] = {}
        for name, use_data in feature_uses.items():
            if not isinstance(use_data, dict):
                continue
            remaining = use_data.get("remaining")
            maximum = use_data.get("max")
            if not isinstance(remaining, int) or not isinstance(maximum, int):
                continue
            projected[str(name)] = {
                "remaining": remaining,
                "max": maximum,
            }
        return projected

    def _build_class_feature_resource_view(self, encounter: Encounter, entity: EncounterEntity) -> dict[str, Any]:
        class_features = entity.class_features if isinstance(entity.class_features, dict) else {}
        projected: dict[str, Any] = {}

        for class_id, summary in MARTIAL_CLASS_SUMMARIES.items():
            bucket = class_features.get(class_id)
            if not isinstance(bucket, dict):
                continue
            if class_id == "monk":
                bucket = ensure_monk_runtime(entity)
            elif class_id == "rogue":
                bucket = ensure_rogue_runtime(entity)
            elif class_id == "paladin":
                bucket = ensure_paladin_runtime(entity)
            elif class_id == "barbarian":
                bucket = ensure_barbarian_runtime(entity)
            elif class_id == "ranger":
                bucket = ensure_ranger_runtime(entity)
            elif class_id == "cleric":
                bucket = ensure_cleric_runtime(entity)
            elif class_id == "druid":
                bucket = ensure_druid_runtime(entity)
            elif class_id == "sorcerer":
                bucket = ensure_sorcerer_runtime(entity)
            elif class_id == "warlock":
                bucket = ensure_warlock_runtime(entity)
            elif class_id == "bard":
                bucket = ensure_bard_runtime(entity)
            elif class_id == "wizard":
                bucket = ensure_wizard_runtime(entity)
            projected[class_id] = {
                field: bucket[field]
                for field in summary["fields"]
                if field in bucket
            }
            if class_id == "warlock":
                gaze = bucket.get("gaze_of_two_minds")
                if isinstance(gaze, dict):
                    projected[class_id]["gaze_of_two_minds"] = dict(gaze)
                    origin = resolve_gaze_of_two_minds_origin(encounter, entity)
                    projected[class_id]["gaze_of_two_minds"]["can_cast_via_link"] = bool(origin.get("can_cast_via_link"))
                    projected[class_id]["gaze_of_two_minds"]["distance_to_link_feet"] = origin.get("distance_to_link_feet")
            if class_id == "rogue" and int(bucket.get("level", 0) or 0) >= 2:
                projected[class_id]["cunning_action"] = {
                    "bonus_dash": True,
                    "bonus_disengage": True,
                    "bonus_hide": True,
                }
            available_features = self._resolve_available_feature_keys(
                summary.get("available_features", []),
                level=int(bucket.get("level", 0) or 0),
            )
            if class_id == "paladin":
                level = int(bucket.get("level", 0) or 0)
                available_features.append("spellcasting")
                if level >= 5:
                    available_features.append("faithful_steed")
                if level >= 3:
                    available_features.append("channel_divinity")
                if level >= 9:
                    available_features.append("abjure_foes")
                if level >= 10:
                    available_features.append("aura_of_courage")
                if level >= 11:
                    available_features.append("radiant_strikes")
                if level >= 14:
                    available_features.append("restoring_touch")
            if class_id == "barbarian":
                level = int(bucket.get("level", 0) or 0)
                if level >= 9:
                    available_features.append("brutal_strike")
                if level >= 11:
                    available_features.append("relentless_rage")
                if level >= 15:
                    available_features.append("persistent_rage")
                if level >= 18:
                    available_features.append("indomitable_might")
            if class_id == "ranger":
                level = int(bucket.get("level", 0) or 0)
                available_features.append("spellcasting")
                if level >= 2:
                    available_features.extend(["deft_explorer", "fighting_style"])
                if level >= 5:
                    available_features.append("extra_attack")
                if level >= 6:
                    available_features.append("roving")
                if level >= 10:
                    available_features.append("tireless")
                if level >= 13:
                    available_features.append("relentless_hunter")
                if level >= 14:
                    available_features.append("natures_veil")
                if level >= 17:
                    available_features.append("precise_hunter")
                if level >= 18:
                    available_features.append("feral_senses")
                if level >= 20:
                    available_features.append("foe_slayer")
            if class_id == "cleric":
                level = int(bucket.get("level", 0) or 0)
                if level >= 2:
                    available_features.extend(["channel_divinity", "divine_spark", "turn_undead"])
                if level >= 5:
                    available_features.append("sear_undead")
                if level >= 7:
                    available_features.append("blessed_strikes")
                if level >= 10:
                    available_features.append("divine_intervention")
                if level >= 14:
                    available_features.append("improved_blessed_strikes")
            if class_id == "druid":
                level = int(bucket.get("level", 0) or 0)
                if level >= 1:
                    available_features.append("druidic")
                if level >= 2:
                    available_features.extend(["wild_shape", "wild_companion"])
                if level >= 5:
                    available_features.append("wild_resurgence")
                if level >= 7:
                    available_features.append("elemental_fury")
                if level >= 18:
                    available_features.append("beast_spells")
                if level >= 20:
                    available_features.append("archdruid")
            if class_id == "bard":
                level = int(bucket.get("level", 0) or 0)
                if level >= 2:
                    available_features.extend(["expertise", "jack_of_all_trades"])
                if level >= 5:
                    available_features.append("font_of_inspiration")
                if level >= 7:
                    available_features.append("countercharm")
                if level >= 10:
                    available_features.append("magical_secrets")
                if level >= 18:
                    available_features.append("superior_inspiration")
                if level >= 20:
                    available_features.append("words_of_creation")
            if class_id == "warlock":
                level = int(bucket.get("level", 0) or 0)
                if isinstance(bucket.get("armor_of_shadows"), dict) and bucket["armor_of_shadows"].get("enabled"):
                    available_features.append("armor_of_shadows")
                if isinstance(bucket.get("fiendish_vigor"), dict) and bucket["fiendish_vigor"].get("enabled"):
                    available_features.append("fiendish_vigor")
                if isinstance(bucket.get("eldritch_mind"), dict) and bucket["eldritch_mind"].get("enabled"):
                    available_features.append("eldritch_mind")
                if isinstance(bucket.get("devils_sight"), dict) and bucket["devils_sight"].get("enabled"):
                    available_features.append("devils_sight")
                if isinstance(bucket.get("pact_of_the_blade"), dict) and bucket["pact_of_the_blade"].get("enabled"):
                    available_features.append("pact_of_the_blade")
                if isinstance(bucket.get("pact_of_the_chain"), dict) and bucket["pact_of_the_chain"].get("enabled"):
                    available_features.append("pact_of_the_chain")
                if isinstance(bucket.get("gaze_of_two_minds"), dict) and bucket["gaze_of_two_minds"].get("enabled"):
                    available_features.append("gaze_of_two_minds")
                if isinstance(bucket.get("eldritch_smite"), dict) and bucket["eldritch_smite"].get("enabled"):
                    available_features.append("eldritch_smite")
                if isinstance(bucket.get("lifedrinker"), dict) and bucket["lifedrinker"].get("enabled"):
                    available_features.append("lifedrinker")
                if level >= 2:
                    available_features.append("magical_cunning")
                if level >= 9:
                    available_features.append("contact_patron")
                if level >= 11:
                    available_features.append("mystic_arcanum")
                if level >= 20:
                    available_features.append("eldritch_master")
            if class_id == "sorcerer":
                level = int(bucket.get("level", 0) or 0)
                if level >= 2:
                    available_features.append("font_of_magic")
                if level >= 5:
                    available_features.append("sorcerous_restoration")
                if level >= 7:
                    available_features.append("sorcery_incarnate")
            projected[class_id]["available_features_zh"] = self._localize_available_feature_keys(
                class_id=class_id,
                feature_keys=available_features,
            )

        fighter = class_features.get("fighter")
        if isinstance(fighter, dict):
            fighter_view = dict(ensure_fighter_runtime(entity))
            fighter_view.pop("weapon_proficiencies", None)
            fighter_view.pop("armor_training", None)
            level = int(fighter_view.get("level", fighter_view.get("fighter_level", 0)) or 0)
            fighter_available_features = ["weapon_mastery", "second_wind"]
            if level >= 2:
                fighter_available_features.extend(["action_surge", "tactical_mind", "tactical_shift"])
            if level >= 5:
                fighter_available_features.append("extra_attack")
            if level >= 9:
                fighter_available_features.extend(["indomitable", "tactical_master"])
            if level >= 13:
                fighter_available_features.append("studied_attacks")
            fighter_view["available_features_zh"] = self._localize_available_feature_keys(
                class_id="fighter",
                feature_keys=fighter_available_features,
            )
            if has_fighting_style(entity, "blind_fighting"):
                fighter_view["blindsight_feet"] = 10
            projected["fighter"] = fighter_view

        return projected

    def _resolve_available_feature_keys(self, entries: Any, *, level: int) -> list[str]:
        if not isinstance(entries, list):
            return []

        resolved: list[str] = []
        for entry in entries:
            if isinstance(entry, str):
                feature_key = entry.strip()
                if feature_key:
                    resolved.append(feature_key)
                continue
            if not isinstance(entry, dict):
                continue
            feature_key = str(entry.get("key") or "").strip()
            if not feature_key:
                continue
            level_required = entry.get("level_required", 0)
            if isinstance(level_required, bool):
                continue
            if isinstance(level_required, int) and level < level_required:
                continue
            resolved.append(feature_key)
        return resolved

    def _localize_available_feature_keys(self, *, class_id: str, feature_keys: list[str]) -> list[str]:
        localized: list[str] = []
        for feature_key in feature_keys:
            label = self._localize_available_feature_key(class_id=class_id, feature_key=feature_key)
            localized.append(label)
        return localized

    def _localize_available_feature_key(self, *, class_id: str, feature_key: str) -> str:
        definition = self.class_feature_definition_repository.get(f"{class_id}.{feature_key}")
        if isinstance(definition, dict):
            name_zh = definition.get("name_zh")
            if isinstance(name_zh, str) and name_zh.strip():
                return name_zh.strip()
        override = AVAILABLE_FEATURE_LABELS_ZH.get(class_id, {}).get(feature_key)
        if isinstance(override, str) and override.strip():
            return override.strip()
        return feature_key

    def _format_death_saves(self, entity: EncounterEntity) -> str:
        combat_flags = entity.combat_flags or {}
        death_saves = combat_flags.get("death_saves")
        if not isinstance(death_saves, dict):
            return "0 成功 / 0 失败"
        successes = death_saves.get("successes", 0)
        failures = death_saves.get("failures", 0)
        if not isinstance(successes, int):
            successes = 0
        if not isinstance(failures, int):
            failures = 0
        return f"{successes} 成功 / {failures} 失败"

    def _format_weapon_bonus(self, weapon: dict[str, Any]) -> str | None:
        attack_bonus = weapon.get("attack_bonus")
        damage_bonus = weapon.get("damage_bonus")
        if attack_bonus is None and damage_bonus is None:
            return None
        parts = []
        if attack_bonus is not None:
            parts.append(f"+{attack_bonus} 命中")
        if damage_bonus is not None:
            parts.append(f"+{damage_bonus} 伤害")
        return ", ".join(parts)

    def _extract_level(self, entity: EncounterEntity) -> int | None:
        source_ref = entity.source_ref
        level = source_ref.get("level")
        return level if isinstance(level, int) else None

    def _extract_description(self, entity: EncounterEntity) -> str | None:
        description = entity.source_ref.get("description")
        return description if isinstance(description, str) else None

    def _calculate_spell_save_dc(self, entity: EncounterEntity) -> int | None:
        spellcasting_ability = entity.source_ref.get("spellcasting_ability")
        if spellcasting_ability is None:
            return None

        ability_mod = entity.ability_mods.get(spellcasting_ability)
        if ability_mod is None:
            return None
        return 8 + entity.proficiency_bonus + ability_mod

    def _is_active_spell_instance(self, instance: dict[str, Any]) -> bool:
        lifecycle = instance.get("lifecycle", {})
        return lifecycle.get("status") == "active"

    def _format_spell_source_label(self, instance: dict[str, Any]) -> str:
        caster_name = instance.get("caster_name") or "未知施法者"
        spell_name = self._localize_display_name(instance.get("spell_name") or instance.get("spell_id") or "未知法术")
        return f"来自{caster_name}的{spell_name}"

    def _dedupe_preserve_order(self, values: list[str]) -> list[str]:
        ordered_values: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            ordered_values.append(value)
        return ordered_values

    def _entity_name_or_fallback(self, encounter: Encounter, entity_id: Any, fallback: str) -> str:
        if isinstance(entity_id, str):
            entity = encounter.entities.get(entity_id)
            if entity is not None:
                return entity.name
        return fallback

    def _extract_previous_target_id(self, instance: dict[str, Any]) -> str | None:
        targets = instance.get("targets")
        if not isinstance(targets, list) or not targets:
            return None
        first_target = targets[0]
        if not isinstance(first_target, dict):
            return None
        entity_id = first_target.get("entity_id")
        return entity_id if isinstance(entity_id, str) else None

    def _normalize_position(self, value: Any) -> dict[str, int] | None:
        if not isinstance(value, dict):
            return None
        x = value.get("x")
        y = value.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            return None
        return {"x": x, "y": y}

    def _normalize_path(self, value: Any) -> list[dict[str, int]]:
        if not isinstance(value, list):
            return []
        normalized: list[dict[str, int]] = []
        for item in value:
            position = self._normalize_position(item)
            if position is not None:
                normalized.append(position)
        return normalized

    def _format_forced_movement_summary(
        self,
        *,
        reason: str,
        target_name: str,
        moved_feet: int,
        final_position: dict[str, int] | None,
        blocked: bool,
        block_reason: Any,
    ) -> str:
        if reason == "weapon_mastery_push":
            if moved_feet <= 0:
                return f"{target_name}尝试被推离，但被{self._format_block_reason(block_reason)}阻挡，位置未改变。"
            destination = self._format_compact_position(final_position)
            if blocked:
                return f"{target_name}被推离 {moved_feet} 尺，移动到 {destination}，随后被{self._format_block_reason(block_reason)}阻挡。"
            return f"{target_name}被推离 {moved_feet} 尺，移动到 {destination}。"
        destination = self._format_compact_position(final_position)
        return f"{target_name}发生了强制位移，最终到达 {destination}。"

    def _format_compact_position(self, position: dict[str, int] | None) -> str:
        if position is None:
            return "(?,?)"
        return f"({position['x']},{position['y']})"

    def _format_block_reason(self, block_reason: Any) -> str:
        mapping = {
            "wall": "墙壁",
            "out_of_bounds": "边界",
            "occupied_tile": "占位",
        }
        return mapping.get(str(block_reason or ""), "障碍")

    def _format_turn_effect_summary(
        self,
        *,
        name: str,
        trigger: str,
        source_name: str,
        target_name: str,
        save: Any,
        trigger_damage_resolution: Any,
        success_damage_resolution: Any,
        failure_damage_resolution: Any,
        condition_updates: Any,
        effect_removed: bool,
    ) -> str:
        trigger_label = {
            "start_of_turn": "回合开始",
            "end_of_turn": "回合结束",
        }.get(trigger, trigger or "触发时")

        parts = [f"{trigger_label}，{source_name}的{name}对{target_name}结算。"]

        save_text = self._format_turn_effect_save_summary(save)
        if save_text is not None:
            parts.append(save_text)

        damage_texts = self._collect_turn_effect_damage_summaries(
            trigger_damage_resolution=trigger_damage_resolution,
            success_damage_resolution=success_damage_resolution,
            failure_damage_resolution=failure_damage_resolution,
        )
        parts.extend(damage_texts)

        condition_text = self._format_turn_effect_condition_summary(condition_updates)
        if condition_text is not None:
            parts.append(condition_text)

        if effect_removed:
            parts.append("该持续效果已移除。")

        return " ".join(parts)

    def _format_turn_effect_save_summary(self, save: Any) -> str | None:
        if not isinstance(save, dict):
            return None
        ability = str(save.get("ability") or "").upper()
        dc = save.get("dc")
        total = save.get("total")
        success = save.get("success")
        if success is True:
            result = "成功"
        elif success is False:
            result = "失败"
        else:
            result = "未知"
        details: list[str] = []
        if ability:
            details.append(f"{ability} 豁免")
        if isinstance(dc, int):
            details.append(f"DC {dc}")
        if isinstance(total, int):
            details.append(f"结果 {total}")
        if not details:
            return f"豁免{result}。"
        return f"{'，'.join(details)}，{result}。"

    def _collect_turn_effect_damage_summaries(
        self,
        *,
        trigger_damage_resolution: Any,
        success_damage_resolution: Any,
        failure_damage_resolution: Any,
    ) -> list[str]:
        items: list[str] = []
        trigger_text = self._format_damage_resolution_summary(trigger_damage_resolution)
        if trigger_text is not None:
            items.append(f"触发伤害：{trigger_text}")
        success_text = self._format_damage_resolution_summary(success_damage_resolution)
        if success_text is not None:
            items.append(f"豁免成功后：{success_text}")
        failure_text = self._format_damage_resolution_summary(failure_damage_resolution)
        if failure_text is not None:
            items.append(f"豁免失败后：{failure_text}")
        return items

    def _format_damage_resolution_summary(self, resolution: Any) -> str | None:
        if not isinstance(resolution, dict):
            return None
        total_damage = resolution.get("total_damage")
        applied_parts = resolution.get("applied_parts")
        if not isinstance(total_damage, int):
            return None
        if not isinstance(applied_parts, list) or not applied_parts:
            return f"造成 {total_damage} 点伤害。"
        parts: list[str] = []
        for part in applied_parts:
            if not isinstance(part, dict):
                continue
            damage_type = str(part.get("type") or "未知")
            final_damage = part.get("final_damage")
            if isinstance(final_damage, int):
                parts.append(f"{final_damage} 点{self._localize_damage_type(damage_type)}")
        if not parts:
            return f"造成 {total_damage} 点伤害。"
        return f"造成 {total_damage} 点伤害（{'，'.join(parts)}）。"

    def _format_turn_effect_condition_summary(self, condition_updates: Any) -> str | None:
        if not isinstance(condition_updates, list) or not condition_updates:
            return None
        applied: list[str] = []
        removed: list[str] = []
        for item in condition_updates:
            if not isinstance(item, dict):
                continue
            if not bool(item.get("changed")):
                continue
            condition = item.get("condition")
            if not isinstance(condition, str):
                continue
            localized_condition = CONDITION_NAME_MAP.get(condition, condition)
            operation = item.get("operation")
            if operation == "apply":
                applied.append(localized_condition)
            elif operation == "remove":
                removed.append(localized_condition)

        parts: list[str] = []
        if applied:
            parts.append(f"附加状态：{'、'.join(applied)}。")
        if removed:
            parts.append(f"移除状态：{'、'.join(removed)}。")
        if not parts:
            return None
        return " ".join(parts)

    def _list_events_for_encounter(self, encounter_id: str) -> list[Any]:
        if self.event_repository is not None:
            return self.event_repository.list_by_encounter(encounter_id)
        event_repository = EventRepository()
        try:
            return event_repository.list_by_encounter(encounter_id)
        finally:
            event_repository.close()

    def _localize_display_name(self, value: Any) -> str:
        if not isinstance(value, str):
            return str(value)
        localized = DISPLAY_NAME_MAP.get(value)
        if localized is not None:
            return localized
        for english, chinese in DISPLAY_NAME_MAP.items():
            value = value.replace(english, chinese)
        return value

    def _localize_damage_type(self, value: Any) -> str:
        if not isinstance(value, str):
            return "未知"
        return DAMAGE_TYPE_MAP.get(value.lower(), value)

    def _localize_check_key(self, value: Any) -> str:
        if not isinstance(value, str):
            return "未知检定"
        return CHECK_KEY_MAP.get(value.lower(), value)

    def _localize_condition_label(self, encounter: Encounter, value: Any) -> str:
        if not isinstance(value, str):
            return str(value)
        if value.startswith("grappled:"):
            grappler_id = value.split(":", 1)[1]
            grappler_name = self._entity_name_or_fallback(encounter, grappler_id, grappler_id)
            return f"被{grappler_name}擒抱"
        if ":" in value:
            base, suffix = value.split(":", 1)
            localized_base = CONDITION_NAME_MAP.get(base, base)
            return f"{localized_base}:{suffix}"
        return CONDITION_NAME_MAP.get(value, value)

    def _format_spell_level_label(self, level: Any) -> str:
        if isinstance(level, str) and level.isdigit():
            return f"{int(level)}环"
        if isinstance(level, int):
            return f"{level}环"
        return str(level)
