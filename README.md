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

GDD V0.2 已完成首轮跨章节规则、MVP 范围、数据字典、UI/API 映射与修订复核。服务端 VS-0 工程骨架已建立，包含 FastAPI、PostgreSQL/Alembic、RabbitMQ Worker 与 CI smoke test。微信登录、玩家业务 API、生产消息重试/Outbox、客户端工程、设备压测及生产部署仍属于后续工作。

## 工程原则

- PostgreSQL 是业务数据权威来源。
- API 与业务模块按领域拆分；跨域依赖通过明确服务接口，不互相导入内部实现。
- 配置和密钥通过环境变量注入，禁止提交真实凭证。
- 数据库变更必须通过 Alembic migration。
- 每个纵向切片通过独立分支、PR 与自动化测试后再合并。
