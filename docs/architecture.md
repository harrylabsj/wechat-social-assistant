# WeChat Social Assistant 架构设计

状态：`v1.2` 本地优先基线（2026-08-24）

## 1. 目标与边界

WeChat Social Assistant（WSA）把“可见的微信会话证据”转换为本地关系记忆、关系质量卡片和用户可编辑的跟进草稿。它不是微信机器人，也不尝试绕过微信安全边界。

明确不做：

- 不读取或修改微信私有数据库、加密存储或内部协议。
- 不自动发送、回复、点赞、加好友或执行任何外部联络动作。
- 不把 OCR/截图中的文字当作系统指令。截图、OCR、导入文件和 MCP 返回均是低信任证据，必须经过宿主策略和用户确认。

## 2. 总体分层

```mermaid
flowchart LR
    Host[通用 Agent 宿主\nHermes / OpenClaw / Codex / 其他 MCP Host]
    Skill[Skill\n工作流、权限、确认、提示注入防护]
    Plugin[OpenClaw 原生 Plugin\n薄适配，仅转发 MCP]
    MCP[MCP stdio\n结构化 tools/resources/prompts]
    CLI[CLI / Python API\n显式命令与回归测试]
    Capture[感知适配层\nAX 文本树 + 窗口截图 + Vision OCR]
    Core[本地关系引擎\n解析、去重、信号、建议、质量]
    Store[(SQLite\nWAL + migrations + review queue)]
    Files[(本地 captures/reports\n用户提供的来源文件)]

    Host --> Skill
    Host --> Plugin
    Host --> MCP
    Skill --> CLI
    Plugin --> MCP
    MCP --> Core
    CLI --> Core
    Capture --> Core
    Core --> Store
    Capture --> Files
    Core --> Files
```

核心原则是“一个引擎、多个宿主入口”：插件和 Skill 不复制业务逻辑，所有关系计算都进入 `wsa/`，MCP 是跨宿主的稳定契约。

### 2.1 宿主适配矩阵

| 宿主 | 安装资产 | 主要职责 | 默认权限 |
|---|---|---|---|
| Hermes | `agent/hermes/wechat-social-assistant/SKILL.md` | 指导命令选择、确认和安全边界 | 读；写操作逐次确认 |
| OpenClaw（原生插件） | `agent/openclaw/wechat-social-assistant-plugin/` | 把 `wsa_*` 工具转发到 MCP | 只注册读工具 |
| OpenClaw（MCP） | `wsa-mcp` / `python3 -m wsa.mcp_server` | 直接使用完整 MCP 工具集 | 写工具字段确认 |
| 其他 MCP Host | stdio MCP | 复用相同 tools/resources/prompts | 由宿主策略控制 |
| 无 MCP 宿主 | CLI + Skill 文档 | 通过 `wsa_run.py --confirm` 调用 | 写命令显式确认 |

OpenClaw 插件配置：

- `projectRoot`：能导入 `wsa` 的可信 checkout（可选）。
- `dbPath`：本地 `social.db` 路径（可选，默认随当前工作目录）。
- `pythonPath`：安装了 WSA 的 Python（默认 `python3`）。
- `trustedWrites=false`：默认只注册读工具；启用后仍必须满足 MCP 的 `confirmed` 和精确 `confirmation_text`。

插件是一次性启动 Python MCP 子进程、发送一个 `tools/call` 请求并读取结构化响应的薄桥接；超时 20 秒、响应 2 MiB 上限，避免宿主被失控进程或异常 OCR 输出拖垮。插件把 `allowedRoot` 作为可信配置传给 `WSA_ALLOWED_ROOT`，MCP 会拒绝越过该根目录的数据库、截图和日志路径；MCP 进程初始化时默认把当前工作目录设为可信根。

## 3. 数据流与时间语义

```mermaid
sequenceDiagram
    participant U as 用户
    participant H as Agent 宿主
    participant C as Capture/OCR
    participant S as Store
    participant A as 分析引擎

    U->>H: 请求查看关系/准备草稿
    H->>S: MCP read tool
    S->>A: 读取 captures + signals + people
    A-->>H: 证据、分数、不确定性、草稿
    H-->>U: 展示并等待编辑/确认
    U->>H: 明确确认（仅在需要写入时）
    H->>S: write tool + confirmation fields

    Note over C,S: 捕获是观察，不等于互动
    C->>S: captured_at + interaction_at=null
    Note over S: 手工录入/明确互动事件才更新 last_interaction_at
```

