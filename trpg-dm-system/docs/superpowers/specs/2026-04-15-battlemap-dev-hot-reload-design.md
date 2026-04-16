# Battlemap 开发模式热重载设计

## 目标

为 battlemap 本地预览提供真正的开发模式：

- 浏览器固定打开一个稳定地址
- 当 Python / HTML / CSS 相关文件变化时，开发页会自动刷新
- Python 代码变化后，新的服务代码会真正生效，而不是只重拉旧状态
- 普通 localhost 预览模式保持不变，不注入 dev 逻辑

---

## 范围

本次只做 battlemap 开发预览所需的最小热重载闭环：

1. 新增一个 dev 监督器脚本
2. 监督器监听项目文件变化
3. 文件变化后重启 battlemap 子服务
4. 监督器维护 `reload_token`
5. 浏览器轮询 `/dev/reload`
6. token 变化时整页刷新
7. 仅在 dev 模式下注入前端热重载脚本

本次不做：

- WebSocket
- 增量 CSS 热替换
- 多页面共享 dev 服务
- 通用前端构建链

---

## 设计结论

### 方案选择

采用“稳定 supervisor + 可重启 worker + 浏览器轮询 reload token”。

原因：

- 用户浏览器入口端口稳定，不需要每次换端口
- Python 代码变更后会通过重启 worker 真正加载新代码
- 前端只需很小一段轮询脚本，复杂度低
- 不污染现有 `run_battlemap_localhost.py` 的普通模式

### 组件划分

#### 1. 普通 battlemap 服务

继续由现有 `scripts/run_battlemap_localhost.py` 提供：

- `/`
- `/api/encounter-state`

它仍然负责 battlemap 页面和 encounter state 轮询，不理解 dev 文件监听。

#### 2. dev supervisor

新增 `scripts/run_battlemap_dev.py`，职责只有三件事：

- 启动并管理一个 worker 子进程
- 监听项目文件变化并重启 worker
- 对外提供 `/dev/reload` 和页面/API 代理

它不参与 battlemap 规则，不修改 encounter 数据结构。

#### 3. dev 前端注入

在 dev 模式下，最终页面会额外注入一段脚本：

- 轮询 `/dev/reload`
- 记住上次的 `reload_token`
- token 变化后执行 `window.location.reload()`

普通模式页面不注入这段脚本。

---

## 数据与接口

### `/dev/reload`

返回格式：

```json
{
  "reload_token": "2026-04-15T16:05:11.120331Z",
  "worker_port": 8871
}
```

字段约定：

- `reload_token`
  - 只要发生代码热重载重启，就生成新值
  - 浏览器只比较是否变化，不关心内部格式
- `worker_port`
  - 仅用于调试和排查
  - 页面逻辑不依赖它

### 页面注入

dev 模式下页面需包含：

- `window.__BATTLEMAP_DEV__`
- `pollReloadToken()` 轮询函数
- `/dev/reload` 请求
- token 变化后 `window.location.reload()`

普通模式下不得出现这些内容。

---

## 文件监听策略

默认监听这些路径：

- `tools/`
- `scripts/`
- `test/`
- `data/examples/`

默认忽略：

- `__pycache__/`
- `.git/`
- `.pytest_cache/`
- `data/db/`

第一版监听后直接整页刷新，不区分是 Python、HTML 还是 CSS 来源。

---

## Worker 重启流程

1. supervisor 启动 worker
2. 浏览器访问 supervisor 稳定端口
3. supervisor 把 `/` 与 `/api/encounter-state` 代理给 worker
4. 文件变化触发后：
   - 停掉旧 worker
   - 启动新 worker
   - 更新 `reload_token`
5. 浏览器轮询发现 token 变化后整页刷新

这样可以保证：

- 页面地址不变
- Python 修改会真正生效
- battlemap 页面重新拉到新 worker 生成的 HTML

---

## 错误处理

### worker 启动失败

如果 worker 没有成功启动：

- supervisor 返回 `503`
- `/dev/reload` 仍可访问
- 页面刷新后可看到明确错误，而不是静默卡死

### watchdog 缺失

开发模式依赖 `watchdog`。

如果本地没有安装：

- `run_battlemap_dev.py` 启动时直接报错并提示安装
- 普通 localhost 模式不受影响

---

## 测试范围

需要覆盖：

1. 普通 localhost 页面不注入 dev 脚本
2. dev 页面会注入 `/dev/reload` 轮询脚本
3. `/dev/reload` 返回当前 token
4. 文件变更事件会更新 token
5. 既有普通 localhost 测试继续通过

---

## 结果预期

最终开发体验应为：

1. 运行 `run_battlemap_dev.py`
2. 浏览器打开固定 localhost 地址
3. 修改 Python / HTML / CSS 相关文件
4. 页面自动刷新并显示最新 battlemap 效果
