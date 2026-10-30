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

GDD V0.2 已完成首轮跨章节规则、MVP 范围、数据字典、UI/API 映射与修订复核。VS-0 至 VS-4 的服务端基础、身份持久化、共享地图、个人关卡、法则与机关权威逻辑，以及客户端 REST/WebSocket 编排已合并至 main。VS-5 发现、结算、永久进度、奖励与三榜能力正在独立分支实现并等待 CI 审核；尚未合并。完整 Cocos 场景表现、关卡坐标/法则数值配置、ROOM-01 出口交互范围校验、赛季审核发奖、RabbitMQ Outbox/Worker、Redis 多节点 presence/pub-sub、正式 AOI、真机端到端、设备压测及生产部署仍未完成。

## 工程原则

- PostgreSQL 是业务数据权威来源。
- API 与业务模块按领域拆分；跨域依赖通过明确服务接口，不互相导入内部实现。
- 配置和密钥通过环境变量注入，禁止提交真实凭证。
- 数据库变更必须通过 Alembic migration。
- 每个纵向切片通过独立分支、PR 与自动化测试后再合并。
