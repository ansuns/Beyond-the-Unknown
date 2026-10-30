# 工程决策记录

## 已确认
- 【MVP必须】客户端引擎：Cocos Creator 3.x。
- 【MVP必须】客户端语言：TypeScript。
- 【MVP必须】服务端：Python 3.12+ + FastAPI，模块化单体。
- 【MVP必须】数据层：SQLAlchemy 2.x async + asyncpg；Alembic 迁移；Pydantic 2.x。
- 【MVP必须】ASGI 运行：Uvicorn；REST 与 WebSocket 共用语言无关契约。
- 【MVP必须】异步任务队列：RabbitMQ；通过独立 Python Worker 消费后台任务。
- 【MVP必须】持久化：PostgreSQL；实时在线状态/缓存可用 Redis。
- 【MVP必须】实时通信：WebSocket；请求接口：REST /api/v1。
- 【MVP必须】首期关闭广告展示与正式广告 SDK；成就系统不在首期范围。
- 【MVP必须】首期包含 5 个常规房间和 LV-HIDDEN-01；隐藏路线 HIDDEN-ROUTE-01 必须启用。
- 【MVP必须】个人关卡运行隔离；未结算机关/谜题临时状态不承诺跨退出恢复。

## 工程约束
- Python 服务端采用 async I/O；数据库连接池、WebSocket 广播、Redis 与 RabbitMQ 访问必须有超时和背压策略，CPU 密集任务不得阻塞事件循环。
- RabbitMQ 承担可靠后台任务投递；消息采用明确的 schema_version、task_id、correlation_id 与幂等键，消费者使用手动 ACK，失败按有限次数重试并进入 dead-letter queue；不得把消息队列当作业务数据权威存储。
- OpenAPI 3.1 与 WebSocket JSON Schema 是客户端/服务端共同契约；Pydantic 模型需通过契约一致性测试。
- PostgreSQL 是玩家永久进度、发现、收藏、奖励、结算与积分流水的权威存储。
- Redis 仅作可重建缓存、在线会话、限流等，不作为永久进度唯一来源。
- 结算事务需将 settlements、积分流水、奖励/发现/收藏、进度版本变更放在同一事务或使用 Transactional Outbox。
- world_archive 使用 discovery_id 唯一键抢占；首位玩家只获得荣誉，不获得榜单积分。
- 同一业务事件在周榜、月赛季分别产生不同 period_id 的 score_events；幂等唯一键范围为 board_type + period_id + idempotency_key。
- 客户端不得直接提交发现事实、分数、奖励持有状态或机关最终状态。
- 所有配置带 schema_version；加载前校验；未知字段默认拒绝（版本升级时显式迁移）。

## 待定但不阻塞首个垂直切片
- 微信登录正式凭证交换、JWT/会话实现细节。
- 坐标单位、移动速度、碰撞尺寸、法则作用半径/持续时间/冷却。
- 法则组合时间窗、AOI 半径、移动同步频率、断线重连窗口。
- 排行榜积分权重、同分规则、榜单刷新频率。
- 性能预算：最低设备档、目标帧率、P95接口延迟、内存上限、加载时间、压测人数与持续时间。

## 迁移执行
- 测试环境先执行 SQL；检查约束、索引、事务回滚与重复执行保护。
- 生产环境执行前必须备份并在预发验证；迁移工具记录 schema_migrations。
- 该 SQL 是初始工程迁移，不代表已经在真实数据库执行或通过压测。
