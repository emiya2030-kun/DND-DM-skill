# Encounter Template Snapshots Design

## 目标

为当前 battlemap / localhost 开发流程新增“命名样板快照”能力。

用户可以把某个已经调好的遭遇完整保存为一份样板，并在后续：

- 从样板恢复当前遭遇
- 从样板复制出新的开发遭遇
- 保留多份不同名字的样板，作为不同阶段的安全回退点

核心目标不是只保存 UI，而是保存**完整遭遇状态**，确保以后更换角色卡、地图、区域、回合数据后，仍然可以回到当前这版完成度。

## 范围

### 本轮纳入

- 新增独立的样板快照存储
- 保存当前遭遇为命名样板
- 列出已有样板
- 用样板恢复某个遭遇
- 用样板复制创建一个新遭遇
- localhost 页面提供最小可用入口

### 本轮不纳入

- 历史版本链
- 样板 diff / 合并
- 样板只恢复局部字段
- 权限控制
- 云端同步

## 用户确认的关键决定

- 保存目标：**完整遭遇快照**
- 样板数量：**允许多份，不同名字**
- 使用目的：**UI 和遭遇数据开发中的安全回退点**
- 数据边界：**样板与正式遭遇分开存，不混用一个列表**

## 当前代码上下文

- 正式遭遇目前由 [encounter_repository.py](/Users/runshi.zhang/DND-DM-skill/trpg-battle-system/tools/repositories/encounter_repository.py) 写入 TinyDB。
- localhost 预览页由 [run_battlemap_localhost.py](/Users/runshi.zhang/DND-DM-skill/trpg-battle-system/scripts/run_battlemap_localhost.py) 生成，并通过 `/api/encounter-state` 轮询当前遭遇状态。
- 当前预览遭遇 `enc_preview_demo` 已经承担 UI 和地图联调职责，适合作为首个样板来源。

## 设计总览

### 1. 独立样板仓储

新增 `EncounterTemplateRepository`，与正式遭遇仓储分离。

推荐单独文件：

- `data/db/encounter_templates.json`

每条记录包含：

- `template_id`
- `name`
- `source_encounter_id`
- `snapshot`
- `created_at`
- `updated_at`

其中 `snapshot` 保存完整 `Encounter.to_dict()` 结果，不做裁剪。

### 2. 样板是“完整快照”，不是引用

样板保存时复制遭遇当前完整内容，而不是引用正式遭遇。

这样后续正式遭遇继续修改时，不会污染已保存样板；恢复时也不会因为引用共享而产生隐式联动。

### 3. 同名策略

默认不覆盖同名样板。

如果用户再次保存一个已存在的名字，接口返回明确错误，提示改名或显式覆盖。第一版先不做“覆盖确认”交互，避免误操作。

### 4. 恢复与复制的区别

#### 恢复

把某个样板的 `snapshot` 写回目标 `encounter_id`。

适合：

- 改坏当前 UI 后直接回退
- 把 `enc_preview_demo` 恢复到某个稳定版本

#### 复制创建

从样板的 `snapshot` 复制出一个新的遭遇记录，并替换：

- `encounter_id`
- `name`（可选新名）

其余数据默认沿用样板。

适合：

- 从基线样板开一个新实验分支
- 保留当前工作内容，同时开始另一个版本

## 数据流

### 保存样板

1. 读取目标遭遇
2. 序列化为完整 snapshot
3. 生成 `template_id`
4. 写入样板仓储
5. 返回样板元数据

### 恢复样板

1. 读取样板记录
2. 反序列化 `snapshot`
3. 将 `encounter_id` 改为目标遭遇 id
4. 保存到正式遭遇仓储
5. localhost 轮询后刷新页面

### 复制创建新遭遇

1. 读取样板记录
2. 反序列化 `snapshot`
3. 替换新 `encounter_id`
4. 可选替换新名称
5. 保存为新遭遇

## localhost 入口

第一版只做最小可用操作区，不做复杂管理页。

建议放在 localhost 页面顶部工具区或地图外层控制区，包含：

- 当前遭遇另存为样板
- 样板列表
- 从样板恢复当前遭遇
- 从样板创建新遭遇

交互原则：

- 操作成功后显示简短状态
- 恢复成功后依赖现有轮询刷新
- 错误信息直接显示，不静默失败

## API / 服务设计

新增服务：

- `SaveEncounterTemplate`
- `ListEncounterTemplates`
- `RestoreEncounterFromTemplate`
- `CreateEncounterFromTemplate`

localhost handler 对应新增最小 HTTP 接口，优先沿用当前脚本内 handler 模式，不引入新框架。

建议接口：

- `GET /api/encounter-templates`
- `POST /api/encounter-templates`
- `POST /api/encounter-templates/restore`
- `POST /api/encounter-templates/create-encounter`

## 错误处理

- 遭遇不存在：返回 `404`
- 样板不存在：返回 `404`
- 样板名重复：返回 `409`
- 新遭遇 id 已存在：返回 `409`
- snapshot 无法反序列化：返回 `400` 或 `500`，取决于是输入错误还是数据损坏

所有错误都返回明确 JSON，不返回空 HTML 或模糊文本。

## 测试策略

至少覆盖：

- 样板仓储保存 / 读取 / 列表
- 同名样板冲突
- 从样板恢复遭遇
- 从样板复制新遭遇
- localhost API 成功与错误响应
- localhost 页面包含样板操作外壳

## 方案比较结论

本设计选择“独立样板仓储 + 完整 encounter 快照”的方案，而不是直接把样板混进正式遭遇表。

原因：

- 语义清晰
- 不污染正式遭遇列表
- 回退能力完整
- 后续容易扩展样板元数据和管理能力

## 实施边界

第一版目标是把“可保存多个命名样板并可恢复/复制”的主链打通。

只要这条链路成立，后续 UI 继续迭代时就已经具备稳定回退点，不需要等历史版本系统或更复杂的样板中心上线。
