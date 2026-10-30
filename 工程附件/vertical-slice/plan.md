# 第一阶段垂直切片开发与测试清单

- 版本：VS-0.1
- 基线：GDD V0.2；Cocos Creator 3.x + TypeScript；Python 3.12+ + FastAPI；PostgreSQL；RabbitMQ
- 目标：端到端验证“登录—共享主地图—进入个人关卡—施放法则—机关解谜—服务端结算—永久进度恢复”。
- 策略：先完成 ROOM-01 可玩闭环，再以配置驱动接入 ROOM-02 至 ROOM-05 与隐藏结局。

## 1. 范围

### 必须包含
- Cocos Creator 3.x 客户端：启动/登录、主地图、移动、交互、法则 UI、个人关卡、结算 UI。
- Python FastAPI 模块化单体：Auth、Player、MapInstance、LevelRun、Rule、Mechanism、Discovery、Settlement、Progress。
- Python 3.12+ + FastAPI；SQLAlchemy 2.x async + asyncpg；Alembic 管理 PostgreSQL 迁移 0001；Pydantic 2.x 校验契约。Redis 首阶段可暂缓，不能作为永久数据唯一来源；RabbitMQ 用于后台异步任务，Worker 独立运行。
- WebSocket AUTH、ENTER/LEAVE、MOVE_SYNC、PING/PONG；机关状态由服务端权威推送。
- ROOM-01 回声显形 HIDEABLE、激活出口。
- 幂等结算、个人发现、world_archive 原子抢占、progress_version 更新。
- 自动化单元/集成测试与本地开发环境。

### 不做
- 正式广告 SDK/广告展示、成就系统、交易/好友/公会。
- 完整赛季发奖后台、排行榜 UI、隐藏结局最终美术。
- 未完成机关状态跨退出恢复；微服务拆分、分库分表。

## 2. 里程碑

| 阶段 | 交付 | 完成定义 |
|---|---|---|
| VS-0 工程骨架 | Cocos 项目、Python 服务端、配置/日志/环境变量、Docker Compose（PostgreSQL、RabbitMQ、API、Worker） | 本地启动、健康检查通过 |
| VS-1 身份与持久化 | 登录适配、players、角色初始化、数据库迁移 | 新玩家创建幂等；重复登录同一玩家 |
| VS-2 共享主地图 | 地图实例、WS鉴权、进入/离开、移动同步 | 两客户端互相看到移动；断线可重新进入 |
| VS-3 个人关卡 | level enter/run、ROOM-01 场景、个人机关状态 | 两玩家同时进入独立 run，互不影响 |
| VS-4 核心玩法 | 回声法则、显形目标、出口机关状态机 | 服务端校验输入并广播权威状态 |
| VS-5 发现与结算 | discovery、world_archive、settlements、score_events、进度快照 | 结算幂等；重登后永久进度可见 |
| VS-6 联调验收 | 真机包、自动化报告、性能/断线测试 | 本文验收项通过或阻塞缺陷有负责人 |

## 3. 客户端任务（Cocos Creator 3.x）
- [ ] 建立 core、network、player、world、level、rules、ui 模块。
- [ ] REST client：鉴权、X-Request-Id、超时、错误映射。
- [ ] WebSocket client：AUTH 首包、seq/ack、心跳、重连、消息 schema 校验。
- [ ] 移动状态机；客户端预测仅用于表现，服务端位置权威。
- [ ] 法则施放输入与冷却 UI；回声命中后显形反馈。
- [ ] 关卡目标/机关表现由配置和服务端状态驱动，不硬编码完成条件。
- [ ] 加载、断网、重连、结算与错误状态。

## 4. 服务端任务
- [ ] 建立 Python 模块化单体：app/api、core、schemas、services、repositories、realtime、workers、tests。\n- [ ] 使用 FastAPI + Uvicorn；Pydantic 2.x 模型与 OpenAPI 契约保持一致。\n- [ ] 使用 SQLAlchemy 2.x async + asyncpg；Alembic 管理迁移，事务边界显式定义。\n- [ ] WebSocket 处理器采用 async I/O；CPU 密集计算不得阻塞事件循环，必要时移交进程池/后台任务。\n- [ ] 部署 RabbitMQ 与 Python Worker；定义任务消息 schema、持久化队列/消息、手动 ACK、有限重试与 dead-letter queue。
- [ ] 仅将可异步化的耗时工作投递到队列；消费者必须幂等，消息确认发生在业务处理成功之后；关键业务写入与消息发布采用 Transactional Outbox，避免数据库提交成功但消息丢失。
- [ ] 玩家身份只从认证上下文取得；校验账号状态。
- [ ] REST 写请求验证 schema、频率限制与幂等键。
- [ ] WS 方向白名单、序列号、速率限制、AOI 广播。
- [ ] level_run 归属检查；机关状态通过 (run_id, player_id) 复合外键隔离。
- [ ] 玩法事件由服务端推导 discovery；客户端不能直接写发现事实。
- [ ] 结算事务：锁定 run → settlement → 发现/收藏 → world_archive INSERT ON CONFLICT → 积分流水 → progress_version + 1 → snapshot。
- [ ] 周榜/月赛季分别写 period_id；全服首发现仅荣誉，不计分。
- [ ] 幂等重试返回首次成功结果；同键不同请求体返回 409。

