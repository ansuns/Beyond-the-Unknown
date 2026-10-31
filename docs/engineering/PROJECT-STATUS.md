# 项目状态

- 更新：2026-10-31
- 基线提交：`da9e151`（main）
- 计算方式：只统计能在当前环境复现的成果。凡“代码存在但未在本机跑通”的，一律记为**已实现未验证**，不计入完成率。

## 1. 仓库事实

| 项 | 值 | 如何确认 |
|---|---:|---|
| 已合并 PR（本轮） | #126 #127 #128 #129 #130 #131 | 均先通过 CI 再合并 |
| 已合并 PR（此前） | #117 #118 #119 #120 #121 #122 #123 #124 #125 | `git log --merges` |
| 未合并 PR | 无 | 只读+写 PAT 查询 GitHub API |
| 服务端 Python 文件 | 80 | `find server -name "*.py"` |
| 服务端路由 | 27（26 条 HTTP + 1 条 WebSocket） | `app.openapi()` 与路由装饰器核对 |
| Alembic 迁移 | 16 | `server/migrations/versions` |
| 数据库表 | 25 | `docs/engineering/database/0001_initial_schema.sql` |
| OpenAPI 路径 | 26，与 HTTP 路由 1:1 | `test_openapi_route_parity.py` |
| 客户端 TypeScript 文件 | 21 | `client/assets/scripts` |
| 客户端场景 | 1（`Boot.scene`） | `client/assets/scenes` |
| 客户端单测 | main 139 / PR #126 分支 143，均 22 文件 | 本次两端实跑 |
| 服务端单测 | 27 通过 | 本次实跑 |
| 服务端集成测试 | 17 项，无数据库时全部跳过 | 本次实跑 |
| GDD 章节 | 18 章 + 总览 + 2 份审核报告 | `docs/gdd` |

## 2. 资源完成率

| 指标 | 值 | 说明 |
|---|---:|---|
| 权威清单条目 | 112 | `asset-manifest.v1.json` |
| P0 条目 | 37 | 同上 |
| READY | **0** | `npm run validate:assets` 输出 |
| IN_PROGRESS | **3** | CHR_001 的主体 / 头像 / 预览，已有独立文件与 provenance |
| MISSING | 109 | 其余条目 |
| P1 / P2 | 24 / 51 | 同上 |
| P0 独立文件已交付 | **3 / 37** | 有文件，但未 Cocos 导入、未真机验收，故不计 READY |
| P0 完成率（READY 口径） | **0 / 37** | 发布门禁仍不通过 |

## 3. MVP 能力核对

状态含义：**已验证**＝本机跑过对应测试并记录在 `TEST-REPORT.md`；**已实现未验证**＝代码与测试存在，但需要 PostgreSQL/Redis/Docker 或 GUI 工具才能跑；**未实现**＝仓库内没有对应实现。

### 3.1 服务端

| 能力 | 代码 | 测试 | 状态 |
|---|---|---|---|
| 微信登录换会话 | `modules/auth` | 集成 1 | 已实现未验证 |
| 玩家资料与角色选择 | `modules/players` | 集成 1 | 已实现未验证 |
| 地图进入与实例成员 | `modules/maps` | 集成 1 | 已实现未验证 |
| 关卡进入/开始/放弃/坐标上报 | `modules/levels` | 集成 1 + 单测 1 | 单测已验证 |
| 法则施放/停止/维持 | `modules/rules` | 集成 1 | 已实现未验证 |
| 机关交互 | `modules/rules` | 集成 1 | 已实现未验证 |
| 结算 | `POST /level/settle` | 集成 1 | 已实现未验证 |
| 探索/收藏/档案 | `modules/progress` | 集成 1 | 已实现未验证 |
| 奖励领取 | `progress` + `rewards` 表 | 集成 1 | 已实现未验证 |
| 奖励条件 SCORE 阈值 | `_grant_score_conditions` | 集成 1（CI 通过） | **已验证**（GDD 11.7） |
| 三榜排行 | `GET /leaderboard` | 集成 2（CI 通过） | **已验证**（含 `season_id` 历史赛季查询） |
| 赛季与周榜 | `season_service` + `seasons` 表 | 集成 2（CI 通过） | **已验证** |
| 排行重算 | `POST /internal/leaderboard/{season_id}/recompute` | 集成 1（CI 通过） | **已验证**（GDD 13.6，流水只读、差异入审计日志） |
| 隐藏路线与隐藏结局 | `hidden_route_sequence` | 单测 1 | 单测已验证 |
| WebSocket 状态同步 | `realtime/` | 集成 1 | 已实现未验证 |
| Redis 在线状态与多节点 | `realtime/manager.py` | 集成 1 | 已实现未验证 |
| RabbitMQ 异步任务 | `workers/task_worker.py` | 单测 1 | 单测已验证 |
| 事务性 outbox | `0008_season_outbox` | 仅 CI smoke | **未验证** |

### 3.2 客户端

| 能力 | 代码 | 状态 |
|---|---|---|
| 移动与位置同步队列 | `latest-position-sync-queue` | 已验证 |
| 法则控制与组合技 | `law-controller`、`prototype-combos` | 已验证 |
| 注视租约时序 | `gaze-lease-timing` | 已验证 |
| 房间切换与关卡推进 | `level-progression`、`world-play-session` | 已验证 |
| 断线重连 | `map-session-reconnect` | 已验证 |
| 微信网络适配 | `wechat-network` | 已验证 |
| 等距投影与深度排序 | `prototype-layout` | 已验证 |
| 机关视觉状态 | `prototype-mechanism-visual` | 已验证 |
| 进程序列化 | `GameEntry`、`Boot.scene` | 已验证（静态结构，非编辑器导入） |

