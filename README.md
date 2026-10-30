# 无界之外 · Beyond the Unknown

一款面向微信小游戏的原创 Q 版奇幻探索解谜游戏。

## 仓库结构

- `docs/gdd/`：GDD 总览；`docs/gdd/chapters/`：第 1–18 章。
- `docs/reviews/`：GDD 审核、修订与复核报告。
- `docs/engineering/`：API、数据库、关卡配置、实时通信协议、技术决策与纵向切片计划。
- `server/`：Python 3.12+ / FastAPI 服务端、数据库迁移、自动化测试与容器构建。
- `client/`：Cocos Creator 客户端工程入口与初始化约定。
- `.github/workflows/`：持续集成工作流。
- `docker-compose.yml`：本地 PostgreSQL、RabbitMQ、API 与 Worker 编排。

## 文档入口

- [GDD 总览](docs/gdd/无界之外_GDD_总览.md)
- [GDD 章节目录](docs/gdd/chapters/README.md)
- [审核报告](docs/reviews/)
- [工程契约与决策](docs/engineering/)

## 当前基线

GDD V0.2 已完成首轮跨章节规则、MVP 范围、数据字典、UI/API 映射与修订复核。服务端 VS-0 至 VS-5（工程骨架、微信身份/玩家持久化、共享地图/WebSocket、个人关卡、法则权威逻辑、发现/结算/奖励/排行榜）已合并至 main；相关 Python/Ruff、PostgreSQL 迁移/集成测试和 Docker Compose smoke 检查通过。客户端已具备 TypeScript REST/WebSocket、个人关卡/法则/进度 API 会话层，以及 Cocos Creator 3.8.8 Boot 几何占位原型（微信登录、共享地图、玩家显示、点击移动、进入/放弃个人房间）。当前仍不是可发布的完整小游戏：法则数值、机关坐标、正式关卡内容/美术、场景交互与结算 UI、Cocos 编辑器导入/构建、微信开发者工具和真机验证尚未完成。Redis 多节点 presence/pub-sub、正式 AOI、RabbitMQ Publisher Confirms、有限重试与 DLQ 已实现；Transactional Outbox、业务消费者、Redis 多节点 presence/pub-sub、生产部署、安全与性能压测仍是 VS-6 发布前工作。

## 工程原则

- PostgreSQL 是业务数据权威来源。
- API 与业务模块按领域拆分；跨域依赖通过明确服务接口，不互相导入内部实现。
- 配置和密钥通过环境变量注入，禁止提交真实凭证。
- 数据库变更必须通过 Alembic migration。
- 每个纵向切片通过独立分支、PR 与自动化测试后再合并。