## 5. 测试清单

### 数据库
- [ ] 空库执行 0001 成功并登记迁移版本。
- [ ] 外键、枚举、CHECK、唯一约束正反例测试。
- [ ] 同一玩家重复进入同一关卡生成不同 run_id。
- [ ] 同一机关配置在不同 run 可独立保存；同 run 重复配置被拒绝。
- [ ] 玩家 A 无法读写玩家 B 的 run、发现、奖励或进度。
- [ ] 并发抢占同一 world_archive.discovery_id 只产生一个首位。
- [ ] score_events 同榜同周期幂等键重复被拒绝；不同周期允许独立写入。
- [ ] 广告/付费/世界首发现不产生榜单流水。
- [ ] 结算失败时事务回滚，不留下部分副作用。

### REST / WebSocket
- [ ] 无 token、封禁玩家的请求被拒绝。
- [ ] 副作用请求缺少 Idempotency-Key 时被拒绝。
- [ ] 同键同请求体重试返回同一结果；同键不同请求体返回 409。
- [ ] 未 AUTH 即发送 MOVE_SYNC 时断开。
- [ ] C2S 伪造 MECH_STATE 被拒绝。
- [ ] MOVE_SYNC 越界、超频、乱序被丢弃或限流。
- [ ] AOI 外玩家不收到无关广播。
- [ ] 重连重新鉴权并获得在线快照；未完成谜题临时状态不恢复。

### 玩法与关卡
- [ ] ROOM-01 回声命中范围内目标后显形。
- [ ] 未命中、冷却中、目标禁用时不改变机关状态。
- [ ] 出口前置目标未完成时拒绝开启。
- [ ] 同一 run 客户端状态一致，不同 run 不串状态。
- [ ] 未完成退出后重新进入创建新 run。
- [ ] 重复结算不重复产生发现、积分、奖励。
- [ ] 五个 room_index 唯一且恰好 1–5；隐藏关卡 room_index=null。
- [ ] HIDDEN-ROUTE-01 缺失、禁用、前置房间不齐或组合序列错误时不能解锁。
- [ ] 前置条件满足且路线启用时，LV-HIDDEN-01 可进入独立 run。

### 永久进度与排行榜
- [ ] 重登后角色、发现、收藏、已完成关卡、奖励保持。
- [ ] 未完成机关状态不要求恢复，永久数据不受影响。
- [ ] 可计分事件按周榜/月赛季分别入账。
- [ ] world_archive 首位记录不产生任何榜单积分。
- [ ] score_events 只追加；纠错通过新流水完成。

### 真机与质量
- [ ] 微信开发者工具、低档 Android、iPhone 完成冒烟。
- [ ] 首屏加载、场景切换、帧率、内存、网络延迟建立基线。
- [ ] 20 在线玩家作为初始压测目标，不作为硬容量承诺。
- [ ] 断网、切后台、重启、网络切换场景完成恢复测试。
- [ ] 关键链路可通过 request_id 与 idempotency_key 追踪。

## 6. 演示脚本
1. A、B 登录并出现在同一主地图。
2. A 进入 ROOM-01，B 留在主地图。
3. A 施放回声，隐藏目标显形；服务端确认并推送机关状态。
4. A 激活出口并完成关卡，服务端幂等结算。
5. A 退出重登，已完成关卡与发现保持。
6. A 重放同一 settle 请求，不产生第二份积分/奖励/发现。
7. B 进入 ROOM-01，机关初始状态与 A 的历史 run 隔离。

## 7. 发布门槛
- P0：跨玩家数据泄露、重复结算/奖励、客户端伪造完成、世界首发现竞争错误，任一存在均禁止推进。
- P1：断线重连、弱网、设备性能、加载问题必须有修复计划。
- 自动化测试、真机冒烟、迁移回滚演练通过后，才标记垂直切片完成。
