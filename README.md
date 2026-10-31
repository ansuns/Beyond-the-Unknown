# 无界之外 · Beyond the Unknown

一款面向微信小游戏的原创 Q 版奇幻探索解谜游戏。

## 仓库结构

- `docs/gdd/`：GDD 总览与第 1–18 章。
- `docs/reviews/`：GDD 审核、修订与复核报告。
- `docs/engineering/`：API、数据库、关卡配置、实时通信协议、资源生产计划与纵向切片验收计划。
- `server/`：Python 3.12+ / FastAPI 服务端、PostgreSQL 迁移、RabbitMQ Worker、Redis 实时状态与自动化测试。
- `client/`：Cocos Creator 3.8.8 + TypeScript 微信小游戏客户端原型。
- `.github/workflows/`：客户端、服务端及 Compose 持续集成。
- `docker-compose.yml`：本地 PostgreSQL、RabbitMQ、Redis、API 与 Worker 编排。

## 文档入口

- [GDD 总览](docs/gdd/无界之外_GDD_总览.md)
- [GDD 章节目录](docs/gdd/chapters/README.md)
- [审核报告](docs/reviews/)
- [工程契约与决策](docs/engineering/)
- [第一阶段垂直切片计划与验收清单](docs/engineering/vertical-slice/plan.md)
- [美术/音效资源清单与交付门禁](docs/engineering/assets/README.md)
- [微信小游戏构建与联调手册](docs/engineering/wechat-mini-game-build.md)

## 当前工程状态（2026-10-31）

### 已完成并由 CI 覆盖

- 服务端：Python 3.12+、FastAPI、SQLAlchemy async、PostgreSQL/Alembic、Redis presence/pub-sub、RabbitMQ Outbox/Worker。
- 玩法权威链路：ROOM-01 至 ROOM-05 与隐藏结局的服务端配置、法则/机关状态、进度结算；隐藏路线端到端集成测试覆盖完成五个房间、按序触发组合、解锁并完成独立隐藏结局 run。
- 客户端：Cocos Creator 3.8.8 工程骨架、微信登录/REST/WebSocket、共享地图与个人关卡会话、45° 等距几何原型、虚拟摇杆、机关类型符号、投影纵深排序、配置驱动组合和位置同步队列。
- 质量门禁：关卡配置/隐藏路线契约、资源清单结构、Cocos 场景 JSON/UUID、客户端 TypeScript 与 Vitest、服务端集成测试及 Compose 数据库迁移/回滚检查。
- 最近主分支提交的 Client CI 与 Server CI 均通过。具体阶段和 PR 记录见垂直切片计划。

### 当前明确阻塞项（不能宣称已可发布）

- **正式美术/音效资源：112 项全部为 MISSING**。其中 P0 37 项、P1 24 项、P2 51 项；资源交付门禁保持 BLOCKED。几何占位、图标符号和资源清单不等于正式资源交付。
- **Cocos Creator 编辑器实际导入/构建、微信开发者工具构建和 Android/iOS 真机验证尚未完成**。CI 的 JSON/TypeScript 检查不能替代编辑器与真机验收。
- 完整移动碰撞/寻路、正式 HUD/结算界面、加载与异常状态、机关动画/音效、性能与弱网实测仍待完成。
- Redis 生产 HA/TLS/鉴权与故障演练、最终 AOI、RabbitMQ 故障恢复演练、生产部署、安全/隐私和小游戏平台审核仍待完成。
- 广告 SDK、广告回调验签、频控及运营配置尚未接入。

因此，当前准确状态是：**服务端五房间与隐藏结局权威玩法链路已有自动化验证，客户端具备几何原型和移动交互；尚未达到正式美术交付、微信真机可玩或发布标准。**

## 本地开发

- 服务端环境与启动步骤：见 [微信小游戏构建与联调手册](docs/engineering/wechat-mini-game-build.md)。
- 客户端在 `client/` 目录执行 `npm run typecheck`、`npm test`、`npm run validate:project`、`npm run validate:content`、`npm run validate:assets`。
- 发布前必须执行 `npm run validate:release-assets`；当前由于 112 项资源未交付，该命令应失败并阻止发布。

## 工程原则

- PostgreSQL 是业务数据权威来源；Redis 仅承担实时 presence/pub-sub 等用途。
- API 与业务模块按领域拆分；跨域依赖通过明确服务接口，不互相导入内部实现。
- 配置和密钥通过环境变量注入，禁止提交真实凭证。
- 数据库变更必须通过 Alembic migration，并验证升级/回滚路径。
- 每个纵向切片通过独立分支、PR 与自动化测试后再合并。
