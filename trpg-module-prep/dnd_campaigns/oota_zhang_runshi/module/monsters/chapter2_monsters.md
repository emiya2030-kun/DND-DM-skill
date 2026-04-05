# 《逃出深渊》第二章 - 怪物手册

> 包含第二章所有可能遭遇的怪物数据和战斗行动逻辑
> 基于D&D 5e SRD数据 + 战术建议

---

## 目录

- [Bandit](#bandit)
- [Bandit Captain](#bandit-captain)
- [Black Pudding](#black-pudding)
- [Chuul](#chuul)
- [Commoner](#commoner)
- [Darkmantle](#darkmantle)
- [Dretch](#dretch)
- [Drow](#drow)
- [Gelatinous Cube](#gelatinous-cube)
- [Giant Fire Beetle](#giant-fire-beetle)
- [Giant Octopus](#giant-octopus)
- [Giant Spider](#giant-spider)
- [Gnoll](#gnoll)
- [Goblin](#goblin)
- [Gray Ooze](#gray-ooze)
- [Grick](#grick)
- [Mimic](#mimic)
- [Minotaur Skeleton](#minotaur-skeleton)
- [Ochre Jelly](#ochre-jelly)
- [Orc](#orc)
- [Scout](#scout)
- [Shrieker](#shrieker)
- [Skeleton](#skeleton)
- [Specter](#specter)
- [Violet Fungus](#violet-fungus)
- [Wraith](#wraith)

---

## Bandit

**类型**: Medium humanoid, any non-lawful alignment
**CR**: 0.125 (25 XP)

**AC**: 12 (armor)
**HP**: 11 (2d8)
**速度**: 30 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 11(+0) | 12(+1) | 12(+1) | 10(+0) | 10(+0) | 10(+0) |

**感官**: passive_perception 10
**语言**: any one language (usually Common)

### 动作

**Scimitar**: Melee Weapon Attack: +3 to hit, reach 5 ft., one target. Hit: 4 (1d6 + 1) slashing damage.

**Light Crossbow**: Ranged Weapon Attack: +3 to hit, range 80 ft./320 ft., one target. Hit: 5 (1d8 + 1) piercing damage.

### 战斗行动逻辑

**战术模式**: 人形生物 - 战术协作

- **编队行动**: 2-3人一组配合
- **优先目标**: 施法者 > 远程 > 近战
- **行动模式**:
  1. 远程攻击者保持距离
  2. 近战者围攻单一目标
  3. 领导者指挥集火
- **撤退条件**: 死亡过半或领导者倒下

---

## Bandit Captain

**类型**: Medium humanoid, any non-lawful alignment
**CR**: 2 (450 XP)

**AC**: 15 (armor)
**HP**: 65 (10d8)
**速度**: 30 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 15(+2) | 16(+3) | 14(+2) | 14(+2) | 11(+0) | 14(+2) |

**感官**: passive_perception 10
**语言**: any two languages

### 动作

**Multiattack**: The captain makes three melee attacks: two with its scimitar and one with its dagger. Or the captain makes two ranged attacks with its daggers.

**Scimitar**: Melee Weapon Attack: +5 to hit, reach 5 ft., one target. Hit: 6 (1d6 + 3) slashing damage.

**Dagger**: Melee or Ranged Weapon Attack: +5 to hit, reach 5 ft. or range 20/60 ft., one target. Hit: 5 (1d4 + 3) piercing damage.

### 战斗行动逻辑

**战术模式**: 通用战斗

- **优先目标**: 对自己威胁最大的敌人
- **行动模式**: 使用最有效的攻击方式
- **撤退条件**: 生命值低于25%时考虑逃跑

---

## Black Pudding

**类型**: Large ooze, unaligned
**CR**: 4 (1100 XP)

**AC**: 7 (dex)
**HP**: 85 (10d10)
**速度**: 20 ft. 尺, climb 20 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 16(+3) | 5(-3) | 16(+3) | 1(-5) | 6(-2) | 1(-5) |

**伤害免疫**: acid, cold, lightning, slashing
**状态免疫**: Blinded, Charmed, Exhaustion, Frightened, Prone
**感官**: blindsight 60 ft. (blind beyond this radius), passive_perception 8
**语言**: 

### 特殊能力

**Amorphous**: The pudding can move through a space as narrow as 1 inch wide without squeezing.

**Corrosive Form**: A creature that touches the pudding or hits it with a melee attack while within 5 feet of it takes 4 (1d8) acid damage. Any nonmagical weapon made of metal or wood that hits the pudding corrodes. After dealing damage, the weapon takes a permanent and cumulative -1 penalty to damage rolls. If its penalty drops to -5, the weapon is destroyed. Nonmagical ammunition made of metal or wood that hits the pudding is destroyed after dealing damage. The pudding can eat through 2-inch-thick, nonmagical wood or metal in 1 round.

**Spider Climb**: The pudding can climb difficult surfaces, including upside down on ceilings, without needing to make an ability check.

### 动作

**Pseudopod**: Melee Weapon Attack: +5 to hit, reach 5 ft., one target. Hit: 6 (1d6 + 3) bludgeoning damage plus 18 (4d8) acid damage. In addition, nonmagical armor worn by the target is partly dissolved and takes a permanent and cumulative -1 penalty to the AC it offers. The armor is destroyed if the penalty reduces its AC to 10.

### 战斗行动逻辑

**战术模式**: 泥怪 - 缓慢吞噬

- **行动模式**: 向最近生物移动并吞噬
- **特殊行为**:
  - 对武器攻击有分裂/腐蚀效果
  - 胶质方块：吸收路径上的一切
- **撤退条件**: 不会撤退

---

## Chuul

**类型**: Large aberration, chaotic evil
**CR**: 4 (1100 XP)

**AC**: 16 (natural)
**HP**: 93 (11d10)
**速度**: 30 ft. 尺, swim 30 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 19(+4) | 10(+0) | 16(+3) | 5(-3) | 11(+0) | 5(-3) |

**伤害免疫**: poison
**状态免疫**: Poisoned
**感官**: darkvision 60 ft., passive_perception 14
**语言**: understands Deep Speech but can't speak

### 特殊能力

**Amphibious**: The chuul can breathe air and water.

**Sense Magic**: The chuul senses magic within 120 feet of it at will. This trait otherwise works like the detect magic spell but isn't itself magical.

### 动作

**Multiattack**: The chuul makes two pincer attacks. If the chuul is grappling a creature, the chuul can also use its tentacles once.

**Pincer**: Melee Weapon Attack: +6 to hit, reach 10 ft., one target. Hit: 11 (2d6 + 4) bludgeoning damage. The target is grappled (escape DC 14) if it is a Large or smaller creature and the chuul doesn't have two other creatures grappled.

**Tentacles**: One creature grappled by the chuul must succeed on a DC 13 Constitution saving throw or be poisoned for 1 minute. Until this poison ends, the target is paralyzed. The target can repeat the saving throw at the end of each of its turns, ending the effect on itself on a success.

### 战斗行动逻辑

**战术模式**: 水生猎手 - 擒抱拖拽

- **伏击策略**: 水中/潮湿区域等待
- **优先目标**: 靠近水源的敌人
- **行动模式**:
  1. 擒抱目标
  2. 拖入水中
  3. 使用麻痹触须
- **撤退条件**: 陆地上受伤严重时退回水中

---

## Commoner

**类型**: Medium humanoid, any alignment
**CR**: 0 (10 XP)

**AC**: 10 (dex)
**HP**: 4 (1d8)
**速度**: 30 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 10(+0) | 10(+0) | 10(+0) | 10(+0) | 10(+0) | 10(+0) |

**感官**: passive_perception 10
**语言**: any one language (usually Common)

### 动作

**Club**: Melee Weapon Attack: +2 to hit, reach 5 ft., one target. Hit: 2 (1d4) bludgeoning damage.

### 战斗行动逻辑

**战术模式**: 通用战斗

- **优先目标**: 对自己威胁最大的敌人
- **行动模式**: 使用最有效的攻击方式
- **撤退条件**: 生命值低于25%时考虑逃跑

---

## Darkmantle

**类型**: Small monstrosity, unaligned
**CR**: 0.5 (100 XP)

**AC**: 11 (dex)
**HP**: 22 (5d6)
**速度**: 10 ft. 尺, fly 30 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 16(+3) | 12(+1) | 13(+1) | 2(-4) | 10(+0) | 5(-3) |

**感官**: blindsight 60 ft., passive_perception 10
**语言**: 

### 特殊能力

**Echolocation**: The darkmantle can't use its blindsight while deafened.

**False Appearance**: While the darkmantle remains motionless, it is indistinguishable from a cave formation such as a stalactite or stalagmite.

### 动作

**Crush**: Melee Weapon Attack: +5 to hit, reach 5 ft., one creature. Hit: 6 (1d6 + 3) bludgeoning damage, and the darkmantle attaches to the target. If the target is Medium or smaller and the darkmantle has advantage on the attack roll, it attaches by engulfing the target's head, and the target is also blinded and unable to breathe while the darkmantle is attached in this way.
While attached to the target, the darkmantle can attack no other creature except the target but has advantage on its attack rolls. The darkmantle's speed also becomes 0, it can't benefit from any bonus to its speed, and it moves with the target.
A creature can detach the darkmantle by making a successful DC 13 Strength check as an action. On its turn, the darkmantle can detach itself from the target by using 5 feet of movement.

**Darkness Aura**: A 15-foot radius of magical darkness extends out from the darkmantle, moves with it, and spreads around corners. The darkness lasts as long as the darkmantle maintains concentration, up to 10 minutes (as if concentrating on a spell). Darkvision can't penetrate this darkness, and no natural light can illuminate it. If any of the darkness overlaps with an area of light created by a spell of 2nd level or lower, the spell creating the light is dispelled.

### 战斗行动逻辑

**战术模式**: 伏击猎手 - 潜伏突袭

- **伏击策略**: 在天花板/阴影中等待
- **优先目标**: 落单的后排角色
- **行动模式**:
  1. 第一轮：突袭 + 擒抱/麻痹
  2. 拖走猎物到巢穴
- **撤退条件**: 受到严重伤害时逃跑

---

## Dretch

**类型**: Small fiend, chaotic evil
**CR**: 0.25 (25 XP)

**AC**: 11 (natural)
**HP**: 18 (4d6)
**速度**: 20 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 11(+0) | 11(+0) | 12(+1) | 5(-3) | 8(-1) | 3(-4) |

**伤害抗性**: cold, fire, lightning
**伤害免疫**: poison
**状态免疫**: Poisoned
**感官**: darkvision 60 ft., passive_perception 9
**语言**: Abyssal, telepathy 60 ft. (works only with creatures that understand Abyssal)

### 动作

**Multiattack**: The dretch makes two attacks: one with its bite and one with its claws.

**Bite**: Melee Weapon Attack: +2 to hit, reach 5 ft., one target. Hit: 3 (1d6) piercing damage.

**Claws**: Melee Weapon Attack: +2 to hit, reach 5 ft., one target. Hit: 5 (2d4) slashing damage.

**Fetid Cloud**: A 10-foot radius of disgusting green gas extends out from the dretch. The gas spreads around corners, and its area is lightly obscured. It lasts for 1 minute or until a strong wind disperses it. Any creature that starts its turn in that area must succeed on a DC 11 Constitution saving throw or be poisoned until the start of its next turn. While poisoned in this way, the target can take either an action or a bonus action on its turn, not both, and can't take reactions.

### 战斗行动逻辑

**战术模式**: 通用战斗

- **优先目标**: 对自己威胁最大的敌人
- **行动模式**: 使用最有效的攻击方式
- **撤退条件**: 生命值低于25%时考虑逃跑

---

## Drow

**类型**: Medium humanoid, neutral evil
**CR**: 0.25 (50 XP)

**AC**: 15 (armor)
**HP**: 13 (3d8)
**速度**: 30 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 10(+0) | 14(+2) | 10(+0) | 11(+0) | 11(+0) | 12(+1) |

**感官**: darkvision 120 ft., passive_perception 12
**语言**: Elvish, Undercommon

### 特殊能力

**Fey Ancestry**: The drow has advantage on saving throws against being charmed, and magic can't put the drow to sleep.

**Innate Spellcasting**: The drow's spellcasting ability is Charisma (spell save DC 11). It can innately cast the following spells, requiring no material components:
At will: dancing lights
1/day each: darkness, faerie fire

**Sunlight Sensitivity**: While in sunlight, the drow has disadvantage on attack rolls, as well as on Wisdom (Perception) checks that rely on sight.

### 动作

**Shortsword**: Melee Weapon Attack: +4 to hit, reach 5 ft., one target. Hit: 5 (1d6 + 2) piercing damage.

**Hand Crossbow**: Ranged Weapon Attack: +4 to hit, range 30/120 ft., one target. Hit: 5 (1d6 + 2) piercing damage, and the target must succeed on a DC 13 Constitution saving throw or be poisoned for 1 hour. If the saving throw fails by 5 or more, the target is also unconscious while poisoned in this way. The target wakes up if it takes damage or if another creature takes an action to shake it awake.

### 战斗行动逻辑

**战术模式**: 通用战斗

- **优先目标**: 对自己威胁最大的敌人
- **行动模式**: 使用最有效的攻击方式
- **撤退条件**: 生命值低于25%时考虑逃跑

---

## Gelatinous Cube

**类型**: Large ooze, unaligned
**CR**: 2 (450 XP)

**AC**: 6 (dex)
**HP**: 84 (8d10)
**速度**: 15 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 14(+2) | 3(-4) | 20(+5) | 1(-5) | 6(-2) | 1(-5) |

**状态免疫**: Blinded, Charmed, Deafened, Exhaustion, Frightened, Prone
**感官**: blindsight 60 ft. (blind beyond this radius), passive_perception 8
**语言**: 

### 特殊能力

**Ooze Cube**: The cube takes up its entire space. Other creatures can enter the space, but a creature that does so is subjected to the cube's Engulf and has disadvantage on the saving throw.
Creatures inside the cube can be seen but have total cover.
A creature within 5 feet of the cube can take an action to pull a creature or object out of the cube. Doing so requires a successful DC 12 Strength check, and the creature making the attempt takes 10 (3d6) acid damage.
The cube can hold only one Large creature or up to four Medium or smaller creatures inside it at a time.

**Transparent**: Even when the cube is in plain sight, it takes a successful DC 15 Wisdom (Perception) check to spot a cube that has neither moved nor attacked. A creature that tries to enter the cube's space while unaware of the cube is surprised by the cube.

### 动作

**Pseudopod**: Melee Weapon Attack: +4 to hit, reach 5 ft., one creature. Hit: 10 (3d6) acid damage.

**Engulf**: The cube moves up to its speed. While doing so, it can enter Large or smaller creatures' spaces. Whenever the cube enters a creature's space, the creature must make a DC 12 Dexterity saving throw.
On a successful save, the creature can choose to be pushed 5 feet back or to the side of the cube. A creature that chooses not to be pushed suffers the consequences of a failed saving throw.
On a failed save, the cube enters the creature's space, and the creature takes 10 (3d6) acid damage and is engulfed. The engulfed creature can't breathe, is restrained, and takes 21 (6d6) acid damage at the start of each of the cube's turns. When the cube moves, the engulfed creature moves with it.
An engulfed creature can try to escape by taking an action to make a DC 12 Strength check. On a success, the creature escapes and enters a space of its choice within 5 feet of the cube.

### 战斗行动逻辑

**战术模式**: 泥怪 - 缓慢吞噬

- **行动模式**: 向最近生物移动并吞噬
- **特殊行为**:
  - 对武器攻击有分裂/腐蚀效果
  - 胶质方块：吸收路径上的一切
- **撤退条件**: 不会撤退

---

## Giant Fire Beetle

**类型**: Small beast, unaligned
**CR**: 0 (10 XP)

**AC**: 13 (natural)
**HP**: 4 (1d6)
**速度**: 30 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 8(-1) | 10(+0) | 12(+1) | 1(-5) | 7(-2) | 3(-4) |

**感官**: blindsight 30 ft., passive_perception 8
**语言**: 

### 特殊能力

**Illumination**: The beetle sheds bright light in a 10-foot radius and dim light for an additional 10 ft..

### 动作

**Bite**: Melee Weapon Attack: +1 to hit, reach 5 ft., one target. Hit: 2 (1d6 - 1) slashing damage.

### 战斗行动逻辑

**战术模式**: 通用战斗

- **优先目标**: 对自己威胁最大的敌人
- **行动模式**: 使用最有效的攻击方式
- **撤退条件**: 生命值低于25%时考虑逃跑

---

## Giant Octopus

**类型**: Large beast, unaligned
**CR**: 1 (200 XP)

**AC**: 11 (dex)
**HP**: 52 (8d10)
**速度**: 10 ft. 尺, swim 60 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 17(+3) | 13(+1) | 13(+1) | 4(-3) | 10(+0) | 4(-3) |

**感官**: darkvision 60 ft., passive_perception 14
**语言**: 

### 特殊能力

**Hold Breath**: While out of water, the octopus can hold its breath for 1 hour.

**Underwater Camouflage**: The octopus has advantage on Dexterity (Stealth) checks made while underwater.

**Water Breathing**: The octopus can breathe only underwater.

### 动作

**Tentacles**: Melee Weapon Attack: +5 to hit, reach 15 ft., one target. Hit: 10 (2d6 + 3) bludgeoning damage. If the target is a creature, it is grappled (escape DC 16). Until this grapple ends, the target is restrained, and the octopus can't use its tentacles on another target.

**Ink Cloud**: A 20-foot-radius cloud of ink extends all around the octopus if it is underwater. The area is heavily obscured for 1 minute, although a significant current can disperse the ink. After releasing the ink, the octopus can use the Dash action as a bonus action.

### 战斗行动逻辑

**战术模式**: 水生猎手 - 擒抱拖拽

- **伏击策略**: 水中/潮湿区域等待
- **优先目标**: 靠近水源的敌人
- **行动模式**:
  1. 擒抱目标
  2. 拖入水中
  3. 使用麻痹触须
- **撤退条件**: 陆地上受伤严重时退回水中

---

## Giant Spider

**类型**: Large beast, unaligned
**CR**: 1 (200 XP)

**AC**: 14 (natural)
**HP**: 26 (4d10)
**速度**: 30 ft. 尺, climb 30 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 14(+2) | 16(+3) | 12(+1) | 2(-4) | 11(+0) | 4(-3) |

**感官**: blindsight 10 ft., darkvision 60 ft., passive_perception 10
**语言**: 

### 特殊能力

**Spider Climb**: The spider can climb difficult surfaces, including upside down on ceilings, without needing to make an ability check.

**Web Sense**: While in contact with a web, the spider knows the exact location of any other creature in contact with the same web.

**Web Walker**: The spider ignores movement restrictions caused by webbing.

### 动作

**Bite**: Melee Weapon Attack: +5 to hit, reach 5 ft., one creature. Hit: 7 (1d8 + 3) piercing damage, and the target must make a DC 11 Constitution saving throw, taking 9 (2d8) poison damage on a failed save, or half as much damage on a successful one. If the poison damage reduces the target to 0 hit points, the target is stable but poisoned for 1 hour, even after regaining hit points, and is paralyzed while poisoned in this way.

**Web**: Ranged Weapon Attack: +5 to hit, range 30/60 ft., one creature. Hit: The target is restrained by webbing. As an action, the restrained target can make a DC 12 Strength check, bursting the webbing on a success. The webbing can also be attacked and destroyed (AC 10; hp 5; vulnerability to fire damage; immunity to bludgeoning, poison, and psychic damage).

### 战斗行动逻辑

**战术模式**: 伏击猎手 - 潜伏突袭

- **伏击策略**: 在天花板/阴影中等待
- **优先目标**: 落单的后排角色
- **行动模式**:
  1. 第一轮：突袭 + 擒抱/麻痹
  2. 拖走猎物到巢穴
- **撤退条件**: 受到严重伤害时逃跑

---

## Gnoll

**类型**: Medium humanoid, chaotic evil
**CR**: 0.5 (100 XP)

**AC**: 15 (armor)
**HP**: 22 (5d8)
**速度**: 30 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 14(+2) | 12(+1) | 11(+0) | 6(-2) | 10(+0) | 7(-2) |

**感官**: darkvision 60 ft., passive_perception 10
**语言**: Gnoll

### 特殊能力

**Rampage**: When the gnoll reduces a creature to 0 hit points with a melee attack on its turn, the gnoll can take a bonus action to move up to half its speed and make a bite attack.

### 动作

**Bite**: Melee Weapon Attack: +4 to hit, reach 5 ft., one creature. Hit: 4 (1d4 + 2) piercing damage.

**Spear**: Melee or Ranged Weapon Attack: +4 to hit, reach 5 ft. or range 20/60 ft., one target. Hit: 5 (1d6 + 2) piercing damage, or 6 (1d8 + 2) piercing damage if used with two hands to make a melee attack.

**Longbow**: Ranged Weapon Attack: +3 to hit, range 150/600 ft., one target. Hit: 5 (1d8 + 1) piercing damage.

### 战斗行动逻辑

**战术模式**: 人形生物 - 战术协作

- **编队行动**: 2-3人一组配合
- **优先目标**: 施法者 > 远程 > 近战
- **行动模式**:
  1. 远程攻击者保持距离
  2. 近战者围攻单一目标
  3. 领导者指挥集火
- **撤退条件**: 死亡过半或领导者倒下

---

## Goblin

**类型**: Small humanoid, neutral evil
**CR**: 0.25 (50 XP)

**AC**: 15 (armor)
**HP**: 7 (2d6)
**速度**: 30 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 8(-1) | 14(+2) | 10(+0) | 10(+0) | 8(-1) | 8(-1) |

**感官**: darkvision 60 ft., passive_perception 9
**语言**: Common, Goblin

### 特殊能力

**Nimble Escape**: The goblin can take the Disengage or Hide action as a bonus action on each of its turns.

### 动作

**Scimitar**: Melee Weapon Attack: +4 to hit, reach 5 ft., one target. Hit: 5 (1d6 + 2) slashing damage.

**Shortbow**: Ranged Weapon Attack: +4 to hit, range 80/320 ft., one target. Hit: 5 (1d6 + 2) piercing damage.

### 战斗行动逻辑

**战术模式**: 人形生物 - 战术协作

- **编队行动**: 2-3人一组配合
- **优先目标**: 施法者 > 远程 > 近战
- **行动模式**:
  1. 远程攻击者保持距离
  2. 近战者围攻单一目标
  3. 领导者指挥集火
- **撤退条件**: 死亡过半或领导者倒下

---

## Gray Ooze

**类型**: Medium ooze, unaligned
**CR**: 0.5 (100 XP)

**AC**: 8 (dex)
**HP**: 22 (3d8)
**速度**: 10 ft. 尺, climb 10 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 12(+1) | 6(-2) | 16(+3) | 1(-5) | 6(-2) | 2(-4) |

**伤害抗性**: acid, cold, fire
**状态免疫**: Blinded, Charmed, Deafened, Exhaustion, Frightened, Prone
**感官**: blindsight 60 ft. (blind beyond this radius), passive_perception 8
**语言**: 

### 特殊能力

**Amorphous**: The ooze can move through a space as narrow as 1 inch wide without squeezing.

**Corrode Metal**: Any nonmagical weapon made of metal that hits the ooze corrodes. After dealing damage, the weapon takes a permanent and cumulative -1 penalty to damage rolls. If its penalty drops to -5, the weapon is destroyed. Nonmagical ammunition made of metal that hits the ooze is destroyed after dealing damage.
The ooze can eat through 2-inch-thick, nonmagical metal in 1 round.

**False Appearance**: While the ooze remains motionless, it is indistinguishable from an oily pool or wet rock.

### 动作

**Pseudopod**: Melee Weapon Attack: +3 to hit, reach 5 ft., one target. Hit: 4 (1d6 + 1) bludgeoning damage plus 7 (2d6) acid damage, and if the target is wearing nonmagical metal armor, its armor is partly corroded and takes a permanent and cumulative -1 penalty to the AC it offers. The armor is destroyed if the penalty reduces its AC to 10.

### 战斗行动逻辑

**战术模式**: 泥怪 - 缓慢吞噬

- **行动模式**: 向最近生物移动并吞噬
- **特殊行为**:
  - 对武器攻击有分裂/腐蚀效果
  - 胶质方块：吸收路径上的一切
- **撤退条件**: 不会撤退

---

## Grick

**类型**: Medium monstrosity, neutral
**CR**: 2 (450 XP)

**AC**: 14 (natural)
**HP**: 27 (6d8)
**速度**: 30 ft. 尺, climb 30 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 14(+2) | 14(+2) | 11(+0) | 3(-4) | 14(+2) | 5(-3) |

**伤害抗性**: bludgeoning, piercing, and slashing from nonmagical weapons
**感官**: darkvision 60 ft., passive_perception 12
**语言**: 

### 特殊能力

**Stone Camouflage**: The grick has advantage on Dexterity (Stealth) checks made to hide in rocky terrain.

### 动作

**Multiattack**: The grick makes one attack with its tentacles. If that attack hits, the grick can make one beak attack against the same target.

**Tentacles**: Melee Weapon Attack: +4 to hit, reach 5 ft., one target. Hit: 9 (2d6 + 2) slashing damage.

**Beak**: Melee Weapon Attack: +4 to hit, reach 5 ft., one target. Hit: 5 (1d6 + 2) piercing damage.

### 战斗行动逻辑

**战术模式**: 通用战斗

- **优先目标**: 对自己威胁最大的敌人
- **行动模式**: 使用最有效的攻击方式
- **撤退条件**: 生命值低于25%时考虑逃跑

---

## Mimic

**类型**: Medium monstrosity, neutral
**CR**: 2 (450 XP)

**AC**: 12 (natural)
**HP**: 58 (9d8)
**速度**: 15 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 17(+3) | 12(+1) | 15(+2) | 5(-3) | 13(+1) | 8(-1) |

**伤害免疫**: acid
**状态免疫**: Prone
**感官**: darkvision 60 ft., passive_perception 11
**语言**: 

### 特殊能力

**Shapechanger**: The mimic can use its action to polymorph into an object or back into its true, amorphous form. Its statistics are the same in each form. Any equipment it is wearing or carrying isn 't transformed. It reverts to its true form if it dies.

**Adhesive (Object Form Only)**: The mimic adheres to anything that touches it. A Huge or smaller creature adhered to the mimic is also grappled by it (escape DC 13). Ability checks made to escape this grapple have disadvantage.

**False Appearance (Object Form Only)**: While the mimic remains motionless, it is indistinguishable from an ordinary object.

**Grappler**: The mimic has advantage on attack rolls against any creature grappled by it.

### 动作

**Pseudopod**: Melee Weapon Attack: +5 to hit, reach 5 ft., one target. Hit: 7 (1d8 + 3) bludgeoning damage. If the mimic is in object form, the target is subjected to its Adhesive trait.

**Bite**: Melee Weapon Attack: +5 to hit, reach 5 ft., one target. Hit: 7 (1d8 + 3) piercing damage plus 4 (1d8) acid damage.

### 战斗行动逻辑

**战术模式**: 通用战斗

- **优先目标**: 对自己威胁最大的敌人
- **行动模式**: 使用最有效的攻击方式
- **撤退条件**: 生命值低于25%时考虑逃跑

---

## Minotaur Skeleton

**类型**: Large undead, lawful evil
**CR**: 2 (450 XP)

**AC**: 12 (natural)
**HP**: 67 (9d10)
**速度**: 40 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 18(+4) | 11(+0) | 15(+2) | 6(-2) | 8(-1) | 5(-3) |

**伤害免疫**: poison
**状态免疫**: Exhaustion, Poisoned
**感官**: darkvision 60 ft., passive_perception 9
**语言**: understands Abyssal but can't speak

### 特殊能力

**Charge**: If the skeleton moves at least 10 feet straight toward a target and then hits it with a gore attack on the same turn, the target takes an extra 9 (2d8) piercing damage. If the target is a creature, it must succeed on a DC 14 Strength saving throw or be pushed up to 10 feet away and knocked prone.

### 动作

**Greataxe**: Melee Weapon Attack: +6 to hit, reach 5 ft., one target. Hit: 17 (2d12 + 4) slashing damage.

**Gore**: Melee Weapon Attack: +6 to hit, reach 5 ft., one target. Hit: 13 (2d8 + 4) piercing damage.

### 战斗行动逻辑

**战术模式**: 不死生物 - 无畏冲锋

- **优先目标**: 生命值最低的敌人
- **行动模式**: 直接攻击最近目标，不考虑自身安全
- **特殊行为**: 
  - 对神圣/光耀伤害有恐惧但不会逃跑
  - 优先使用特殊能力（如吸取生命）
- **撤退条件**: 不会撤退，战斗至死

---

## Ochre Jelly

**类型**: Large ooze, unaligned
**CR**: 2 (450 XP)

**AC**: 8 (dex)
**HP**: 45 (6d10)
**速度**: 10 ft. 尺, climb 10 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 15(+2) | 6(-2) | 14(+2) | 2(-4) | 6(-2) | 1(-5) |

**伤害抗性**: acid
**伤害免疫**: lightning, slashing
**状态免疫**: Blinded, Charmed, Blinded, Exhaustion, Frightened, Prone
**感官**: blindsight 60 ft. (blind beyond this radius), passive_perception 8
**语言**: 

### 特殊能力

**Amorphous**: The jelly can move through a space as narrow as 1 inch wide without squeezing.

**Spider Climb**: The jelly can climb difficult surfaces, including upside down on ceilings, without needing to make an ability check.

### 动作

**Pseudopod**: Melee Weapon Attack: +4 to hit, reach 5 ft., one target. Hit: 9 (2d6 + 2) bludgeoning damage plus 3 (1d6) acid damage.

### 战斗行动逻辑

**战术模式**: 泥怪 - 缓慢吞噬

- **行动模式**: 向最近生物移动并吞噬
- **特殊行为**:
  - 对武器攻击有分裂/腐蚀效果
  - 胶质方块：吸收路径上的一切
- **撤退条件**: 不会撤退

---

## Orc

**类型**: Medium humanoid, chaotic evil
**CR**: 0.5 (100 XP)

**AC**: 13 (armor)
**HP**: 15 (2d8)
**速度**: 30 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 16(+3) | 12(+1) | 16(+3) | 7(-2) | 11(+0) | 10(+0) |

**感官**: darkvision 60 ft., passive_perception 10
**语言**: Common, Orc

### 特殊能力

**Aggressive**: As a bonus action, the orc can move up to its speed toward a hostile creature that it can see.

### 动作

**Greataxe**: Melee Weapon Attack: +5 to hit, reach 5 ft., one target. Hit: 9 (1d12 + 3) slashing damage.

**Javelin**: Melee or Ranged Weapon Attack: +5 to hit, reach 5 ft. or range 30/120 ft., one target. Hit: 6 (1d6 + 3) piercing damage.

### 战斗行动逻辑

**战术模式**: 人形生物 - 战术协作

- **编队行动**: 2-3人一组配合
- **优先目标**: 施法者 > 远程 > 近战
- **行动模式**:
  1. 远程攻击者保持距离
  2. 近战者围攻单一目标
  3. 领导者指挥集火
- **撤退条件**: 死亡过半或领导者倒下

---

## Scout

**类型**: Medium humanoid, any alignment
**CR**: 0.5 (100 XP)

**AC**: 13 (armor)
**HP**: 16 (3d8)
**速度**: 30 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 11(+0) | 14(+2) | 12(+1) | 11(+0) | 13(+1) | 11(+0) |

**感官**: passive_perception 15
**语言**: any one language (usually Common)

### 特殊能力

**Keen Hearing and Sight**: The scout has advantage on Wisdom (Perception) checks that rely on hearing or sight.

### 动作

**Multiattack**: The scout makes two melee attacks or two ranged attacks.

**Shortsword**: Melee Weapon Attack: +4 to hit, reach 5 ft., one target. Hit: 5 (1d6 + 2) piercing damage.

**Longbow**: Ranged Weapon Attack: +4 to hit, range 150/600 ft., one target. Hit: 6 (1d8 + 2) piercing damage.

### 战斗行动逻辑

**战术模式**: 通用战斗

- **优先目标**: 对自己威胁最大的敌人
- **行动模式**: 使用最有效的攻击方式
- **撤退条件**: 生命值低于25%时考虑逃跑

---

## Shrieker

**类型**: Medium plant, unaligned
**CR**: 0 (10 XP)

**AC**: 5 (dex)
**HP**: 13 (3d8)
**速度**: 0 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 1(-5) | 1(-5) | 10(+0) | 1(-5) | 3(-4) | 1(-5) |

**状态免疫**: Blinded, Blinded, Frightened
**感官**: blindsight 30 ft. (blind beyond this radius), passive_perception 6
**语言**: 

### 特殊能力

**False Appearance**: While the shrieker remains motionless, it is indistinguishable from an ordinary fungus.

### 战斗行动逻辑

**战术模式**: 真菌/植物 - 被动防御

- **触发条件**: 生物进入30尺范围
- **行动模式**: 固定不动，使用孢子攻击
- **特殊行为**:
  - 尖叫蕈：发出警报吸引其他怪物
  - 紫蕈：使用多重触手攻击多个目标
- **撤退条件**: 无法移动，战斗至死

---

## Skeleton

**类型**: Medium undead, lawful evil
**CR**: 0.25 (50 XP)

**AC**: 13 (armor)
**HP**: 13 (2d8)
**速度**: 30 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 10(+0) | 14(+2) | 15(+2) | 6(-2) | 8(-1) | 5(-3) |

**伤害免疫**: poison
**状态免疫**: Poisoned, Exhaustion
**感官**: darkvision 60 ft., passive_perception 9
**语言**: understands all languages it spoke in life but can't speak

### 动作

**Shortsword**: Melee Weapon Attack: +4 to hit, reach 5 ft., one target. Hit: 5 (1d6 + 2) piercing damage.

**Shortbow**: Ranged Weapon Attack: +4 to hit, range 80/320 ft., one target. Hit: 5 (1d6 + 2) piercing damage.

### 战斗行动逻辑

**战术模式**: 不死生物 - 无畏冲锋

- **优先目标**: 生命值最低的敌人
- **行动模式**: 直接攻击最近目标，不考虑自身安全
- **特殊行为**: 
  - 对神圣/光耀伤害有恐惧但不会逃跑
  - 优先使用特殊能力（如吸取生命）
- **撤退条件**: 不会撤退，战斗至死

---

## Specter

**类型**: Medium undead, chaotic evil
**CR**: 1 (200 XP)

**AC**: 12 (dex)
**HP**: 22 (5d8)
**速度**: 0 ft. 尺, fly 50 ft. 尺, hover True 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 1(-5) | 14(+2) | 11(+0) | 10(+0) | 10(+0) | 11(+0) |

**伤害抗性**: acid, cold, fire, lightning, thunder, bludgeoning, piercing, and slashing from nonmagical weapons
**伤害免疫**: necrotic, poison
**状态免疫**: Charmed, Exhaustion, Grappled, Paralyzed, Petrified, Poisoned, Prone, Restrained, Unconscious
**感官**: darkvision 60 ft., passive_perception 10
**语言**: understands all languages it knew in life but can't speak

### 特殊能力

**Incorporeal Movement**: The specter can move through other creatures and objects as if they were difficult terrain. It takes 5 (1d10) force damage if it ends its turn inside an object.

**Sunlight Sensitivity**: While in sunlight, the specter has disadvantage on attack rolls, as well as on Wisdom (Perception) checks that rely on sight.

### 动作

**Life Drain**: Melee Spell Attack: +4 to hit, reach 5 ft., one creature. Hit: 10 (3d6) necrotic damage. The target must succeed on a DC 10 Constitution saving throw or its hit point maximum is reduced by an amount equal to the damage taken. This reduction lasts until the creature finishes a long rest. The target dies if this effect reduces its hit point maximum to 0.

### 战斗行动逻辑

**战术模式**: 不死生物 - 无畏冲锋

- **优先目标**: 生命值最低的敌人
- **行动模式**: 直接攻击最近目标，不考虑自身安全
- **特殊行为**: 
  - 对神圣/光耀伤害有恐惧但不会逃跑
  - 优先使用特殊能力（如吸取生命）
- **撤退条件**: 不会撤退，战斗至死

---

## Violet Fungus

**类型**: Medium plant, unaligned
**CR**: 0.25 (50 XP)

**AC**: 5 (dex)
**HP**: 18 (4d8)
**速度**: 5 ft. 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 3(-4) | 1(-5) | 10(+0) | 1(-5) | 3(-4) | 1(-5) |

**状态免疫**: Blinded, Blinded, Frightened
**感官**: blindsight 30 ft. (blind beyond this radius), passive_perception 6
**语言**: 

### 特殊能力

**False Appearance**: While the violet fungus remains motionless, it is indistinguishable from an ordinary fungus.

### 动作

**Multiattack**: The fungus makes 1d4 Rotting Touch attacks.

**Rotting Touch**: Melee Weapon Attack: +2 to hit, reach 10 ft., one creature. Hit: 4 (1d8) necrotic damage.

### 战斗行动逻辑

**战术模式**: 真菌/植物 - 被动防御

- **触发条件**: 生物进入30尺范围
- **行动模式**: 固定不动，使用孢子攻击
- **特殊行为**:
  - 尖叫蕈：发出警报吸引其他怪物
  - 紫蕈：使用多重触手攻击多个目标
- **撤退条件**: 无法移动，战斗至死

---

## Wraith

**类型**: Medium undead, neutral evil
**CR**: 5 (1800 XP)

**AC**: 13 (dex)
**HP**: 67 (9d8)
**速度**: 0 ft. 尺, fly 60 ft. 尺, hover True 尺

| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
| --- | --- | --- | --- | --- | --- |
| 6(-2) | 16(+3) | 16(+3) | 12(+1) | 14(+2) | 15(+2) |

**伤害抗性**: acid, cold, fire, lightning, thunder, bludgeoning, piercing, and slashing from nonmagical weapons that aren't silvered
**伤害免疫**: necrotic, poison
**状态免疫**: Charmed, Exhaustion, Grappled, Paralyzed, Petrified, Poisoned, Prone, Restrained
**感官**: darkvision 60 ft., passive_perception 12
**语言**: the languages it knew in life

### 特殊能力

**Incorporeal Movement**: The wraith can move through other creatures and objects as if they were difficult terrain. It takes 5 (1d10) force damage if it ends its turn inside an object.

**Sunlight Sensitivity**: While in sunlight, the wraith has disadvantage on attack rolls, as well as on Wisdom (Perception) checks that rely on sight.

### 动作

**Life Drain**: Melee Weapon Attack: +6 to hit, reach 5 ft., one creature. Hit: 21 (4d8 + 3) necrotic damage. The target must succeed on a DC 14 Constitution saving throw or its hit point maximum is reduced by an amount equal to the damage taken. This reduction lasts until the target finishes a long rest. The target dies if this effect reduces its hit point maximum to 0.

**Create Specter**: The wraith targets a humanoid within 10 feet of it that has been dead for no longer than 1 minute and died violently. The target's spirit rises as a specter in the space of its corpse or in the nearest unoccupied space. The specter is under the wraith's control. The wraith can have no more than seven specters under its control at one time.

### 战斗行动逻辑

**战术模式**: 不死生物 - 无畏冲锋

- **优先目标**: 生命值最低的敌人
- **行动模式**: 直接攻击最近目标，不考虑自身安全
- **特殊行为**: 
  - 对神圣/光耀伤害有恐惧但不会逃跑
  - 优先使用特殊能力（如吸取生命）
- **撤退条件**: 不会撤退，战斗至死

---

## 遭遇战术指南

### 随机遭遇处理

**遭遇强度判断**:
- CR 1/4以下：轻松遭遇
- CR 1/2-1：普通遭遇  
- CR 2-3：困难遭遇
- CR 4+：极危险遭遇

### 队伍应对建议

**当前队伍**: 5级 x 1 + 5级NPC x 1 + 辅助NPC x 5
**预估战力**: 相当于5级4人队

**遭遇难度参考**:
- 简单: 1-2个CR 1/2敌人
- 普通: 3-4个CR 1/4敌人 或 1个CR 2敌人
- 困难: 5-6个CR 1/4敌人 或 1个CR 3-4敌人

### NPC战斗行为

| NPC | 战斗风格 | 优先行动 |
|-----|---------|---------|
| 艾丝缇娅 | 后排支援 | 治疗>神术>近战 |
| 普皮多 | 狂热攻击 | 会找机会背刺队友 |
| 蒂纶朵 | 前排坦克 | 保护奎利昂 |
| 沙里士 | 精准打击 | 远程为主，近战自保 |
| 术沙 | 非暴力 | 只自卫，不主动攻击 |
| 史东 | 辅助 | 情绪感知，通知危险 |

---

*数据来源: D&D 5e SRD API*
*战术逻辑: 基于怪物类型和PDF原文行为模式*
