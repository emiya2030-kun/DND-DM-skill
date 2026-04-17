ABILITY_ALIASES = {
    "str": "str",
    "strength": "str",
    "力量": "str",
    "dex": "dex",
    "dexterity": "dex",
    "敏捷": "dex",
    "con": "con",
    "constitution": "con",
    "体质": "con",
    "int": "int",
    "intelligence": "int",
    "智力": "int",
    "wis": "wis",
    "wisdom": "wis",
    "感知": "wis",
    "cha": "cha",
    "charisma": "cha",
    "魅力": "cha",
}

SKILL_ALIASES = {
    "athletics": "athletics",
    "运动": "athletics",
    "acrobatics": "acrobatics",
    "特技": "acrobatics",
    "animal handling": "animal_handling",
    "animal_handling": "animal_handling",
    "驯兽": "animal_handling",
    "arcana": "arcana",
    "奥秘": "arcana",
    "deception": "deception",
    "欺瞒": "deception",
    "history": "history",
    "历史": "history",
    "insight": "insight",
    "洞悉": "insight",
    "intimidation": "intimidation",
    "威吓": "intimidation",
    "investigation": "investigation",
    "调查": "investigation",
    "medicine": "medicine",
    "医药": "medicine",
    "nature": "nature",
    "自然": "nature",
    "perception": "perception",
    "察觉": "perception",
    "performance": "performance",
    "表演": "performance",
    "persuasion": "persuasion",
    "游说": "persuasion",
    "religion": "religion",
    "宗教": "religion",
    "sleight of hand": "sleight_of_hand",
    "sleight_of_hand": "sleight_of_hand",
    "巧手": "sleight_of_hand",
    "stealth": "stealth",
    "潜行": "stealth",
    "隐匿": "stealth",
    "survival": "survival",
    "求生": "survival",
}


def normalize_check_name(check_type: str, raw_check: str) -> str:
    normalized = raw_check.strip().lower()
    if check_type == "ability":
        result = ABILITY_ALIASES.get(normalized)
        if result is None:
            raise ValueError("unknown_ability_check")
        return result
    if check_type == "skill":
        result = SKILL_ALIASES.get(normalized)
        if result is None:
            raise ValueError("unknown_skill_check")
        return result
    raise ValueError("check_type must be 'ability' or 'skill'")