### 3.3 交付

| 能力 | 状态 |
|---|---|
| Cocos Creator 3.8.8 编辑器导入 | **未验证**（环境无 Cocos Creator） |
| 微信开发者工具导入 | **未验证**（环境无该工具） |
| Android / iOS 微信真机测试 | **未验证**（无设备与账号） |
| 正式美术资源入库 | **0 项** |
| 包体积与首屏优化 | 未开始（依赖构建结果） |

## 4. CI 状态

通过只读 PAT 读取 GitHub Actions 实际结果（2026-10-31 10:22 GMT+8）。

| 分支 / 提交 | 工作流 | 结果 |
|---|---|---|
| `091a6e5`（main 当前 HEAD） | server-ci / client-ci | 随 #128 合并后重跑 |
| `06187d4`（main 前一版） | server-ci / client-ci | success |
| PR #126 head `e2eef88` | client | success |
| PR #127 head | python / compose-smoke | success |
| PR #128 head | python / compose-smoke | success |

PR #127 与 #128 的 `compose-smoke` 在 GitHub 托管 runner 上通过，包含
`docker compose` 起服务、迁移升降级、健康检查、RabbitMQ worker 消费与 outbox 投递验证。
这**不等于**本机能跑：本机未安装 Docker，本地仍无法复现该作业。

下列 CI 步骤本机无法执行，未验证：

| 步骤 | 原因 |
|---|---|
| `alembic upgrade head` | 无 PostgreSQL |
| `docker compose` smoke（含 outbox → RabbitMQ 投递） | 无 Docker |
| 迁移 downgrade 后配置保留检查 | 无 Docker |

## 4.1 范围澄清（避免把可选功能当缺口）

| 章节 | 标记 | 处理 |
|---|---|---|
| GDD 12.6 成就系统 | **【可选扩展】**，V0.2 已明确不属于首期 MVP | 不实现是符合范围的，不列为缺口；启用时复用既有 `achievements` / `player_achievements` / `RT_ACHIEVE` 数据模型 |
| GDD 13.2 积分数值 | 明确写“具体数值为待定项” | 不擅自填数值；见阻塞 B-7 |
| GDD 15 商业化与广告 | 不在本期 MVP | `ad_reward_grants` 表已留位，逻辑未实现属预期 |
| GDD 14 轻社交 | 不在本期 MVP | 同上 |

## 5. 阻塞

| 编号 | 阻塞 | 影响 | 解除条件 |
|---|---|---|---|
| B-1 | ~~无 GitHub 凭据~~ | 已解除：PAT 已具备 `Contents` / `Pull requests` 写权限，实测建 ref 201、push 与合并成功 | — |
| B-2 | 无 Cocos Creator 3.8.8 | 无法验证导入与构建 | 安装编辑器 |
| B-3 | 无微信开发者工具 / 小程序 AppID | 无法验证小游戏导入与真机。工具已装于 `C:\Program Files (x86)\Tencent\微信web开发者工具`，但仍需登录与 AppID | 提供 AppID 并登录工具 |
| B-4 | 本机未安装 Docker / PostgreSQL / Redis | 19 项集成测试与迁移无法**本地**验证；CI 的 compose-smoke 已覆盖同等流程 | 安装 Docker Desktop，或提供数据库连接串 |
| B-5 | ~~生图后端带烘焙水印~~ | 已解除：`tools/strip_overlay.py` 按模式清角/裁边，23 项测试覆盖 | — |
| B-8 | AI 生成资源的授权与标识未核实 | 生成资源不得标 READY；若要求保留标识，现有 3 件需回退重制 | 见 `assets/AI-content-compliance.md` 的 C-1～C-4 |
| B-6 | 独立生图角色形象漂移 | 角色资源无法成套 | 确定 CHR_001 基准图后改图生图 |
| B-7 | 积分规则 `config_status=TUNING_REQUIRED`、`delta=NULL` | **三榜在任何未调优环境恒为 0 分**；`content_readiness` 报 BLOCKED、退出码 2 | GDD 13.2 明确数值为待定项，需策划定档后写入种子数据 |

## 6. 下一批任务

顺序按依赖排列。已完成的不再重复列出。

**已完成（本轮）**

- PR #126 关卡配置校验加强 + 测试转义修正。
- PR #127 服务端测试自治化。
- PR #128 资源色键管线 + 后端能力核查记录 + `.gitignore` 修复。
- PR #129 四份进度文件。
- PR #130 排行榜 `season_id` 历史赛季查询 + OpenAPI 与代码 1:1 对齐 + 路由一致性守卫。
- PR #131 排行榜重算（GDD 13.6）。

**待做（按优先级）**

1. **服务端 MVP 缺口**：`player_tasks` 个人任务（GDD 11.1，有表无代码）；`COMPOSITE` 组合条件未求值（GDD 11.7 剩余部分）；进度落库无 outbox 补偿（GDD 11.3）。三项都需要 PostgreSQL，可继续走 CI 验证。
2. **积分数值定档**（B-7）：需策划给出 13.2 的 `delta`，否则三榜恒为 0。
3. **资源**：水印处置决策 + CHR_001 基准图，然后按 `P0-production-handoff.md` §10 推进。
4. **客户端**：补齐 `UI_SETTLEMENT`、`UI_LAW_BAR` 状态机测试；场景与组件挂接需 Cocos Creator（B-2）。
5. **交付**：`wechat-mini-game-build.md` 的可执行构建步骤与包体积预算脚本。
