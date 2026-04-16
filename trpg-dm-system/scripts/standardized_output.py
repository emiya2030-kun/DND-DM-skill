#!/usr/bin/env python3
"""
标准化战斗输出系统
生成符合TRPG DM系统规范的标准化格式输出

输出格式（用户指定）:
    **第1矢 攻击骰1d20+7=16 ✅ → 伤害骰1d8+4=12 穿刺 | 缓速 ✅**
    > 第一箭射出——黑色流星贯穿龙翼！
    
    **命中: 1/2 | 总伤害: 12**
"""

import random
import re
from typing import List, Dict, Optional, Tuple


class DiceRoller:
    """骰子投掷器"""
    
    @staticmethod
    def roll(dice_str: str) -> Dict:
        """
        投掷骰子
        
        Args:
            dice_str: "1d20+5", "2d6-1", "1d8"
        
        Returns:
            {"dice": "1d20+5", "rolls": [8], "modifier": 5, "total": 13, "formatted": "1d20+5=8+5=13"}
        """
        match = re.match(r'(\d+)d(\d+)([+-]\d+)?', dice_str.lower().replace(' ', ''))
        if not match:
            raise ValueError(f"无效的骰子表达式: {dice_str}")
        
        num_dice = int(match.group(1))
        die_size = int(match.group(2))
        modifier = int(match.group(3) or 0)
        
        rolls = [random.randint(1, die_size) for _ in range(num_dice)]
        total = sum(rolls) + modifier
        
        # 格式化: 1d20+5=8+5=13 或 2d6=3+5=8
        if num_dice == 1:
            rolls_str = str(rolls[0])
        else:
            rolls_str = '+'.join(str(r) for r in rolls)
        
        if modifier > 0:
            formatted = f"{dice_str}={rolls_str}+{modifier}={total}"
        elif modifier < 0:
            formatted = f"{dice_str}={rolls_str}{modifier}={total}"
        else:
            formatted = f"{dice_str}={rolls_str}={total}"
        
        return {
            "dice": dice_str,
            "rolls": rolls,
            "modifier": modifier,
            "total": total,
            "formatted": formatted
        }
    
    @staticmethod
    def roll_with_crit(dice_str: str, is_crit: bool = False) -> Dict:
        """投掷骰子（暴击时骰子翻倍）"""
        match = re.match(r'(\d+)d(\d+)([+-]\d+)?', dice_str.lower().replace(' ', ''))
        if not match:
            raise ValueError(f"无效的骰子表达式: {dice_str}")
        
        num_dice = int(match.group(1))
        die_size = int(match.group(2))
        modifier = int(match.group(3) or 0)
        
        # 暴击翻倍
        actual_dice = num_dice * 2 if is_crit else num_dice
        rolls = [random.randint(1, die_size) for _ in range(actual_dice)]
        total = sum(rolls) + modifier
        
        if actual_dice == 1:
            rolls_str = str(rolls[0])
        else:
            rolls_str = '+'.join(str(r) for r in rolls)
        
        if modifier > 0:
            formatted = f"{actual_dice}d{die_size}={rolls_str}+{modifier}={total}"
        elif modifier < 0:
            formatted = f"{actual_dice}d{die_size}={rolls_str}{modifier}={total}"
        else:
            formatted = f"{actual_dice}d{die_size}={rolls_str}={total}"
        
        return {
            "dice": dice_str,
            "actual_dice": actual_dice,
            "rolls": rolls,
            "modifier": modifier,
            "total": total,
            "formatted": formatted,
            "is_crit": is_crit
        }


class AttackResult:
    """单次攻击结果"""
    
    def __init__(self, attack_num: int, attack_roll: str, hit: bool, 
                 damage_str: str = "", damage_total: int = 0, is_crit: bool = False):
        self.attack_num = attack_num
        self.attack_roll = attack_roll
        self.hit = hit
        self.damage_str = damage_str
        self.damage_total = damage_total
        self.is_crit = is_crit
        self.rp_text: Optional[str] = None
        self.conditions: List[str] = []  # 附加状态效果
    
    def set_rp(self, text: str) -> 'AttackResult':
        self.rp_text = text
        return self
    
    def add_condition(self, condition: str) -> 'AttackResult':
        self.conditions.append(condition)
        return self
    
    def format_output(self) -> str:
        """格式化输出"""
        # 命中符号
        hit_symbol = "⚡✅" if self.is_crit else ("✅" if self.hit else "❌")
        
        # 条件效果
        cond_str = ""
        if self.conditions:
            cond_str = " | " + " ".join(self.conditions)
        
        # 攻击行
        if self.hit and self.damage_str:
            line1 = f"**第{self.attack_num}击 攻击骰{self.attack_roll} {hit_symbol} → 伤害骰{self.damage_str}{cond_str}**"
        else:
            line1 = f"**第{self.attack_num}击 攻击骰{self.attack_roll} {hit_symbol}**"
        
        # RP行
        if self.rp_text:
            line2 = f"> {self.rp_text}"
            return f"{line1}\n{line2}"
        else:
            return line1