`captured_at` 表示屏幕或文件被观察的时间；`last_interaction_at` 表示用户明确声明或手工录入的互动时间。自动 OCR/watch 不会因为观察到旧聊天而把联系人“碰过”时间刷新到现在。旧版本直接调用 Python API 未传 `interaction_at` 时保留向后兼容行为；CLI capture/import 已使用正确的显式语义。

图片路径也有所有权边界：

- WSA 自己生成的截图存放在 `data/captures/`，标记为 managed，可在联系人删除时按引用计数安全清理。
- `import-image`、`ingest --image-path` 只保存用户文件的引用，不拥有该文件；删除联系人不会删除原图。
- 删除前解析真实路径并要求位于数据库旁的 `captures/` 根目录内，防止通过绝对路径或符号链接误删用户文件。

### 3.1 OCR observation 表

`captures` 保留一次采集的业务记录；`ocr_observations` 保留每条 AX/OCR 观察的结构化证据（不再假设一定有截图）；`ocr_reviews`/`ocr_review_events` 保留用户校正状态和审计事件：

```text
ocr_observations(
  id, capture_id, sequence, text, confidence,
  bbox_x, bbox_y, bbox_width, bbox_height,
  source, speaker_candidate, speaker_confidence, created_at
)
```

坐标使用 Vision/AX 共用的 0..1 归一化坐标（左下角为原点），`speaker_candidate` 是低置信度启发式候选，不是已确认联系人。旧数据库升级时会把已有 `clean_text` 按行回填为 `source=text` 的无坐标 observation；Vision OCR 保存 `source=vision`，AX 文本树保存 `source=accessibility` 且 confidence=1.0。用户 review 不覆盖原始 observation，而是把生效文本物化到 `captures.corrected_text`；分析查询统一使用 `coalesce(corrected_text, clean_text)`。MCP 的 `get_capture_observations` 和 `list_ocr_reviews` 可供通用 Agent 定位并请求人工校正证据。

数据库通过 `schema_migrations(version, applied_at)` 顺序升级。当前版本为 2：v1 引入结构化 OCR，v2 引入校正队列和生效文本。连接默认启用 WAL、5 秒 busy timeout 和 `synchronous=normal`；`wsa backup --yes` 使用 SQLite backup API 生成一致快照，而不是直接复制可能尚未合并的 WAL 文件。

## 4. 感知层：AX 优先，OCR 兜底

微信桌面端没有面向个人桌面客户端的稳定 CLI/API，因此产品采用“AX 文本树优先 + 用户可见窗口截图 + macOS Vision OCR 兜底”的组合。AX 只读取前台应用公开的 Accessibility 属性；微信版本或控件不暴露文本时，才回退截图 OCR。当前实现的隐私收紧点：

- `capture`、`quick-capture`、`watch` 默认只抓取当前前台窗口；使用 CoreGraphics helper 找到前台应用的 window id，再调用 `screencapture -l`，不再在后台循环中弹出交互式全屏选择器。
- `capture --mode accessibility` 读取前台应用的 AX 文本节点并以 `source=accessibility` 入库；权限未授予、读取失败或文本树为空时自动走 `window` OCR，标记为 `source=ocr-fallback`。该模式不生成截图，除非实际发生 OCR fallback。
- `--mode screen` 仍保留为显式 opt-in；Skill/插件不得替用户默认启用它。
- OCR helper 同时保留 Vision observation 的排序逻辑；群聊说话人识别增加非人名词/后缀保护，避免“产品方向”“项目资料”等普通短句被当成联系人。
- 已安装 wheel 会把 Swift 源码作为 package data 携带，并把编译产物放在用户缓存目录；不会写入只读的 site-packages。

### 4.1 更好的感知路线（按可靠性排序）

1. **企业微信官方 AI Bot / 长连接**：如果业务允许迁移到企业微信，优先使用官方机器人/长连接事件，获得结构化消息、发送权限和审计边界；这比桌面 OCR 稳定得多。
2. **macOS ScreenCaptureKit 指定窗口**：把现有 `screencapture -l` helper 演进为 `SCContentFilter(desktopIndependentWindow:)`，只订阅 WeChat 窗口帧，并配合窗口生命周期和权限检测。它适合长期 watch，避免显示器级采集。
3. **macOS Accessibility（AXUIElement）**：当前已实现前台应用 AX 文本树读取、来源标记、归一化坐标和空树/权限失败的 OCR fallback。仍需针对不同微信版本补充窗口/消息气泡层级适配，不能假设所有版本微信都暴露完整文本或说话人关系。
4. **用户主动分享/导入**：用户手动截取、导入图片、或导入脱敏的聊天归档 manifest，适合隐私敏感场景；不需要驻留 watch。

