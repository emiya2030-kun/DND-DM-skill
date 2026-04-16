#!/usr/bin/env python3
"""
D&D 5e 战斗状态管理器
用于追踪战斗中所有单位的位置、HP、状态
每次战斗必须使用此系统！

## AC计算规则（权威源）
AC以本系统的equipment字段计算为准，NPC/PC档案中的AC仅供参考。
- add_unit时传入裸装base_ac(10)，通过equipment自动计算最终AC
- 装备/卸下时自动重算AC
- get_ac_breakdown()可查看AC分解

## HP规则
HP以NPC/PC档案中的数值为准。combat_manager只记录状态，不生成HP。
"""

import json
import os
import math

class CombatManager:
    def __init__(self, filename="combat_state.json"):
        self.filename = filename
        self.state = self.load()
    
    def load(self):
        """加载战斗状态"""
        try:
            with open(self.filename, 'r') as f:
                return json.load(f)
        except:
            return {
                "combat_id": "new_combat",
                "round": 1,
                "current_turn": 0,
                "initiative_order": [],
                "units": {},
                "terrain": [],
                "auras": [],
                "active_effects": [],
                "concentration": None,  # {"unit": "奎利昂", "effect_id": "...", "spell": "护盾术"}
                "map_width": 12,
                "map_height": 12
            }
    
    def save(self):
        """保存战斗状态"""
        with open(self.filename, 'w') as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)
    
    # ========== 初始化 ==========
    
    def init_combat(self, combat_id, width=12, height=12):
        """初始化新战斗"""
        self.state = {
            "combat_id": combat_id,
            "round": 1,
            "current_turn": 0,
            "initiative_order": [],
            "units": {},
            "terrain": [],
            "auras": [],
            "active_effects": [],
            "concentration": None,
            "map_width": width,
            "map_height": height
        }
        self.save()
        return f"战斗初始化: {combat_id} ({width}x{height}格)"
    
    def add_unit(self, name, x, y, hp, max_hp, ac, symbol=None, is_player=False, 
                 dex_mod=0, equipment=None,
                 save_proficiencies=None,
                 ability_mods=None,
                 damage_immunities=None,
                 damage_resistances=None,
                 damage_vulnerabilities=None,
                 size="medium",
                 movement_speed=30):
        """添加单位
        
        ac: 基础AC（无装备时: 10 + DEX修正值）
        dex_mod: 敏捷修正值
        equipment: 装备列表，每项为字典:
            {
                "name": "嵌钉皮甲",
                "type": "armor",        # armor / shield / style / weapon_bonus / spell / other
                "ac_base": 12,          # 盔甲基础AC（仅armor类型有效）
                "ac_bonus": 0,          # 固定AC加值（shield=2, style=1, 等）
                "dex_cap": null,        # DEX上限（null=无上限, 2=中甲, 0=重甲）
                "conditional": null     # 条件描述（如"同时持双剑时"）
            }
        save_proficiencies: 具有熟练豁免的属性列表，如 ["con", "wis"]
        ability_mods: 六属性修正值，如 {"str": -1, "dex": 2, "con": 1, "int": 0, "wis": 0, "cha": 0}
        damage_immunities: 伤害免疫列表，如 ["poison", "necrotic"]
        damage_resistances: 伤害抗性列表，如 ["cold", "fire"]
        damage_vulnerabilities: 伤害易伤列表，如 ["radiant"]
        size: 体型 tiny/small/medium/large/huge/gargantuan
        movement_speed: 移动速度（尺），默认30尺
        """
        if symbol is None:
            if is_player:
                symbol = "奎" if "奎利昂" in name else "艾" if "艾丝缇娅" in name else name[0]
            else:
                symbol = name[:2] if len(name) >= 2 else name
        
        if equipment is None:
            equipment = []
        
        self.state["units"][name] = {
            "x": x,
            "y": y,
            "hp": hp,
            "max_hp": max_hp,
            "ac": ac,
            "base_ac": ac,
            "dex_mod": dex_mod,
            "equipment": equipment,
            "symbol": symbol,
            "is_player": is_player,
            "status": [],
            "conditions": [],
            # === 新增: 豁免/抗性/死亡豁免 ===
            "save_proficiencies": save_proficiencies or [],
            "ability_mods": ability_mods or {
                "str": 0, "dex": dex_mod, "con": 0, "int": 0, "wis": 0, "cha": 0
            },
            "proficiency_bonus": 3,  # 5级 = +3
            "damage_immunities": damage_immunities or [],
            "damage_resistances": damage_resistances or [],
            "damage_vulnerabilities": damage_vulnerabilities or [],
            "death_saves": {"successes": 0, "failures": 0},
            "temp_hp": 0,
            "reaction_used": False,  # 保留兼容，由action_economy同步
            # === 行动经济 ===
            "action_economy": {
                "action_used": False,
                "bonus_action_used": False,
                "reaction_used": False,
                "movement_used": 0,
                "movement_max": movement_speed // 5,  # 30尺=6格
                "free_interaction_used": False
            },
            # === 体型 ===
            "size": size,  # tiny/small/medium/large/huge/gargantuan
            "size_grids": {"tiny": 1, "small": 1, "medium": 1, "large": 2, "huge": 3, "gargantuan": 4}.get(size, 1)
        }
        self.save()
        eff_ac = self.get_effective_ac(name)
        return f"添加单位: {name} @ ({x},{y}) HP:{hp}/{max_hp} AC:{eff_ac}"
    
    # ========== 装备系统 ==========
    
    def equip_item(self, name, item):
        """装备物品
        
        item: {"name": "...", "type": "armor|shield|style|weapon_bonus|spell|other",
               "ac_base": N, "ac_bonus": N, "dex_cap": N|null, "conditional": "..."}
        """
        if name not in self.state["units"]:
            return f"找不到 {name}"
        
        unit = self.state["units"][name]
        
        # 同类型互斥（除weapon_bonus和other）
        if item["type"] in ("armor", "shield"):
            unit["equipment"] = [e for e in unit["equipment"] if e["type"] != item["type"]]
        
        unit["equipment"].append(item)
        new_ac = self.get_effective_ac(name)
        unit["ac"] = new_ac
        self.save()
        return f"{name} 装备 {item['name']} → AC: {new_ac}"
    
    def unequip_item(self, name, item_name):
        """卸下装备"""
        if name not in self.state["units"]:
            return f"找不到 {name}"
        
        unit = self.state["units"][name]
        before = len(unit["equipment"])
        unit["equipment"] = [e for e in unit["equipment"] if e["name"] != item_name]
        after = len(unit["equipment"])
        
        if before == after:
            return f"{name} 没有装备 {item_name}"
        
        new_ac = self.get_effective_ac(name)
        unit["ac"] = new_ac
        self.save()
        return f"{name} 卸下 {item_name} → AC: {new_ac}"
    
    def get_effective_ac(self, name):
        """计算有效AC（自动合并所有装备）"""
        if name not in self.state["units"]:
            return 0
        
        unit = self.state["units"][name]
        dex_mod = unit.get("dex_mod", 0)
        equipment = unit.get("equipment", [])
        
        # 无装备基础：10 + DEX
        armor_ac = None
        dex_cap = None
        bonuses = 0
        
        for item in equipment:
            if item["type"] == "armor":
                armor_ac = item.get("ac_base", 10)
                dex_cap = item.get("dex_cap", None)
            elif item["type"] == "shield":
                bonuses += item.get("ac_bonus", 2)
            elif item["type"] == "style":
                bonuses += item.get("ac_bonus", 1)
            elif item["type"] == "weapon_bonus":
                # 条件性加值（如干将莫邪），暂时加入bonuses
                # 实际应该由调用方在满足条件时才添加
                bonuses += item.get("ac_bonus", 0)
            elif item["type"] == "spell":
                bonuses += item.get("ac_bonus", 0)
            elif item["type"] == "other":
                bonuses += item.get("ac_bonus", 0)
        
        # 计算DEX有效加值
        if dex_cap is not None:
            effective_dex = min(dex_mod, dex_cap)
        else:
            effective_dex = dex_mod
        
        if armor_ac is not None:
            total = armor_ac + effective_dex + bonuses
        else:
            total = 10 + effective_dex + bonuses
        
        return total
    
    def get_ac_breakdown(self, name):
        """获取AC分解（用于调试/显示）"""
        if name not in self.state["units"]:
            return "找不到单位"
        
        unit = self.state["units"][name]
        dex_mod = unit.get("dex_mod", 0)
        equipment = unit.get("equipment", [])
        
        lines = [f"【{name} AC分解】"]
        
        armor_ac = None
        dex_cap = None
        bonuses = []
        
        for item in equipment:
            if item["type"] == "armor":
                armor_ac = item.get("ac_base", 10)
                dex_cap = item.get("dex_cap", None)
                cap_str = f" (DEX上限{dex_cap})" if dex_cap is not None else ""
                lines.append(f"  盔甲: {item['name']} 基础AC {armor_ac}{cap_str}")
            elif item["type"] == "shield":
                bonuses.append(f"  盾牌: {item['name']} +{item.get('ac_bonus', 2)}")
            elif item["type"] == "style":
                bonuses.append(f"  风格: {item['name']} +{item.get('ac_bonus', 1)}")
            elif item["type"] == "weapon_bonus":
                cond = item.get("conditional", "")
                bonuses.append(f"  武器: {item['name']} +{item.get('ac_bonus', 0)} {cond}")
            elif item["type"] == "spell":
                bonuses.append(f"  法术: {item['name']} +{item.get('ac_bonus', 0)}")
            elif item["type"] == "other":
                bonuses.append(f"  其他: {item['name']} +{item.get('ac_bonus', 0)}")
        
        for b in bonuses:
            lines.append(b)
        
        # DEX
        if dex_cap is not None:
            effective_dex = min(dex_mod, dex_cap)
            lines.append(f"  DEX: {dex_mod} (有效{effective_dex})")
        else:
            lines.append(f"  DEX: {dex_mod}")
        
        total = self.get_effective_ac(name)
        lines.append(f"  ═══════")
        lines.append(f"  总计AC: {total}")
        
        return "\n".join(lines)
    
    def add_terrain(self, x, y, terrain_type):
        """添加地形"""
        self.state["terrain"].append({"x": x, "y": y, "type": terrain_type})
        self.save()
        return f"添加地形: ({x},{y}) = {terrain_type}"
    
    def add_aura(self, center_x, center_y, radius, name):
        """添加光环"""
        self.state["auras"].append({
            "center_x": center_x,
            "center_y": center_y,
            "radius": radius,
            "name": name
        })
        self.save()
        return f"添加光环: {name} 中心({center_x},{center_y}) 半径{radius}格"
    
    # ========== 先攻系统 ==========
    
    def set_initiative(self, name, initiative):
        """设置先攻值"""
        if name not in [i["name"] for i in self.state["initiative_order"]]:
            self.state["initiative_order"].append({"name": name, "initiative": initiative})
            # 按先攻值排序（高到低）
            self.state["initiative_order"].sort(key=lambda x: x["initiative"], reverse=True)
            self.save()
        return f"设置先攻: {name} = {initiative}"
    
    def get_initiative_order(self):
        """获取先攻顺序"""
        return self.state["initiative_order"]
    
    def get_current_unit(self):
        """获取当前行动单位"""
        if self.state["initiative_order"]:
            idx = self.state["current_turn"] % len(self.state["initiative_order"])
            return self.state["initiative_order"][idx]["name"]
        return None
    
    def next_turn(self):
        """进入下一个行动，并自动解析持续效果"""
        # 结束当前单位的回合效果
        current = self.get_current_unit()
        end_results = self.resolve_effects("end_of_turn", current)
        
        # 推进回合
        self.state["current_turn"] += 1
        if self.state["current_turn"] >= len(self.state["initiative_order"]):
            self.state["current_turn"] = 0
            self.state["round"] += 1
            # 新轮开始时重置所有单位的行动经济
            self.reset_action_economy()
            # 新轮开始时解析轮级效果
            self.resolve_effects("start_of_round")
        
        self.save()
        
        # 新单位回合开始时解析效果
        new_current = self.get_current_unit()
        start_results = self.resolve_effects("start_of_turn", new_current)
        
        # 构建输出
        output = f"回合 {self.state['round']}, 轮到 {new_current}"
        
        effect_messages = []
        for r in end_results + start_results:
            effect_messages.append(f"  ⚡ {r['effect']['name']}: {r['result']}")
        
        if effect_messages:
            output += "\n【自动效果】\n" + "\n".join(effect_messages)
        
        return output
    
    # ========== 单位操作 ==========
    
    def move_unit(self, name, x, y):
        """移动单位"""
        if name in self.state["units"]:
            old_x, old_y = self.state["units"][name]["x"], self.state["units"][name]["y"]
            self.state["units"][name]["x"] = x
            self.state["units"][name]["y"] = y
            self.save()
            distance = math.sqrt((x-old_x)**2 + (y-old_y)**2) * 5
            return f"{name} 移动: ({old_x},{old_y}) → ({x},{y}) [{distance:.0f}尺]"
        return f"找不到 {name}"
    
    def damage_unit(self, name, damage, damage_type=""):
        """造成伤害（自动触发专注检定）
        
        注意：此方法已过时，建议使用 take_damage() 来自动处理抗性
        """
        # 使用新的 take_damage 方法处理伤害
        result = self.take_damage(name, damage, damage_type, "damage_unit")
        
        # 专注检定（受伤时自动检查）
        conc_result = self.check_concentration(name, damage)
        if conc_result:
            result += f"\n{conc_result}"
        
        return result
    
    def heal_unit(self, name, healing):
        """治疗"""
        if name in self.state["units"]:
            unit = self.state["units"][name]
            old_hp = unit["hp"]
            unit["hp"] = min(unit["max_hp"], unit["hp"] + healing)
            # 治疗时重置死亡豁免
            if old_hp == 0:
                unit["death_saves"] = {"successes": 0, "failures": 0}
            self.save()
            return f"{name} 恢复 {healing} HP | HP: {old_hp} → {unit['hp']}/{unit['max_hp']}"
        return f"找不到 {name}"

    # ========== 豁免检定系统 ==========

    def saving_throw(self, name, ability, dc, advantage=False, disadvantage=False):
        """豁免检定
        
        参数:
            name: 单位名
            ability: 属性名 ("str","dex","con","int","wis","cha")
            dc: 豁免DC
            advantage: 优势骰
            disadvantage: 劣势骰
        
        返回: (是否成功, 详细信息字符串)
        """
        import random
        
        if name not in self.state["units"]:
            return False, f"找不到 {name}"
        
        unit = self.state["units"][name]
        ability_mod = unit.get("ability_mods", {}).get(ability, 0)
        prof_bonus = unit.get("proficiency_bonus", 3)
        is_proficient = ability in unit.get("save_proficiencies", [])
        total_bonus = ability_mod + (prof_bonus if is_proficient else 0)
        
        # 掷骰
        roll1 = random.randint(1, 20)
        roll2 = random.randint(1, 20)
        
        if advantage and not disadvantage:
            roll = max(roll1, roll2)
            dice_str = f"d20({roll1},{roll2})取高={roll}"
        elif disadvantage and not advantage:
            roll = min(roll1, roll2)
            dice_str = f"d20({roll1},{roll2})取低={roll}"
        else:
            roll = roll1
            dice_str = f"d20={roll}"
        
        total = roll + total_bonus
        success = total >= dc
        
        # 构建详情
        prof_str = f"+{prof_bonus}熟练" if is_proficient else ""
        mod_str = f"+{ability_mod}" if ability_mod >= 0 else str(ability_mod)
        
        ability_names = {
            "str": "力量", "dex": "敏捷", "con": "体质",
            "int": "智力", "wis": "感知", "cha": "魅力"
        }
        ability_cn = ability_names.get(ability, ability)
        
        result_str = "✅ 成功" if success else "❌ 失败"
        # 特殊：自然20自动成功，自然1自动失败
        special = ""
        if roll == 20 and not success:
            special = " (自然20自动成功!)"
            success = True
        elif roll == 1 and success:
            special = " (自然1自动失败!)"
            success = False
        
        detail = f"{ability_cn}豁免 DC{dc}: {dice_str} {mod_str}{prof_str} = {total} vs {dc}{special} → {result_str}"
        return success, detail

    # ========== 伤害抗性系统 ==========

    def take_damage(self, name, damage, damage_type="", source=""):
        """造成伤害（自动应用免疫/抗性/易伤 + 临时HP）
        
        参数:
            name: 目标单位
            damage: 原始伤害值（int）
            damage_type: 伤害类型 ("slashing","piercing","fire","cold","necrotic"等)
            source: 伤害来源描述
        
        返回: 详情字符串
        """
        if name not in self.state["units"]:
            return f"找不到 {name}"
        
        unit = self.state["units"][name]
        immunities = [t.lower() for t in unit.get("damage_immunities", [])]
        resistances = [t.lower() for t in unit.get("damage_resistances", [])]
        vulnerabilities = [t.lower() for t in unit.get("damage_vulnerabilities", [])]
        dt = damage_type.lower() if damage_type else ""
        
        original_damage = damage
        modifier = ""
        
        # 1. 免疫
        if dt and dt in immunities:
            damage = 0
            modifier = f"免疫({damage_type})"
        # 2. 抗性（在免疫之后检查）
        elif dt and dt in resistances:
            damage = max(1, damage // 2)  # 抗性至少1伤害（除非免疫）
            modifier = f"抗性({damage_type})半伤"
        # 3. 易伤（在抗性之后检查）
        elif dt and dt in vulnerabilities:
            damage = damage * 2
            modifier = f"易伤({damage_type})双倍"
        
        after_modifier_damage = damage  # 保存抗性/易伤后的中间值
        
        # 4. 先扣临时HP
        temp_hp = unit.get("temp_hp", 0)
        temp_absorbed = 0
        if temp_hp > 0:
            temp_absorbed = min(temp_hp, damage)
            unit["temp_hp"] = temp_hp - temp_absorbed
            damage = damage - temp_absorbed
        
        # 5. 扣实际HP
        old_hp = unit["hp"]
        unit["hp"] = max(0, unit["hp"] - damage)
        self.save()
        
        # 构建输出
        parts = []
        if original_damage != after_modifier_damage and modifier:
            parts.append(f"原始{original_damage}→{modifier}→{after_modifier_damage}")
        if temp_absorbed > 0:
            parts.append(f"临时HP吸收{temp_absorbed}")
        
        detail_str = f" [{', '.join(parts)}]" if parts else ""
        status = ""
        if unit["hp"] == 0:
            status = "💀 已倒地！"
            # 倒地时清除所有非死亡状态，添加倒地状态
            if "倒地" not in unit["conditions"]:
                unit["conditions"].append("倒地")
            self.save()
        elif unit["hp"] <= unit["max_hp"] * 0.25:
            status = "⚠️ 濒危！"
        
        source_str = f" ({source})" if source else ""
        return f"{name} 受到 {damage} {damage_type}伤害{detail_str}{source_str} | HP: {old_hp}→{unit['hp']}/{unit['max_hp']} {status}"

    # ========== 死亡豁免系统 ==========

    def death_save(self, name, roll=None):
        """死亡豁免检定
        
        参数:
            name: 单位名（必须HP=0）
            roll: 手动指定骰子结果（None则自动掷d20）
        
        返回: 详情字符串
        """
        import random
        
        if name not in self.state["units"]:
            return f"找不到 {name}"
        
        unit = self.state["units"][name]
        
        if unit["hp"] > 0:
            return f"{name} HP={unit['hp']}，不需要死亡豁免"
        
        if roll is None:
            roll = random.randint(1, 20)
        
        saves = unit.get("death_saves", {"successes": 0, "failures": 0})
        result = ""
        
        if roll == 20:
            # 自然20：恢复1HP
            unit["hp"] = 1
            saves["successes"] = 0
            saves["failures"] = 0
            if "倒地" in unit["conditions"]:
                unit["conditions"].remove("倒地")
            self.save()
            return f"🎲 死亡豁免 d20={roll} → 自然20! {name} 恢复1HP!"
        
        elif roll == 1:
            # 自然1：计2次失败
            saves["failures"] += 2
            result = "自然1! 计2次失败"
        
        elif roll >= 10:
            # 成功
            saves["successes"] += 1
            result = f"成功 ({saves['successes']}成功/{saves['failures']}失败)"
        
        else:
            # 失败
            saves["failures"] += 1
            result = f"失败 ({saves['successes']}成功/{saves['failures']}失败)"
        
        unit["death_saves"] = saves
        
        # 检查结果
        final = ""
        if saves["successes"] >= 3:
            final = " ✨ 已稳定（不需再骰死亡豁免，但仍需治疗才能行动）"
        elif saves["failures"] >= 3:
            final = " ☠️ 已死亡！"
            unit["conditions"].append("死亡")
        
        self.save()
        return f"🎲 死亡豁免 d20={roll} → {result}{final}"

    def get_death_saves(self, name):
        """查看死亡豁免状态"""
        if name not in self.state["units"]:
            return f"找不到 {name}"
        
        unit = self.state["units"][name]
        saves = unit.get("death_saves", {"successes": 0, "failures": 0})
        
        if unit["hp"] > 0:
            return f"{name} HP={unit['hp']}，不需要死亡豁免"
        
        s = "●" * saves["successes"] + "○" * (3 - saves["successes"])
        f = "●" * saves["failures"] + "○" * (3 - saves["failures"])
        return f"{name} 死亡豁免: ✅{s} ❌{f}"

    # ========== 临时HP ==========

    def set_temp_hp(self, name, amount):
        """设置临时HP（取较高值，不叠加）
        
        参数:
            name: 单位名
            amount: 临时HP值
        
        返回: 详情字符串
        """
        if name not in self.state["units"]:
            return f"找不到 {name}"
        
        unit = self.state["units"][name]
        old_temp = unit.get("temp_hp", 0)
        new_temp = max(old_temp, amount)  # 临时HP取高值，不叠加
        unit["temp_hp"] = new_temp
        self.save()
        return f"{name} 临时HP: {old_temp}→{new_temp}"

    # ========== 行动经济系统 ==========

    def _get_economy(self, name):
        """获取行动经济字典（兼容旧数据）"""
        if name not in self.state["units"]:
            return None
        unit = self.state["units"][name]
        eco = unit.get("action_economy")
        if not eco:
            # 兼容旧数据：从reaction_used迁移
            eco = {
                "action_used": False,
                "bonus_action_used": False,
                "reaction_used": unit.get("reaction_used", False),
                "movement_used": 0,
                "movement_max": 6,
                "free_interaction_used": False
            }
            unit["action_economy"] = eco
        return eco

    def use_action(self, name):
        """标记使用了主要动作"""
        eco = self._get_economy(name)
        if not eco:
            return f"找不到 {name}"
        if eco["action_used"]:
            return f"{name} 本轮已使用过主要动作"
        eco["action_used"] = True
        self.state["units"][name]["reaction_used"] = eco["reaction_used"]  # 同步
        self.save()
        return f"{name} 使用了主要动作"

    def use_bonus_action(self, name):
        """标记使用了附赠动作"""
        eco = self._get_economy(name)
        if not eco:
            return f"找不到 {name}"
        if eco["bonus_action_used"]:
            return f"{name} 本轮已使用过附赠动作"
        eco["bonus_action_used"] = True
        self.save()
        return f"{name} 使用了附赠动作"

    def use_reaction(self, name):
        """标记已使用反应"""
        eco = self._get_economy(name)
        if not eco:
            return f"找不到 {name}"
        if eco["reaction_used"]:
            return f"{name} 本轮已使用过反应"
        eco["reaction_used"] = True
        self.state["units"][name]["reaction_used"] = True  # 同步旧字段
        self.save()
        return f"{name} 使用了反应（本轮不能再使用反应）"

    def use_movement(self, name, grids):
        """标记使用了移动距离
        
        grids: 移动格数
        
        返回: (是否成功, 详情字符串)
        """
        eco = self._get_economy(name)
        if not eco:
            return False, f"找不到 {name}"
        
        remaining = eco["movement_max"] - eco["movement_used"]
        if grids > remaining:
            return False, f"{name} 移动不足! 剩余{remaining}格({remaining*5}尺), 试图移动{grids}格({grids*5}尺)"
        
        eco["movement_used"] += grids
        self.save()
        used = eco["movement_used"]
        total = eco["movement_max"]
        return True, f"{name} 移动{grids}格({grids*5}尺) | 已用{used}/{total}格({used*5}/{total*5}尺)"

    def use_free_interaction(self, name):
        """标记使用了免费物品交互"""
        eco = self._get_economy(name)
        if not eco:
            return f"找不到 {name}"
        if eco["free_interaction_used"]:
            return f"{name} 本轮已使用过免费交互"
        eco["free_interaction_used"] = True
        self.save()
        return f"{name} 使用了免费物品交互"

    def reset_action_economy(self, name=None):
        """重置行动经济
        
        name: 指定单位名，None则重置所有单位
        """
        targets = [name] if name else list(self.state["units"].keys())
        for n in targets:
            if n in self.state["units"]:
                unit = self.state["units"][n]
                eco = self._get_economy(n)
                if eco:
                    eco["action_used"] = False
                    eco["bonus_action_used"] = False
                    eco["reaction_used"] = False
                    eco["movement_used"] = 0
                    eco["free_interaction_used"] = False
                    unit["reaction_used"] = False  # 同步旧字段
        self.save()
        return f"行动经济已重置: {', '.join(targets)}"

    def check_action_economy(self, name):
        """查看行动经济状态"""
        eco = self._get_economy(name)
        if not eco:
            return f"找不到 {name}"
        
        def mark(used):
            return "❌" if used else "✅"
        
        move_remaining = eco["movement_max"] - eco["movement_used"]
        lines = [
            f"【{name} 行动经济】",
            f"  {mark(eco['action_used'])} 主要动作 {'已用' if eco['action_used'] else '可用'}",
            f"  {mark(eco['bonus_action_used'])} 附赠动作 {'已用' if eco['bonus_action_used'] else '可用'}",
            f"  {mark(eco['reaction_used'])} 反应 {'已用' if eco['reaction_used'] else '可用'}",
            f"  {'⚠️' if move_remaining == 0 else '🏃'} 移动: 已用{eco['movement_used']}格 / 剩余{move_remaining}格 ({move_remaining*5}尺)",
            f"  {mark(eco['free_interaction_used'])} 免费交互 {'已用' if eco['free_interaction_used'] else '可用'}"
        ]
        return "\n".join(lines)

    def can_use_action(self, name, action_type="action"):
        """检查是否可以使用某种行动类型
        
        action_type: "action" / "bonus_action" / "reaction" / "movement" / "free_interaction"
        """
        eco = self._get_economy(name)
        if not eco:
            return False
        
        if action_type == "action":
            return not eco["action_used"]
        elif action_type == "bonus_action":
            return not eco["bonus_action_used"]
        elif action_type == "reaction":
            return not eco["reaction_used"]
        elif action_type == "movement":
            return (eco["movement_max"] - eco["movement_used"]) > 0
        elif action_type == "free_interaction":
            return not eco["free_interaction_used"]
        return False

    # ========== 体型系统 ==========

    def get_occupied_grids(self, name):
        """获取单位占据的所有格子坐标列表
        
        返回: [(x, y), ...] 左下角为(x,y)
        """
        if name not in self.state["units"]:
            return []
        unit = self.state["units"]
        base_x = self.state["units"][name]["x"]
        base_y = self.state["units"][name]["y"]
        grids = self.state["units"][name].get("size_grids", 1)
        
        occupied = []
        for dx in range(grids):
            for dy in range(grids):
                occupied.append((base_x + dx, base_y + dy))
        return occupied

    def set_size(self, name, size):
        """设置单位体型
        
        size: tiny/small/medium/large/huge/gargantuan
        """
        if name not in self.state["units"]:
            return f"找不到 {name}"
        
        size_map = {"tiny": 1, "small": 1, "medium": 1, "large": 2, "huge": 3, "gargantuan": 4}
        grids = size_map.get(size, 1)
        
        self.state["units"][name]["size"] = size
        self.state["units"][name]["size_grids"] = grids
        self.save()
        return f"{name} 体型: {size} ({grids}×{grids}格)"
    
    def push_unit(self, name, direction, distance_grids):
        """推离单位
        
        direction: (dx, dy) 方向向量，如 (1, 0) 表示向右
        distance_grids: 推离格数
        """
        if name in self.state["units"]:
            unit = self.state["units"][name]
            dx, dy = direction
            old_x, old_y = unit["x"], unit["y"]
            unit["x"] += dx * distance_grids
            unit["y"] += dy * distance_grids
            # 确保在地图范围内
            unit["x"] = max(1, min(self.state["map_width"], unit["x"]))
            unit["y"] = max(1, min(self.state["map_height"], unit["y"]))
            self.save()
            distance_feet = distance_grids * 5
            return f"{name} 被推离 {distance_feet}尺 | ({old_x},{old_y}) → ({unit['x']},{unit['y']})"
        return f"找不到 {name}"
    
    def add_condition(self, name, condition):
        """添加状态效果"""
        if name in self.state["units"]:
            if condition not in self.state["units"][name]["conditions"]:
                self.state["units"][name]["conditions"].append(condition)
                self.save()
            return f"{name} 获得状态: {condition}"
        return f"找不到 {name}"
    
    def remove_condition(self, name, condition):
        """移除状态效果"""
        if name in self.state["units"]:
            if condition in self.state["units"][name]["conditions"]:
                self.state["units"][name]["conditions"].remove(condition)
                self.save()
            return f"{name} 移除状态: {condition}"
        return f"找不到 {name}"
    
    # ========== 持续效果系统（Active Effects） ==========
    
    def add_effect(self, name, target, trigger, effect_type, effect_data,
                   source=None, duration_type="instant", duration_value=None,
                   is_concentration=False, spell_name=None):
        """添加持续效果
        
        参数:
            name: 效果名称（如"莫邪飞回"、"护盾术"）
            target: 目标单位名
            trigger: 触发时机
                - "start_of_turn"  目标回合开始时
                - "end_of_turn"    目标回合结束时
                - "start_of_round" 每轮开始时
                - "on_hit"         被命中时
                - "on_damage"      受伤时
            effect_type: 效果类型
                - "return_weapon"  飞回武器
                - "ac_bonus"       AC加值
                - "damage_over_time" 持续伤害
                - "condition"      状态附加
                - "remove_condition" 移除状态
                - "heal"           治疗
                - "custom"         自定义（effect_data.description描述）
            effect_data: 效果数据（字典）
            source: 效果来源（施法者/使用者）
            duration_type: 持续类型
                - "instant"       瞬发（触发一次后移除）
                - "rounds"        持续N轮
                - "until_removed" 手动移除
                - "concentration" 专注（被打断时移除）
            duration_value: 持续值（rounds时为轮数）
            is_concentration: 是否为专注效果
            spell_name: 法术名称（专注时必填）
        """
        if "active_effects" not in self.state:
            self.state["active_effects"] = []
        
        effect_id = f"effect_{len(self.state['active_effects'])}_{self.state['round']}"
        
        effect = {
            "id": effect_id,
            "name": name,
            "target": target,
            "source": source or target,
            "trigger": trigger,
            "effect_type": effect_type,
            "effect_data": effect_data,
            "created_round": self.state["round"],
            "duration_type": duration_type,
            "duration_value": duration_value,
            "is_concentration": is_concentration,
            "resolved": False
        }
        
        self.state["active_effects"].append(effect)
        
        # 专注处理：打断旧专注，设置新专注
        conc_msg = ""
        if is_concentration:
            spell = spell_name or name
            conc_msg = self.start_concentration(source or target, spell, effect_id)
        
        self.save()
        
        msg = f"添加效果: {name} → {target} [{trigger}] ({duration_type})"
        if conc_msg:
            msg += f"\n{conc_msg}"
        return msg
    
    def resolve_effects(self, trigger, target=None):
        """解析指定触发时机的效果
        
        参数:
            trigger: 触发时机（start_of_turn / end_of_turn / start_of_round）
            target: 目标单位名（可选，None则解析所有匹配的效果）
        
        返回: 已解析的效果列表
        """
        if "active_effects" not in self.state:
            return []
        
        resolved = []
        remaining = []
        
        for effect in self.state["active_effects"]:
            # 检查触发条件
            if effect["trigger"] != trigger:
                remaining.append(effect)
                continue
            
            # 检查目标
            if target and effect["target"] != target:
                remaining.append(effect)
                continue
            
            # 检查是否已解析
            if effect.get("resolved"):
                continue
            
            # 执行效果
            result = self._execute_effect(effect)
            effect["resolved"] = True
            resolved.append({"effect": effect, "result": result})
            
            # 检查持续时间
            if effect["duration_type"] == "instant":
                # 瞬发效果：执行后移除
                pass  # 不加入remaining
            elif effect["duration_type"] == "rounds":
                # 持续N轮：检查是否到期
                elapsed = self.state["round"] - effect["created_round"]
                if elapsed >= effect["duration_value"]:
                    pass  # 到期，移除
                else:
                    effect["resolved"] = False  # 未到期，重置
                    remaining.append(effect)
            elif effect["duration_type"] == "until_removed":
                remaining.append(effect)  # 手动移除
            elif effect["duration_type"] == "concentration":
                remaining.append(effect)  # 专注，直到被打断
        
        self.state["active_effects"] = remaining
        self.save()
        return resolved
    
    def _execute_effect(self, effect):
        """执行效果内部逻辑"""
        effect_type = effect["effect_type"]
        data = effect["effect_data"]
        target = effect["target"]
        
        if effect_type == "return_weapon":
            item = data.get("item", "?")
            return f"{target} 的 {item} 飞回手中！"
        
        elif effect_type == "ac_bonus":
            bonus = data.get("bonus", 0)
            if target in self.state["units"]:
                self.state["units"][target]["ac"] += bonus
            return f"{target} AC +{bonus}"
        
        elif effect_type == "damage_over_time":
            damage_str = data.get("damage", "1d4")
            damage_type = data.get("damage_type", "")
            # 简化：取平均值
            parts = damage_str.split("d")
            if len(parts) == 2:
                avg = int(parts[0]) * (int(parts[1]) + 1) // 2
            else:
                avg = int(damage_str)
            if target in self.state["units"]:
                self.state["units"][target]["hp"] = max(0, self.state["units"][target]["hp"] - avg)
            return f"{target} 受到 {avg} {damage_type}持续伤害"
        
        elif effect_type == "condition":
            condition = data.get("condition", "")
            if target in self.state["units"]:
                if condition not in self.state["units"][target]["conditions"]:
                    self.state["units"][target]["conditions"].append(condition)
            return f"{target} 获得状态: {condition}"
        
        elif effect_type == "remove_condition":
            condition = data.get("condition", "")
            if target in self.state["units"]:
                if condition in self.state["units"][target]["conditions"]:
                    self.state["units"][target]["conditions"].remove(condition)
            return f"{target} 移除状态: {condition}"
        
        elif effect_type == "heal":
            heal = data.get("amount", 0)
            if target in self.state["units"]:
                unit = self.state["units"][target]
                unit["hp"] = min(unit["max_hp"], unit["hp"] + heal)
            return f"{target} 恢复 {heal} HP"
        
        elif effect_type == "custom":
            return data.get("description", f"自定义效果作用于 {target}")
        
        return f"未知效果类型: {effect_type}"
    
    def remove_effect(self, effect_id=None, name=None, target=None):
        """移除持续效果
        
        可通过effect_id、name、target任意组合定位效果
        """
        if "active_effects" not in self.state:
            return "没有活跃效果"
        
        before = len(self.state["active_effects"])
        remaining = []
        
        for effect in self.state["active_effects"]:
            match = True
            if effect_id and effect["id"] != effect_id:
                match = False
            if name and effect["name"] != name:
                match = False
            if target and effect["target"] != target:
                match = False
            
            if not match:
                remaining.append(effect)
        
        self.state["active_effects"] = remaining
        self.save()
        removed = before - len(remaining)
        return f"移除 {removed} 个效果"
    
    def list_effects(self, target=None):
        """列出活跃效果"""
        if "active_effects" not in self.state:
            return "没有活跃效果"
        
        effects = self.state["active_effects"]
        if target:
            effects = [e for e in effects if e["target"] == target]
        
        if not effects:
            return "没有活跃效果"
        
        lines = ["【活跃效果】"]
        for e in effects:
            dur = ""
            if e["duration_type"] == "rounds":
                elapsed = self.state["round"] - e["created_round"]
                remaining = e["duration_value"] - elapsed
                dur = f" (剩余{remaining}轮)"
            elif e["duration_type"] == "until_removed":
                dur = " (手动移除)"
            elif e["duration_type"] == "concentration":
                dur = " (专注)"
            
            lines.append(f"  {e['name']} → {e['target']} [{e['trigger']}]{dur}")
        
        return "\n".join(lines)
    
    # ========== 专注系统（Concentration） ==========
    
    def start_concentration(self, unit_name, spell_name, effect_id=None):
        """开始专注
        
        如果该单位已在专注中，自动打断旧专注
        """
        old_conc = self.state.get("concentration")
        msg_list = []
        
        # 打断旧专注
        if old_conc and old_conc["unit"] == unit_name:
            msg_list.append(f"  🧠 {unit_name} 打断旧专注: {old_conc['spell']}")
            self._break_concentration_effect(old_conc)
        
        # 设置新专注
        self.state["concentration"] = {
            "unit": unit_name,
            "spell": spell_name,
            "effect_id": effect_id,
            "started_round": self.state["round"]
        }
        self.save()
        
        msg_list.append(f"  🧠 {unit_name} 开始专注: {spell_name}")
        return "\n".join(msg_list)
    
    def check_concentration(self, unit_name, damage_taken):
        """专注检定（受伤时触发）
        
        D&D 5e 专注规则：
        - 受到伤害时必须进行体质豁免
        - DC = max(10, 伤害/2)（向下取整）
        - 成功：维持专注
        - 失败：专注被打断
        
        返回专注检定结果，如果没有专注则返回空字符串
        """
        conc = self.state.get("concentration")
        if not conc or conc["unit"] != unit_name:
            return ""
        
        import math
        dc = max(10, math.floor(damage_taken / 2))
        
        return (f"  ⚠️ 专注检定: {unit_name} 受到 {damage_taken} 伤害\n"
                f"     DC = max(10, {damage_taken}/2) = {dc}\n"
                f"     需要骰体质豁免 (1d20+CON)")
    
    def maintain_concentration(self, unit_name, save_roll, con_modifier):
        """维持专注（玩家骰出体质豁免后调用）
        
        参数:
            unit_name: 单位名
            save_roll: 体质豁免骰出值（1d20的结果，不含修正值）
            con_modifier: 体质修正值
        
        返回: 检定结果
        """
        conc = self.state.get("concentration")
        if not conc or conc["unit"] != unit_name:
            return f"{unit_name} 没有在专注"
        
        import math
        total = save_roll + con_modifier
        damage_taken = 0  # 需要从上下文获取
        # 简化：DC 10（实际应根据伤害计算，但这里只做基本判断）
        dc = 10
        
        if total >= dc:
            return f"  ✅ 专注维持: {unit_name} 豁免 {save_roll}+{con_modifier}={total} ≥ DC{dc}"
        else:
            return (f"  ❌ 专注失败: {unit_name} 豁免 {save_roll}+{con_modifier}={total} < DC{dc}\n"
                    f"     {self.break_concentration(unit_name)}")
    
    def break_concentration(self, unit_name=None):
        """打断专注
        
        参数:
            unit_name: 单位名（可选，不传则检查当前专注单位）
        """
        conc = self.state.get("concentration")
        if not conc:
            return "没有专注效果"
        
        if unit_name and conc["unit"] != unit_name:
            return f"{unit_name} 不是专注者"
        
        msg = self._break_concentration_effect(conc)
        self.state["concentration"] = None
        self.save()
        return msg
    
    def _break_concentration_effect(self, conc):
        """打断专注时移除关联的效果"""
        effect_id = conc.get("effect_id")
        if effect_id:
            # 从active_effects中移除
            self.state["active_effects"] = [
                e for e in self.state.get("active_effects", [])
                if e["id"] != effect_id
            ]
        return f"  💔 专注被打断: {conc['spell']} 效果消失"
    
    def get_concentration_status(self):
        """获取专注状态"""
        conc = self.state.get("concentration")
        if not conc:
            return "没有专注效果"
        
        elapsed = self.state["round"] - conc["started_round"]
        return f"🧠 {conc['unit']} 专注中: {conc['spell']} (第{elapsed}轮)"
    
    # ========== 距离计算 ==========
    
    def _edge_distance(self, name1, name2):
        """计算两个单位最近边缘之间的距离（尺）
        
        考虑体型：大型(2x2)、巨型(3x3)等占据多格。
        返回最近边缘到最近边缘的距离。
        """
        if name1 not in self.state["units"] or name2 not in self.state["units"]:
            return float('inf')
        
        u1 = self.state["units"][name1]
        u2 = self.state["units"][name2]
        
        s1 = u1.get("size_grids", 1)
        s2 = u2.get("size_grids", 1)
        
        # 计算X和Y轴上最近边缘距离
        # u1 占据 [x1, x1+s1-1], u2 占据 [x2, x2+s2-1]
        x1_end = u1["x"] + s1 - 1
        x2_end = u2["x"] + s2 - 1
        y1_end = u1["y"] + s1 - 1
        y2_end = u2["y"] + s2 - 1
        
        # X轴最近距离（格数）
        if x1_end < u2["x"]:
            dx = u2["x"] - x1_end  # u1完全在u2左边
        elif x2_end < u1["x"]:
            dx = u1["x"] - x2_end  # u1完全在u2右边
        else:
            dx = 0  # X轴重叠
        
        # Y轴最近距离（格数）
        if y1_end < u2["y"]:
            dy = u2["y"] - y1_end
        elif y2_end < u1["y"]:
            dy = u1["y"] - y2_end
        else:
            dy = 0
        
        # 对角线距离（勾股定理）转尺
        return math.sqrt(dx**2 + dy**2) * 5

    def distance(self, name1, name2):
        """计算两个单位之间的距离（考虑体型，最近边缘）"""
        if name1 in self.state["units"] and name2 in self.state["units"]:
            u1 = self.state["units"][name1]
            u2 = self.state["units"][name2]
            s1 = u1.get("size_grids", 1)
            s2 = u2.get("size_grids", 1)
            dist = self._edge_distance(name1, name2)
            size_str1 = f"({s1}x{s1})" if s1 > 1 else ""
            size_str2 = f"({s2}x{s2})" if s2 > 1 else ""
            return f"{name1}{size_str1}@({u1['x']},{u1['y']}) → {name2}{size_str2}@({u2['x']},{u2['y']}) = {dist:.0f}尺(边缘)"
        return f"找不到单位"
    
    def is_adjacent(self, name1, name2):
        """检查两个单位是否相邻（5尺，考虑体型）"""
        if name1 in self.state["units"] and name2 in self.state["units"]:
            dist = self._edge_distance(name1, name2)
            return dist <= 7  # 对角线也算相邻（约7尺）
        return False
    
    def can_attack(self, attacker, target, attack_type="melee", reach_feet=5, range_feet=0):
        """检查是否可以攻击（考虑体型）
        
        attack_type: "melee" (近战), "ranged" (远程), "spell" (法术)
        reach_feet: 近战触及范围（尺），默认5尺
        range_feet: 远程/法术射程（尺），0表示无限制
        
        返回: (是否可以攻击, 距离信息, 建议)
        """
        if attacker not in self.state["units"] or target not in self.state["units"]:
            return False, "找不到单位", "检查单位名称"
        
        dist = self._edge_distance(attacker, target)
        
        if attack_type == "melee":
            if dist <= reach_feet + 2:
                return True, f"距离{dist:.0f}尺(边缘)，在触及范围{reach_feet}尺内", "可以近战攻击"
            else:
                return False, f"距离{dist:.0f}尺(边缘)，超出触及范围{reach_feet}尺", f"需要移动到{reach_feet}尺内"
        
        elif attack_type == "ranged":
            if range_feet == 0:
                return True, f"距离{dist:.0f}尺，无射程限制", "可以远程攻击"
            elif dist <= range_feet:
                return True, f"距离{dist:.0f}尺，在射程{range_feet}尺内", "可以远程攻击"
            else:
                return False, f"距离{dist:.0f}尺，超出射程{range_feet}尺", f"需要移动到{range_feet}尺内"
        
        elif attack_type == "spell":
            if range_feet == 0:
                return True, f"距离{dist:.0f}尺，无距离限制", "可以施法"
            elif dist <= range_feet:
                return True, f"距离{dist:.0f}尺，在施法距离{range_feet}尺内", "可以施法"
            else:
                return False, f"距离{dist:.0f}尺，超出施法距离{range_feet}尺", f"需要移动到{range_feet}尺内"
        
        return False, "未知攻击类型", "检查攻击类型"
    
    def npc_strategy(self, npc_name, target_name, attack_type="melee", reach_feet=5, range_feet=0):
        """NPC策略：根据攻击类型选择最佳位置
        
        attack_type: "melee" (近战), "ranged" (远程), "spell" (法术)
        reach_feet: 近战触及范围
        range_feet: 远程/法术射程
        
        返回: (建议位置, 移动距离, 建议)
        """
        if npc_name not in self.state["units"] or target_name not in self.state["units"]:
            return None, 0, "找不到单位"
        
        npc = self.state["units"][npc_name]
        target = self.state["units"][target_name]
        
        # 计算当前位置
        current_x, current_y = npc["x"], npc["y"]
        target_x, target_y = target["x"], target["y"]
        
        # 计算距离
        dist = math.sqrt((current_x-target_x)**2 + (current_y-target_y)**2) * 5
        
        if attack_type == "melee":
            # 近战策略：移动到触及范围内
            if dist <= reach_feet + 2:
                return (current_x, current_y), 0, "已经在触及范围内，无需移动"
            
            # 计算最佳移动位置（朝目标移动）
            dx = target_x - current_x
            dy = target_y - current_y
            dist_grids = math.sqrt(dx**2 + dy**2)
            
            if dist_grids > 0:
                # 归一化方向
                dx_norm = dx / dist_grids
                dy_norm = dy / dist_grids
                
                # 计算移动步数（每格5尺）
                move_grids = min(6, int((dist - reach_feet) / 5))  # 最多移动6格（30尺）
                
                if move_grids > 0:
                    new_x = current_x + int(dx_norm * move_grids)
                    new_y = current_y + int(dy_norm * move_grids)
                    
                    # 确保在触及范围内
                    new_dist = math.sqrt((new_x-target_x)**2 + (new_y-target_y)**2) * 5
                    if new_dist > reach_feet:
                        # 需要再移动一步
                        move_grids += 1
                        new_x = current_x + int(dx_norm * move_grids)
                        new_y = current_y + int(dy_norm * move_grids)
                    
                    # 确保在地图范围内
                    new_x = max(1, min(self.state["map_width"], new_x))
                    new_y = max(1, min(self.state["map_height"], new_y))
                    
                    move_dist = move_grids * 5
                    return (new_x, new_y), move_dist, f"移动到触及范围{reach_feet}尺内"
            
            return (current_x, current_y), 0, "无法移动到触及范围"
        
        elif attack_type in ["ranged", "spell"]:
            # 远程/法术策略：保持最佳距离
            if range_feet == 0:
                return (current_x, current_y), 0, "无射程限制，当前位置合适"
            
            # 最佳距离：射程的50-75%
            optimal_dist = range_feet * 0.6
            optimal_dist = max(optimal_dist, reach_feet + 5)  # 至少比近战触及范围远5尺
            
            if dist <= range_feet:
                # 在射程内，检查是否需要调整距离
                if dist < optimal_dist - 10:
                    # 太近了，后退
                    dx = current_x - target_x
                    dy = current_y - target_y
                    dist_grids = math.sqrt(dx**2 + dy**2)
                    
                    if dist_grids > 0:
                        dx_norm = dx / dist_grids
                        dy_norm = dy / dist_grids
                        
                        # 后退2-3格
                        retreat_grids = 2
                        new_x = current_x + int(dx_norm * retreat_grids)
                        new_y = current_y + int(dy_norm * retreat_grids)
                        
                        # 确保在地图范围内
                        new_x = max(1, min(self.state["map_width"], new_x))
                        new_y = max(1, min(self.state["map_height"], new_y))
                        
                        new_dist = math.sqrt((new_x-target_x)**2 + (new_y-target_y)**2) * 5
                        if new_dist <= range_feet:
                            return (new_x, new_y), retreat_grids * 5, f"后退到最佳距离{optimal_dist:.0f}尺"
                
                elif dist > optimal_dist + 10:
                    # 太远了，前进
                    dx = target_x - current_x
                    dy = target_y - current_y
                    dist_grids = math.sqrt(dx**2 + dy**2)
                    
                    if dist_grids > 0:
                        dx_norm = dx / dist_grids
                        dy_norm = dy / dist_grids
                        
                        # 前进2-3格
                        advance_grids = 2
                        new_x = current_x + int(dx_norm * advance_grids)
                        new_y = current_y + int(dy_norm * advance_grids)
                        
                        # 确保在地图范围内
                        new_x = max(1, min(self.state["map_width"], new_x))
                        new_y = max(1, min(self.state["map_height"], new_y))
                        
                        new_dist = math.sqrt((new_x-target_x)**2 + (new_y-target_y)**2) * 5
                        if new_dist <= range_feet:
                            return (new_x, new_y), advance_grids * 5, f"前进到最佳距离{optimal_dist:.0f}尺"
                
                return (current_x, current_y), 0, "当前位置距离合适"
            
            else:
                # 超出射程，需要前进
                dx = target_x - current_x
                dy = target_y - current_y
                dist_grids = math.sqrt(dx**2 + dy**2)
                
                if dist_grids > 0:
                    dx_norm = dx / dist_grids
                    dy_norm = dy / dist_grids
                    
                    # 计算需要移动多少格才能进入射程
                    needed_dist = dist - range_feet + 5  # 进入射程后留5尺余量
                    move_grids = int(needed_dist / 5) + 1
                    
                    move_grids = min(move_grids, 6)  # 最多移动6格（30尺）
                    
                    new_x = current_x + int(dx_norm * move_grids)
                    new_y = current_y + int(dy_norm * move_grids)
                    
                    # 确保在地图范围内
                    new_x = max(1, min(self.state["map_width"], new_x))
                    new_y = max(1, min(self.state["map_height"], new_y))
                    
                    move_dist = move_grids * 5
                    new_dist = math.sqrt((new_x-target_x)**2 + (new_y-target_y)**2) * 5
                    
                    if new_dist <= range_feet:
                        return (new_x, new_y), move_dist, f"前进进入射程{range_feet}尺"
                    else:
                        return (new_x, new_y), move_dist, f"前进{move_dist}尺（仍超出射程）"
                
                return (current_x, current_y), 0, "无法移动进入射程"
        
        return (current_x, current_y), 0, "未知攻击类型"
    
    # ========== 地图渲染 ==========
    
    def render_map(self, show_aura=True):
        """从状态文件生成ASCII地图"""
        width = self.state["map_width"]
        height = self.state["map_height"]
        
        # 初始化网格
        grid = [['  .' for _ in range(width)] for _ in range(height)]
        
        # 放置地形
        for terrain in self.state["terrain"]:
            x, y = terrain["x"], terrain["y"]
            if 1 <= x <= width and 1 <= y <= height:
                grid[y-1][x-1] = f' {terrain["type"]}'
        
        # 放置单位
        for name, unit in self.state["units"].items():
            x, y = unit["x"], unit["y"]
            symbol = unit["symbol"]
            size_grids = unit.get("size_grids", 1)
            
            # 填充所有占据的格子
            for dx in range(size_grids):
                for dy in range(size_grids):
                    px, py = x + dx, y + dy
                    if 1 <= px <= width and 1 <= py <= height:
                        # 主格显示符号，其他格显示边框
                        if dx == 0 and dy == 0:
                            grid[py-1][px-1] = f' {symbol}'
                        else:
                            # 大型单位其他格用边框字符
                            border_char = "─" if size_grids > 1 else "·"
                            grid[py-1][px-1] = f' {border_char}'
        
        # 计算光环
        if show_aura:
            for aura in self.state["auras"]:
                cx, cy, r = aura["center_x"], aura["center_y"], aura["radius"]
                for y in range(1, height+1):
                    for x in range(1, width+1):
                        if ((x-cx)**2 + (y-cy)**2) <= r**2:
                            if grid[y-1][x-1] == '  .':
                                grid[y-1][x-1] = ' 光'
        
        # 生成输出
        lines = []
        lines.append(f"【{self.state['combat_id']}】回合 {self.state['round']}")
        lines.append("")
        
        header = "    "
        for x in range(1, width+1):
            header += f" {x:2d}"
        lines.append(header)
        lines.append("   +" + "---" * width + "+")
        
        for y in range(height, 0, -1):
            row = f"{y:2d} |"
            for x in range(1, width+1):
                row += grid[y-1][x-1]
            row += " |"
            lines.append(row)
        
        lines.append("   +" + "---" * width + "+")
        
        # 单位状态
        lines.append("")
        lines.append("【单位状态】")
        for name, unit in self.state["units"].items():
            hp_status = "💀" if unit["hp"] == 0 else "⚠️" if unit["hp"] <= unit["max_hp"] * 0.25 else ""
            conditions = f" [{', '.join(unit['conditions'])}]" if unit["conditions"] else ""
            
            # 体型
            size = unit.get("size", "medium")
            size_grids = unit.get("size_grids", 1)
            size_str = f" {size}({size_grids}x{size_grids})" if size_grids > 1 else ""
            
            # 临时HP
            temp_hp = unit.get("temp_hp", 0)
            temp_str = f" +{temp_hp}T" if temp_hp > 0 else ""
            
            # 死亡豁免（HP=0时显示）
            death_str = ""
            if unit["hp"] == 0:
                saves = unit.get("death_saves", {"successes": 0, "failures": 0})
                s_ok = "●" * saves["successes"] + "○" * (3 - saves["successes"])
                s_fail = "●" * saves["failures"] + "○" * (3 - saves["failures"])
                death_str = f" 死亡豁免:✅{s_ok}❌{s_fail}"
            
            # 反应状态
            reaction_str = " ⚡已用反应" if unit.get("reaction_used") else ""
            
            # 抗性摘要
            res_parts = []
            if unit.get("damage_immunities"):
                res_parts.append(f"免疫:{','.join(unit['damage_immunities'])}")
            if unit.get("damage_resistances"):
                res_parts.append(f"免疫:{','.join(unit['damage_immunities'])}")
            if unit.get("damage_resistances"):
                res_parts.append(f"抗性:{','.join(unit['damage_resistances'])}")
            if unit.get("damage_vulnerabilities"):
                res_parts.append(f"易伤:{','.join(unit['damage_vulnerabilities'])}")
            res_str = f" ({', '.join(res_parts)})" if res_parts else ""
            
            lines.append(f"  {unit['symbol']} {name}{size_str} ({unit['x']},{unit['y']}) | HP: {unit['hp']}/{unit['max_hp']}{temp_str} | AC: {unit['ac']}{conditions}{death_str}{reaction_str}{res_str} {hp_status}")
        
        # 先攻顺序
        if self.state["initiative_order"]:
            lines.append("")
            lines.append("【先攻顺序】")
            current = self.get_current_unit()
            for i, init in enumerate(self.state["initiative_order"]):
                marker = " ◀ 当前" if init["name"] == current else ""
                lines.append(f"  {i+1}. {init['name']} ({init['initiative']}){marker}")
        
        # 光环信息
        if self.state["auras"]:
            lines.append("")
            lines.append("【光环效果】")
            for aura in self.state["auras"]:
                lines.append(f"  {aura['name']} - 中心({aura['center_x']},{aura['center_y']}), 半径{aura['radius']*5}尺")
        
        # 持续效果
        effects = self.state.get("active_effects", [])
        active = [e for e in effects if not e.get("resolved")]
        if active:
            lines.append("")
            lines.append("【持续效果】")
            for e in active:
                dur = ""
                if e["duration_type"] == "rounds":
                    elapsed = self.state["round"] - e["created_round"]
                    remaining = e["duration_value"] - elapsed
                    dur = f" 剩余{remaining}轮"
                elif e["duration_type"] == "concentration":
                    dur = " 专注"
                lines.append(f"  ⚡ {e['name']} → {e['target']} [{e['trigger']}]{dur}")
        
        # 专注状态
        conc = self.state.get("concentration")
        if conc:
            elapsed = self.state["round"] - conc["started_round"]
            lines.append("")
            lines.append("【专注状态】")
            lines.append(f"  🧠 {conc['unit']} 专注中: {conc['spell']} (第{elapsed}轮)")
        
        return "\n".join(lines)
    
    # ========== 状态查询 ==========
    
    def get_unit(self, name):
        """获取单位信息"""
        return self.state["units"].get(name)
    
    def get_all_units(self):
        """获取所有单位"""
        return self.state["units"]
    
    def get_round(self):
        """获取当前回合数"""
        return self.state["round"]
    
    def get_status(self):
        """获取战斗状态摘要"""
        lines = []
        lines.append(f"战斗ID: {self.state['combat_id']}")
        lines.append(f"回合: {self.state['round']}")
        lines.append(f"当前行动: {self.get_current_unit()}")
        lines.append(f"单位数量: {len(self.state['units'])}")
        return "\n".join(lines)


# ========== 命令行接口 ==========

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python3 combat_manager.py <command> [args...]")
        print("命令:")
        print("  init <combat_id> [width] [height]")
        print("  add_unit <name> <x> <y> <hp> <max_hp> <ac> [symbol] [is_player]")
        print("  move <name> <x> <y>")
        print("  damage <name> <damage> [damage_type]")
        print("  take_damage <name> <damage> <damage_type> [source]  # 自动应用抗性")
        print("  heal <name> <healing>")
        print("  push <name> <dx> <dy> <grids>")
        print("  initiative <name> <value>")
        print("  next_turn")
        print("  render")
        print("  status")
        print("  save <name> <ability> <dc> [advantage] [disadvantage]  # 豁免检定")
        print("  death_save <name> [roll]  # 死亡豁免")
        print("  death_saves <name>  # 查看死亡豁免状态")
        print("  temp_hp <name> <amount>  # 设置临时HP")
        print("  use_action <name>  # 标记已使用主要动作")
        print("  use_bonus_action <name>  # 标记已使用附赠动作")
        print("  use_reaction <name>  # 标记已使用反应")
        print("  use_movement <name> <grids>  # 标记已移动格数")
        print("  use_free_interaction <name>  # 标记已使用免费交互")
        print("  check_economy <name>  # 查看行动经济状态")
        print("  reset_economy [name]  # 重置行动经济（无name则重置所有）")
        print("  can_action <name> <action_type>  # 检查是否可使用某行动")
        print("  set_size <name> <size>  # 设置体型 tiny/small/medium/large/huge/gargantuan")
        print("  occupied <name>  # 查看单位占据的格子")
        sys.exit(1)
    
    cm = CombatManager()
    cmd = sys.argv[1]
    
    if cmd == "init":
        combat_id = sys.argv[2] if len(sys.argv) > 2 else "combat"
        width = int(sys.argv[3]) if len(sys.argv) > 3 else 12
        height = int(sys.argv[4]) if len(sys.argv) > 4 else 12
        print(cm.init_combat(combat_id, width, height))
    
    elif cmd == "add_unit":
        name = sys.argv[2]
        x, y = int(sys.argv[3]), int(sys.argv[4])
        hp, max_hp = int(sys.argv[5]), int(sys.argv[6])
        ac = int(sys.argv[7])
        symbol = sys.argv[8] if len(sys.argv) > 8 else None
        is_player = sys.argv[9].lower() == "true" if len(sys.argv) > 9 else False
        print(cm.add_unit(name, x, y, hp, max_hp, ac, symbol, is_player))
    
    elif cmd == "equip":
        # equip <name> <json_item>
        import json as j
        name = sys.argv[2]
        item = j.loads(sys.argv[3])
        print(cm.equip_item(name, item))
    
    elif cmd == "unequip":
        name = sys.argv[2]
        item_name = sys.argv[3]
        print(cm.unequip_item(name, item_name))
    
    elif cmd == "ac_breakdown":
        name = sys.argv[2]
        print(cm.get_ac_breakdown(name))
    
    elif cmd == "move":
        name = sys.argv[2]
        x, y = int(sys.argv[3]), int(sys.argv[4])
        print(cm.move_unit(name, x, y))
    
    elif cmd == "damage":
        name = sys.argv[2]
        damage = int(sys.argv[3])
        damage_type = sys.argv[4] if len(sys.argv) > 4 else ""
        print(cm.damage_unit(name, damage, damage_type))
    
    elif cmd == "heal":
        name = sys.argv[2]
        healing = int(sys.argv[3])
        print(cm.heal_unit(name, healing))
    
    elif cmd == "push":
        name = sys.argv[2]
        dx, dy = int(sys.argv[3]), int(sys.argv[4])
        grids = int(sys.argv[5])
        print(cm.push_unit(name, (dx, dy), grids))
    
    elif cmd == "initiative":
        name = sys.argv[2]
        value = int(sys.argv[3])
        print(cm.set_initiative(name, value))
    
    elif cmd == "next_turn":
        print(cm.next_turn())
    
    elif cmd == "render":
        print(cm.render_map())
    
    elif cmd == "status":
        print(cm.get_status())
    
    elif cmd == "add_effect":
        # add_effect <name> <target> <trigger> <effect_type> <effect_data_json> [source] [duration_type] [duration_value]
        import json as j
        name = sys.argv[2]
        target = sys.argv[3]
        trigger = sys.argv[4]
        effect_type = sys.argv[5]
        effect_data = j.loads(sys.argv[6]) if len(sys.argv) > 6 else {}
        source = sys.argv[7] if len(sys.argv) > 7 else None
        duration_type = sys.argv[8] if len(sys.argv) > 8 else "instant"
        duration_value = int(sys.argv[9]) if len(sys.argv) > 9 else None
        print(cm.add_effect(name, target, trigger, effect_type, effect_data,
                           source, duration_type, duration_value))
    
    elif cmd == "resolve_effects":
        trigger = sys.argv[2] if len(sys.argv) > 2 else "start_of_turn"
        target = sys.argv[3] if len(sys.argv) > 3 else None
        results = cm.resolve_effects(trigger, target)
        for r in results:
            print(f"  ⚡ {r['effect']['name']}: {r['result']}")
        if not results:
            print("没有需要解析的效果")
    
    elif cmd == "list_effects":
        target = sys.argv[2] if len(sys.argv) > 2 else None
        print(cm.list_effects(target))
    
    elif cmd == "remove_effect":
        effect_id = sys.argv[2] if len(sys.argv) > 2 else None
        name = sys.argv[3] if len(sys.argv) > 3 else None
        target = sys.argv[4] if len(sys.argv) > 4 else None
        print(cm.remove_effect(effect_id, name, target))
    
    elif cmd == "start_concentration":
        # start_concentration <unit_name> <spell_name> [effect_id]
        unit = sys.argv[2]
        spell = sys.argv[3]
        effect_id = sys.argv[4] if len(sys.argv) > 4 else None
        print(cm.start_concentration(unit, spell, effect_id))
    
    elif cmd == "break_concentration":
        # break_concentration [unit_name]
        unit = sys.argv[2] if len(sys.argv) > 2 else None
        print(cm.break_concentration(unit))
    
    elif cmd == "maintain_concentration":
        # maintain_concentration <unit_name> <save_roll> <con_modifier>
        unit = sys.argv[2]
        roll = int(sys.argv[3])
        mod = int(sys.argv[4])
        print(cm.maintain_concentration(unit, roll, mod))
    
    elif cmd == "concentration":
        # concentration - 显示专注状态
        print(cm.get_concentration_status())
    
    elif cmd == "save":
        # save <name> <ability> <dc> [advantage] [disadvantage]
        name = sys.argv[2]
        ability = sys.argv[3]
        dc = int(sys.argv[4])
        advantage = sys.argv[5].lower() == "true" if len(sys.argv) > 5 else False
        disadvantage = sys.argv[6].lower() == "true" if len(sys.argv) > 6 else False
        success, detail = cm.saving_throw(name, ability, dc, advantage, disadvantage)
        print(detail)
    
    elif cmd == "take_damage":
        # take_damage <name> <damage> <damage_type> [source]
        name = sys.argv[2]
        damage = int(sys.argv[3])
        damage_type = sys.argv[4] if len(sys.argv) > 4 else ""
        source = sys.argv[5] if len(sys.argv) > 5 else ""
        print(cm.take_damage(name, damage, damage_type, source))
    
    elif cmd == "death_save":
        # death_save <name> [roll]
        name = sys.argv[2]
        roll = int(sys.argv[3]) if len(sys.argv) > 3 else None
        print(cm.death_save(name, roll))
    
    elif cmd == "death_saves":
        # death_saves <name>
        name = sys.argv[2]
        print(cm.get_death_saves(name))
    
    elif cmd == "temp_hp":
        # temp_hp <name> <amount>
        name = sys.argv[2]
        amount = int(sys.argv[3])
        print(cm.set_temp_hp(name, amount))
    
    elif cmd == "use_reaction":
        # use_reaction <name>
        name = sys.argv[2]
        print(cm.use_reaction(name))
    
    elif cmd == "can_reaction":
        # can_reaction <name>
        name = sys.argv[2]
        print(f"{name} {'可以' if cm.can_use_action(name, 'reaction') else '不能'}使用反应")
    
    elif cmd == "use_action":
        # use_action <name>
        name = sys.argv[2]
        print(cm.use_action(name))
    
    elif cmd == "use_bonus_action":
        # use_bonus_action <name>
        name = sys.argv[2]
        print(cm.use_bonus_action(name))
    
    elif cmd == "use_movement":
        # use_movement <name> <grids>
        name = sys.argv[2]
        grids = int(sys.argv[3])
        success, msg = cm.use_movement(name, grids)
        print(msg)
    
    elif cmd == "use_free_interaction":
        # use_free_interaction <name>
        name = sys.argv[2]
        print(cm.use_free_interaction(name))
    
    elif cmd == "check_economy":
        # check_economy <name>
        name = sys.argv[2]
        print(cm.check_action_economy(name))
    
    elif cmd == "reset_economy":
        # reset_economy [name]
        name = sys.argv[2] if len(sys.argv) > 2 else None
        print(cm.reset_action_economy(name))
    
    elif cmd == "can_action":
        # can_action <name> <action_type>
        name = sys.argv[2]
        action_type = sys.argv[3]
        print(f"{name} {'可以' if cm.can_use_action(name, action_type) else '不能'}使用{action_type}")
    
    elif cmd == "set_size":
        # set_size <name> <size>
        name = sys.argv[2]
        size = sys.argv[3]
        print(cm.set_size(name, size))
    
    elif cmd == "occupied":
        # occupied <name>
        name = sys.argv[2]
        grids = cm.get_occupied_grids(name)
        print(f"{name} 占据: {grids}")
    
    else:
        print(f"未知命令: {cmd}")