class RoundSummary:
    """回合攻击摘要"""
    
    def __init__(self):
        self.attacks: List[AttackResult] = []
    
    def add_attack(self, attack: AttackResult) -> 'RoundSummary':
        self.attacks.append(attack)
        return self
    
    def format_summary(self) -> str:
        """格式化摘要: **命中: 1/2 | 总伤害: 12**"""
        total_hits = sum(1 for a in self.attacks if a.hit)
        total_damage = sum(a.damage_total for a in self.attacks)
        
        return f"**命中: {total_hits}/{len(self.attacks)} | 总伤害: {total_damage}**"
    
    def format_all(self) -> str:
        """格式化所有输出"""
        lines = []
        for attack in self.attacks:
            lines.append(attack.format_output())
        lines.append("")  # 空行
        lines.append(self.format_summary())
        return "\n".join(lines)


class BattleOutputFormatter:
    """战斗输出格式化器"""
    
    # ========== 攻击输出 ==========
    
    @staticmethod
    def format_attack_simple(
        attack_num: int,
        attack_roll: str,
        hit: bool,
        damage_str: str = "",
        is_crit: bool = False,
        conditions: List[str] = None
    ) -> str:
        """
        格式化单次攻击（简单版）
        
        格式: **第N击 攻击骰X=Y ✅ → 伤害骰...**
        """
        hit_symbol = "⚡✅" if is_crit else ("✅" if hit else "❌")
        cond_str = ""
        if conditions:
            cond_str = " | " + " ".join(conditions)
        
        if hit and damage_str:
            return f"**第{attack_num}击 攻击骰{attack_roll} {hit_symbol} → 伤害骰{damage_str}{cond_str}**"
        else:
            return f"**第{attack_num}击 攻击骰{attack_roll} {hit_symbol}**"
    
    @staticmethod
    def format_attack_with_rp(
        attack_num: int,
        attack_roll: str,
        hit: bool,
        damage_str: str,
        rp_text: str,
        is_crit: bool = False,
        conditions: List[str] = None
    ) -> str:
        """
        格式化单次攻击（带RP）
        
        格式:
            **第N击 攻击骰X=Y ✅ → 伤害骰...**
            > RP描写
        """
        line1 = BattleOutputFormatter.format_attack_simple(
            attack_num, attack_roll, hit, damage_str, is_crit, conditions
        )
        return f"{line1}\n> {rp_text}"
    
    # ========== 回合摘要 ==========
    
    @staticmethod
    def format_round_summary(num_attacks: int, hits: int, total_damage: int) -> str:
        """
        格式化回合摘要
        
        格式: **命中: 1/2 | 总伤害: 12**
        """
        return f"**命中: {hits}/{num_attacks} | 总伤害: {total_damage}**"
    
    # ========== 状态变化 ==========
    
    @staticmethod
    def format_hp_change(name: str, hp_before: int, hp_after: int, max_hp: int) -> str:
        """格式化HP变化"""
        if hp_after <= 0:
            return f"**{name}: HP {hp_before}→{hp_after}/{max_hp} 💀**"
        elif hp_after <= hp_before * 0.25:
            return f"**{name}: HP {hp_before}→{hp_after}/{max_hp} ⚠️**"
        else:
            return f"**{name}: HP {hp_before}→{hp_after}/{max_hp}**"
    
    # ========== 移动 ==========
    
    @staticmethod
    def format_movement(name: str, from_pos: Tuple[int, int], 
                       to_pos: Tuple[int, int], distance: int = None) -> str:
        """格式化移动"""
        dist_str = f" [{distance}尺]" if distance else ""
        return f"**{name} 移动: ({from_pos[0]},{from_pos[1]})→({to_pos[0]},{to_pos[1]}){dist_str}**"
    
    # ========== 回合标题 ==========
    
    @staticmethod
    def format_round_header(round_num: int) -> str:
        return f"【第{round_num}回合】\n========================================"
    
    @staticmethod
    def format_round_end() -> str:
        return "========================================"


