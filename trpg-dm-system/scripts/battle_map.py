#!/usr/bin/env python3
"""D&D 战斗地图 - 完整版"""

def render_map(title, width, height, units, terrain=None, auras=None):
    if terrain is None:
        terrain = []
    if auras is None:
        auras = []
    
    grid = [['  .' for _ in range(width)] for _ in range(height)]
    
    for x, y, ttype in terrain:
        if 1 <= x <= width and 1 <= y <= height:
            grid[y-1][x-1] = f' {ttype}'
    
    for name, x, y in units:
        if 1 <= x <= width and 1 <= y <= height:
            grid[y-1][x-1] = f' {name}'
    
    aura_cells = set()
    for cx, cy, r, aname in auras:
        for y in range(1, height+1):
            for x in range(1, width+1):
                if ((x-cx)**2 + (y-cy)**2) <= r**2:
                    aura_cells.add((x, y))
    
    lines = []
    lines.append(f"【{title}】{width}x{height}格 = {width*5}x{height*5}尺")
    lines.append("")
    
    header = "    "
    for x in range(1, width+1):
        header += f" {x:2d}"
    lines.append(header)
    lines.append("   +" + "---" * width + "+")
    
    # 从上到下画（行号大的在上面）
    for y in range(height, 0, -1):
        row = f"{y:2d} |"
        for x in range(1, width+1):
            cell = grid[y-1][x-1]
            if cell == '  .' and (x, y) in aura_cells:
                cell = ' 光'
            row += cell
        row += " |"
        lines.append(row)
    
    lines.append("   +" + "---" * width + "+")
    
    lines.append("")
    lines.append("【图例】. = 空地  光 = 光环  墙 = 岩壁  岩 = 石柱  水 = 水流  坑 = 陷坑  陷 = 陷阱")
    
    if units:
        lines.append("")
        lines.append("【单位】")
        for name, x, y in units:
            lines.append(f"  {name} ({x},{y})")
    
    if auras:
        lines.append("")
        lines.append("【光环】")
        for cx, cy, r, aname in auras:
            lines.append(f"  {aname} - 中心({cx},{cy}), 半径{r*5}尺")
    
    return "\n".join(lines)


# ========== 10x10 完整 ==========
print(render_map(
    "狭窄洞窟 - 奎利昂 vs 3卓尔",
    width=10, height=10,
    units=[
        ("奎", 6, 6),
        ("卓1", 3, 3),
        ("卓2", 8, 4),
        ("卓3", 4, 9),
    ],
    terrain=[
        (1, 5, "墙"), (1, 6, "墙"), (1, 7, "墙"),
        (5, 5, "陷"),
    ]
))

print("\n" + "=" * 50 + "\n")

# ========== 15x15 完整 ==========
water_terrain = []
for x in range(3, 14):
    for y in range(7, 13):
        water_terrain.append((x, y, "水"))

print(render_map(
    "瀑布洞窟 - 灰泥怪水池",
    width=15, height=15,
    units=[
        ("奎", 8, 3),
        ("艾", 6, 3),
        ("泥1", 5, 9),
        ("泥2", 11, 10),
    ],
    terrain=water_terrain + [(9, 8, "陷")]
))

print("\n" + "=" * 50 + "\n")

# ========== 20x20 完整 ==========
rocks = []
for x in [1,2,3, 18,19,20]:
    for y in [1,2,3, 18,19,20]:
        rocks.append((x, y, "岩"))

print(render_map(
    "无限剑制 - 奎利昂爆发",
    width=20, height=20,
    units=[
        ("奎", 10, 10),
        ("卓1", 5, 5),
        ("卓2", 15, 5),
        ("卓3", 5, 15),
        ("卓4", 15, 15),
        ("精", 10, 3),
    ],
    terrain=rocks,
    auras=[(10, 10, 12, "无限剑制(60尺)")]
))