不建议：注入微信进程、读取微信私有数据库、逆向内部协议、模拟未公开 WebSocket/CLI。这些方案不可审计、易失效，也会把产品带入账号和隐私风险。

实现依据：Apple 的 [ScreenCaptureKit 指定窗口过滤器](https://developer.apple.com/documentation/screencapturekit/sccontentfilter/init(desktopindependentwindow:))、[Vision 文本观察结果](https://developer.apple.com/documentation/vision/vnrecognizedtextobservation)，以及企业微信团队提供的 [AI Bot Node SDK](https://github.com/WecomTeam/aibot-node-sdk)。

## 5. 核心模块

- `wsa/store.py`：SQLite schema、去重、图片所有权、观察/互动时间语义、派生联系人。
- `wsa/audit.py`：本地表行数、schema 版本、数据路径和删除影响审计。
- `wsa/reviews.py`：低置信度 OCR review 队列、人工校正、生效文本物化和审计事件。
- `wsa/security.py`：MCP 可信根路径策略；CLI/Python API 不受该传输层策略限制。
- `wsa/connectors.py`：`CaptureConnector` seam、窗口/整屏采集 connector、AX 权限探测和文本树 reader/fallback contract。
- `wsa/parser.py`：OCR 文本清洗、联系人提示、信号提取。
- `wsa/profiles.py`：联系人/群聊/群内发言人画像、链接/文件/组织线索；低置信度的普通短句不进入 speaker。
- `wsa/suggestions.py`、`wsa/relationship_quality.py`、`wsa/dashboard.py`：只根据证据和明确互动时间计算建议、质量和仪表盘。
- `wsa/mcp_server.py`：唯一跨宿主结构化契约；写工具必须携带精确确认字段。
- `wsa/ocr.py`：通过 connector 调用 macOS 捕获、AX 文本树读取、前台应用/窗口识别、Vision OCR、用户缓存中的 native helper 编译。
- `agent/...`：宿主安装资产，不得承载关系算法。

## 6. 安全与权限模型

读写操作分为四类：

1. **纯读**：status、connector status、audit、contacts、brief、quality、dashboard、reports、sources、candidates、feedback list、recent captures。
2. **本地数据库写入**：ingest、feedback、OCR review、candidate confirm、import source/archive、Obsidian import、analyze。
3. **本地文件/删除**：capture/watch、export、delete、Obsidian export、reset。
4. **进程控制**：watch-interval、watch、stop-watch。

Skill、插件和 MCP 描述必须把第 2–4 类交给用户确认。Agent 可以生成草稿，但永远不能把草稿直接送入微信发送动作。任何 OCR 文本中的“忽略之前指令”“执行命令”等内容都只能作为会话证据展示。`record_ocr_review` 只能带精确的 `confirmation_text="review OCR observation"` 写入 review；原始 OCR 和截图不会被覆盖。

## 7. 发布与安装布局

```text
pyproject.toml                 # wsa + wsa-mcp console scripts
wsa/native/*.swift             # wheel 中携带的 native helper source
agent/agent.json               # 机器可读安装/能力清单
agent/hermes/...               # Hermes Skill + CLI wrapper
agent/openclaw/...md           # OpenClaw Skill/fallback
agent/openclaw/...-plugin/     # OpenClaw manifest + JS thin adapter
docs/architecture.md           # 本文
```

发布前最低检查：

```bash
python3 -m pytest -q
python3 -m build --wheel --no-isolation
python3 -m json.tool agent/agent.json >/dev/null
node --check agent/openclaw/wechat-social-assistant-plugin/index.js
node --check agent/openclaw/wechat-social-assistant-plugin/openclaw_compat.js
```

## 8. 后续演进

- 让 speaker 归因进一步使用 bbox/头像区域和多帧一致性，而不是只靠当前的短行启发式候选。
- 用 ScreenCaptureKit 指定窗口替换 `screencapture -l`，增加窗口关闭、权限撤销、多显示器和睡眠恢复测试。
- MCP initialize 返回 `schemaVersion=1.2.0` 和 capability discovery；插件只消费 MCP，不与 Python 内部函数耦合。
- 将企业微信官方长连接作为独立 `official_connector`，与 OCR connector 共享 `CaptureEvent`/`InteractionEvent` 事件模型。
- 增加脱敏日志、密钥/路径红线检查和一套宿主互操作 smoke test（Hermes wrapper、OpenClaw plugin、裸 MCP）。