class AttackBuilder:
    """攻击构建器 - 用于构建完整的攻击序列"""
    
    def __init__(self, round_num: int):
        self.round_num = round_num
        self.summary = RoundSummary()
        self.formatter = BattleOutputFormatter()
    
    def create_attack(self, attack_num: int, attacker: str, target: str, 
                      target_ac: int, attack_dice: str = "1d20",
                      attack_modifier: int = 0) -> 'AttackBuilder':
        """创建一次攻击"""
        # 投攻击骰
        full_attack_dice = f"{attack_dice}+{attack_modifier}" if attack_modifier else attack_dice
        attack_result = DiceRoller.roll(full_attack_dice)
        attack_roll = attack_result["formatted"]
        hit = attack_result["total"] >= target_ac
        is_crit = attack_result["rolls"][0] == 20
        
        # 存储攻击信息供后续使用
        self._current_attack = {
            "attack_num": attack_num,
            "attack_roll": attack_roll,
            "hit": hit,
            "is_crit": is_crit,
            "damage_parts": [],
            "damage_total": 0,
            "conditions": []
        }
        
        return self
    
    def add_damage(self, dice: str, damage_type: str, modifier: int = 0, 
                   notes: str = "", is_crit: bool = None) -> 'AttackBuilder':
        """添加伤害"""
        if is_crit is None:
            is_crit = self._current_attack["is_crit"]
        
        damage_result = DiceRoller.roll_with_crit(dice, is_crit)
        
        # 格式化伤害字符串
        if modifier:
            full_dice = f"{dice}+{modifier}" if modifier > 0 else f"{dice}{modifier}"
            damage_total = damage_result["total"] + modifier
        else:
            full_dice = damage_result["dice"]
            damage_total = damage_result["total"]
        
        damage_str = f"{damage_result['formatted']}"
        if damage_type:
            damage_str += f" {damage_type}"
        if notes:
            damage_str += f" | {notes}"
        
        self._current_attack["damage_parts"].append(damage_str)
        self._current_attack["damage_total"] += damage_total
        
        return self
    
    def add_condition(self, condition: str) -> 'AttackBuilder':
        """添加状态效果"""
        self._current_attack["conditions"].append(condition)
        return self
    
    def set_rp(self, rp_text: str) -> 'AttackBuilder':
        """设置RP描写"""
        self._current_attack["rp_text"] = rp_text
        return self
    
    def finish_attack(self) -> 'AttackResult':
        """完成当前攻击"""
        attack = AttackResult(
            attack_num=self._current_attack["attack_num"],
            attack_roll=self._current_attack["attack_roll"],
            hit=self._current_attack["hit"],
            damage_str=" + ".join(self._current_attack["damage_parts"]),
            damage_total=self._current_attack["damage_total"],
            is_crit=self._current_attack["is_crit"]
        )
        
        if self._current_attack.get("rp_text"):
            attack.set_rp(self._current_attack["rp_text"])
        
        for cond in self._current_attack["conditions"]:
            attack.add_condition(cond)
        
        self.summary.add_attack(attack)
        return attack
    
    def get_summary(self) -> RoundSummary:
        """获取回合摘要"""
        return self.summary
    
    def format_all(self) -> str:
        """格式化所有输出"""
        return self.summary.format_all()


# ========== 便捷函数 ==========

def quick_attack(attack_num: int, attack_roll: str, hit: bool, 
                 damage_str: str = "", rp_text: str = "", 
                 is_crit: bool = False, conditions: List[str] = None) -> str:
    """快速生成攻击输出"""
    if rp_text:
        return BattleOutputFormatter.format_attack_with_rp(
            attack_num, attack_roll, hit, damage_str, rp_text, is_crit, conditions
        )
    else:
        return BattleOutputFormatter.format_attack_simple(
            attack_num, attack_roll, hit, damage_str, is_crit, conditions
        )


def quick_summary(num_attacks: int, hits: int, total_damage: int) -> str:
    """快速生成摘要"""
    return BattleOutputFormatter.format_round_summary(num_attacks, hits, total_damage)
