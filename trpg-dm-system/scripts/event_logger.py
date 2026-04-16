#!/usr/bin/env python3
"""
战斗事件日志系统
记录每轮战斗事件，支持即时状态查询和回合回放

使用方式:
    from event_logger import BattleEventLogger
    
    logger = BattleEventLogger("wraith_fight_001")
    logger.log_event({
        "event": "attack",
        "round": 1,
        "turn": "奎利昂",
        "actor": "奎利昂",
        "target": "幽魂",
        "action": "投影武器攻击",
        "damage": "1d6+4=7穿刺 + 2d6=6力场",
        "damage_total": 13,
        "target_hp_change": "67→54"
    })
"""

import json
import os
import random
from datetime import datetime
from typing import List, Dict, Optional


class BattleEventLogger:
    """战斗事件记录器"""
    
    def __init__(self, battle_id: str, base_dir: str = "/tmp/trpg_battles"):
        """
        初始化事件记录器
        
        Args:
            battle_id: 战斗唯一标识符
            base_dir: 数据存储根目录
        """
        self.battle_id = battle_id
        self.base_dir = os.path.join(base_dir, battle_id)
        self.events_file = os.path.join(self.base_dir, "events.jsonl")
        self._ensure_dir()
    
    def _ensure_dir(self):
        """确保目录存在"""
        os.makedirs(self.base_dir, exist_ok=True)
    
    # ========== 事件记录 ==========
    
    def log_event(self, event: Dict) -> str:
        """
        记录单个事件到日志
        
        Args:
            event: 事件字典，必须包含以下字段:
                - event: 事件类型 (attack/move/cast_spell/status_change)
                - round: 回合数
                - turn: 当前行动角色
                - actor: 事件执行者
                
                可选字段:
                - target: 目标
                - action: 动作描述
                - damage: 伤害详情
                - damage_total: 总伤害
                - target_hp_change: 目标HP变化 (如 "67→54")
                - spell_slot_used: 消耗的法术位
                - movement: 移动路径
                - notes: 备注
        
        Returns:
            event_id: 事件唯一标识符
        """
        event["timestamp"] = datetime.now().isoformat()
        event["event_id"] = self._generate_event_id()
        
        with open(self.events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        
        return event["event_id"]
    
    def _generate_event_id(self) -> str:
        """生成事件ID"""
        return f"evt_{random.randint(1000, 9999)}"
    
    # ========== 回合回放 ==========
    
    def get_round_events(self, round_num: int) -> List[Dict]:
        """
        获取指定回合的所有事件
        
        Args:
            round_num: 回合数
        
        Returns:
            该回合的所有事件列表
        """
        events = []
        
        if not os.path.exists(self.events_file):
            return events
        
        with open(self.events_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    event = json.loads(line)
                    if event.get("round") == round_num:
                        events.append(event)
        
        return events
    
    def get_last_round_events(self, current_round: int) -> List[Dict]:
        """
        获取上回合事件
        
        Args:
            current_round: 当前回合数
        
        Returns:
            上回合的所有事件列表
        """
        return self.get_round_events(current_round - 1)
    
    def format_round_summary(self, round_num: int) -> str:
        """
        格式化回合摘要
        
        Args:
            round_num: 回合数
        
        Returns:
            格式化的回合摘要文本
        """
        events = self.get_round_events(round_num)
        
        if not events:
            return f"【第{round_num}回合】无事件记录"
        
        lines = [f"【第{round_num}回合】", "=" * 40]
        
        for event in events:
            line = self._format_single_event(event)
            lines.append(line)
        
        lines.append("=" * 40)
        return "\n".join(lines)
    
    def _format_single_event(self, event: Dict) -> str:
        """格式化单个事件"""
        event_type = event.get("event", "unknown")
        actor = event.get("actor", "未知")
        target = event.get("target", "")
        action = event.get("action", "")
        
        if event_type == "attack":
            damage = event.get("damage", "")
            hp_change = event.get("target_hp_change", "")
            target_str = f"→{target}" if target else ""
            return f"• {actor}{target_str}: {action} | {damage} | HP{hp_change}"
        
        elif event_type == "move":
            movement = event.get("movement", "")
            return f"• {actor} 移动: {movement}"
        
        elif event_type == "cast_spell":
            spell = action
            slot = event.get("spell_slot_used", "")
            target_str = f"→{target}" if target else ""
            slot_str = f" | 消耗{slot}环法术位" if slot else ""
            return f"• {actor} 施法: {spell}{target_str}{slot_str}"
        
        elif event_type == "status_change":
            notes = event.get("notes", "")
            return f"• {actor}: {notes}"
        
        elif event_type == "use_item":
            return f"• {actor} 使用物品: {action}"
        
        else:
            return f"• {actor}: {action or event_type}"
    
    # ========== 战斗结束 ==========
    
    def finalize_battle(self, summary: Dict) -> str:
        """
        战斗结束：生成总结，清理事件日志
        
        Args:
            summary: 战斗总结字典
                - result: 战斗结果
                - rounds: 总回合数
                - summary: 战斗摘要文本
                - key_moments: 关键时刻列表
        
        Returns:
            summary_file: 总结文件路径
        """
        # 1. 生成总结文件
        summary_file = os.path.join(self.base_dir, "battle_summary.json")
        summary["battle_id"] = self.battle_id
        summary["date"] = datetime.now().isoformat()
        
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        # 2. 删除事件日志
        if os.path.exists(self.events_file):
            os.remove(self.events_file)
        
        return summary_file
    
    # ========== 状态查询 ==========
    
    def get_all_events(self) -> List[Dict]:
        """获取当前战斗所有事件"""
        events = []
        
        if not os.path.exists(self.events_file):
            return events
        
        with open(self.events_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
        
        return events
    
    def event_exists(self) -> bool:
        """检查事件日志文件是否存在"""
        return os.path.exists(self.events_file)
