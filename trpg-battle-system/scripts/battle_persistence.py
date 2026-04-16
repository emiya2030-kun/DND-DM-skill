#!/usr/bin/env python3
"""
战斗持久化管理器
整合 combat_manager.py 和 event_logger.py

使用方式:
    from battle_persistence import BattlePersistenceManager
    
    persistence = BattlePersistenceManager("wraith_fight_001")
    persistence.init_battle(width=10, height=10)
    persistence.combat.add_unit("奎利昂", x=3, y=3, hp=44, max_hp=44, ac=16)
    persistence.log_attack(...)
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

# 添加脚本目录到路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)


class BattlePersistenceManager:
    """战斗持久化管理器"""
    
    def __init__(self, battle_id: str, base_dir: str = "/tmp/trpg_battles"):
        """
        初始化持久化管理器
        
        Args:
            battle_id: 战斗唯一标识符
            base_dir: 数据存储根目录
        """
        self.battle_id = battle_id
        self.base_dir = os.path.join(base_dir, battle_id)
        self.state_file = os.path.join(self.base_dir, "current_state.json")
        self.rounds_dir = os.path.join(self.base_dir, "rounds")
        
        # 延迟导入，避免循环依赖
        from combat_manager import CombatManager
        from event_logger import BattleEventLogger
        
        self.combat = CombatManager(self.state_file)
        self.logger = BattleEventLogger(battle_id, base_dir)
        
        os.makedirs(self.rounds_dir, exist_ok=True)
    
    # ========== 初始化 ==========
    
    def init_battle(self, width: int = 12, height: int = 12) -> str:
        """
        初始化新战斗
        
        Args:
            width: 地图宽度
            height: 地图高度
        
        Returns:
            状态消息
        """
        self.combat.init_combat(self.battle_id, width, height)
        return f"战斗已初始化: {self.battle_id}"
    
    # ========== 事件记录 ==========
    
    def log_attack(self, round_num: int, turn: str, actor: str, target: str,
                   action: str, damage: str, damage_total: int,
                   target_hp_before: int, target_hp_after: int,
                   spell_slot_used: Optional[int] = None) -> str:
        """
        记录攻击事件
        
        Args:
            round_num: 回合数
            turn: 当前行动角色
            actor: 攻击者
            target: 目标
            action: 攻击动作名称
            damage: 伤害详情 (如 "1d6+4=7穿刺 + 2d6=6力场")
            damage_total: 总伤害
            target_hp_before: 目标受伤前HP
            target_hp_after: 目标受伤后HP
            spell_slot_used: 消耗的法术位 (可选)
        
        Returns:
            event_id: 事件ID
        """
        event = {
            "event": "attack",
            "round": round_num,
            "turn": turn,
            "actor": actor,
            "target": target,
            "action": action,
            "damage": damage,
            "damage_total": damage_total,
            "target_hp_change": f"{target_hp_before}→{target_hp_after}"
        }
        
        if spell_slot_used:
            event["spell_slot_used"] = spell_slot_used
        
        return self.logger.log_event(event)
    
    def log_move(self, round_num: int, turn: str, actor: str,
                 from_pos: tuple, to_pos: tuple) -> str:
        """
        记录移动事件
        
        Args:
            round_num: 回合数
            turn: 当前行动角色
            actor: 移动者
            from_pos: 起始坐标 (x, y)
            to_pos: 目标坐标 (x, y)
        
        Returns:
            event_id: 事件ID
        """
        event = {
            "event": "move",
            "round": round_num,
            "turn": turn,
            "actor": actor,
            "movement": f"({from_pos[0]},{from_pos[1]})→({to_pos[0]},{to_pos[1]})"
        }
        return self.logger.log_event(event)
    
    def log_spell(self, round_num: int, turn: str, actor: str,
                  spell_name: str, target: Optional[str] = None,
                  spell_slot: Optional[int] = None,
                  notes: Optional[str] = None) -> str:
        """
        记录施法事件
        
        Args:
            round_num: 回合数
            turn: 当前行动角色
            actor: 施法者
            spell_name: 法术名称
            target: 目标 (可选)
            spell_slot: 法术位环数 (可选)
            notes: 备注 (可选)
        
        Returns:
            event_id: 事件ID
        """
        event = {
            "event": "cast_spell",
            "round": round_num,
            "turn": turn,
            "actor": actor,
            "action": spell_name
        }
        
        if target:
            event["target"] = target
        if spell_slot:
            event["spell_slot_used"] = spell_slot
        if notes:
            event["notes"] = notes
        
        return self.logger.log_event(event)
    
    def log_status_change(self, round_num: int, turn: str, actor: str,
                          notes: str) -> str:
        """
        记录状态变化事件
        
        Args:
            round_num: 回合数
            turn: 当前行动角色
            actor: 角色
            notes: 状态变化描述
        
        Returns:
            event_id: 事件ID
        """
        event = {
            "event": "status_change",
            "round": round_num,
            "turn": turn,
            "actor": actor,
            "notes": notes
        }
        return self.logger.log_event(event)
    
    def log_use_item(self, round_num: int, turn: str, actor: str,
                     item_name: str, target: Optional[str] = None,
                     notes: Optional[str] = None) -> str:
        """
        记录使用物品事件
        
        Args:
            round_num: 回合数
            turn: 当前行动角色
            actor: 使用者
            item_name: 物品名称
            target: 目标 (可选)
            notes: 备注 (可选)
        
        Returns:
            event_id: 事件ID
        """
        event = {
            "event": "use_item",
            "round": round_num,
            "turn": turn,
            "actor": actor,
            "action": item_name
        }
        
        if target:
            event["target"] = target
        if notes:
            event["notes"] = notes
        
        return self.logger.log_event(event)
    
    # ========== 回合管理 ==========
    
    def save_round_snapshot(self, round_num: int) -> str:
        """
        保存回合快照 (回合结束时调用)
        
        Args:
            round_num: 回合数
        
        Returns:
            快照文件路径
        """
        snapshot_file = os.path.join(self.rounds_dir, f"round_{round_num}.json")
        
        # 深拷贝当前状态
        state = json.loads(json.dumps(self.combat.state))
        
        # 添加回合元数据
        state["snapshot_round"] = round_num
        state["snapshot_time"] = datetime.now().isoformat()
        
        with open(snapshot_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        
        return snapshot_file
    
    def get_round_snapshot(self, round_num: int) -> Optional[Dict]:
        """
        获取回合快照
        
        Args:
            round_num: 回合数
        
        Returns:
            快照数据，不存在则返回None
        """
        snapshot_file = os.path.join(self.rounds_dir, f"round_{round_num}.json")
        
        if os.path.exists(snapshot_file):
            with open(snapshot_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return None
    
    # ========== 查询接口 ==========
    
    def get_current_state(self) -> Dict:
        """
        获取当前战斗状态
        
        Returns:
            当前战斗状态字典
        """
        return self.combat.state
    
    def get_round_events(self, round_num: int) -> List[Dict]:
        """
        获取指定回合的事件列表
        
        Args:
            round_num: 回合数
        
        Returns:
            事件列表
        """
        return self.logger.get_round_events(round_num)
    
    def get_round_summary(self, round_num: int) -> str:
        """
        获取格式化的回合摘要
        
        Args:
            round_num: 回合数
        
        Returns:
            格式化的回合摘要
        """
        return self.logger.format_round_summary(round_num)
    
    def get_last_round_summary(self) -> str:
        """
        获取上回合摘要
        
        Returns:
            上回合摘要文本
        """
        current_round = self.combat.state.get("round", 1)
        if current_round > 1:
            return self.get_round_summary(current_round - 1)
        return "【第0回合】无事件记录"
    
    # ========== 战斗结束 ==========
    
    def finalize_battle(self, result: str, summary_text: str,
                        key_moments: Optional[List[str]] = None) -> Dict:
        """
        战斗结束处理
        
        Args:
            result: 战斗结果 (如 "奎利昂胜利")
            summary_text: 战斗摘要文本
            key_moments: 关键时刻列表 (可选)
        
        Returns:
            包含总结信息的字典
        """
        # 计算总回合数
        rounds = self.combat.state.get("round", 1)
        
        summary = {
            "result": result,
            "rounds": rounds,
            "summary": summary_text,
            "key_moments": key_moments or [],
            "participants": list(self.combat.state.get("units", {}).keys())
        }
        
        summary_file = self.logger.finalize_battle(summary)
        
        return {
            "summary_file": summary_file,
            "rounds": rounds,
            "participants": summary["participants"]
        }
