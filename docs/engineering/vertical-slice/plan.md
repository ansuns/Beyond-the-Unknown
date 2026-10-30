# 第一阶段垂直切片开发与测试清单

- 版本：VS-6A.1
- 状态：VS-0 至 VS-5 服务端基础、权威法则、发现/结算/奖励/排行榜已合并并通过 CI；客户端 REST/WebSocket、个人关卡/法则/进度会话已合并或进入 CI；Cocos Creator 3.8.8 Boot 几何原型已合并。正式机关/法则数值、关卡玩法表现、Cocos 编辑器导入、微信构建与真机联调仍未完成
- 基线：GDD V0.2；Cocos Creator 3.x + TypeScript；Python 3.12+ + FastAPI；PostgreSQL；RabbitMQ
- 目标：端到端验证“登录—共享主地图—进入个人关卡—施放法则—机关解谜—服务端结算—永久进度恢复”。
- 策略：先完成 ROOM-01 可玩闭环，再以配置驱动接入 ROOM-02 至 ROOM-05 与隐藏结局。

## 1. 范围

### 必须包含
- Cocos Creator 3.x 客户端：启动/登录、主地图、移动、交互、法则 UI、个人关卡、结算 UI。
- Python FastAPI 模块化单体：Auth、Player、MapInstance、LevelRun、Rule、Mechanism、Discovery、Settlement、Progress。
- Python 3.12+ + FastAPI；SQLAlchemy 2.x async + asyncpg；Alembic 管理 PostgreSQL 迁移 0001–0008；Pydantic 2.x 校验契约。Redis 首阶段可暂缓，不能作为永久数据唯一来源；RabbitMQ 用于后台异步任务，Worker 独立运行。
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
| VS-0 工程骨架 | Python 服务端、配置/环境变量、Docker Compose（PostgreSQL、RabbitMQ、API、Worker） | 服务端骨架已完成；Cocos Creator 3.8.8 项目骨架与 Boot 场景已提交，编辑器导入/构建验证待完成 |
| VS-1 身份与持久化 | 微信 code 服务端交换、players、12个角色初始化、JWT、玩家/角色 API、迁移与测试 | 服务端已完成；客户端 wx.login、玩家资料/角色目录/选角 REST 调用已完成；角色选择 UI 待做 |
| VS-2 共享主地图 | 地图实例分配、WS鉴权、ENTER/LEAVE、MOVE_SYNC、动作广播、心跳与重连保留 | 服务端单进程原型已合并；客户端 WebSocket/MapSession/WorldPlaySession 已合并；自动重连、移动表现、精细 AOI 与 Redis 多节点仍待完成 |
| VS-3 个人关卡 | levels目录、个人run创建/开始/放弃、进入幂等与主地图席位释放 | 后端接口与迁移已合并；客户端 PersonalLevelSession/WorldPlaySession 可进入并启动个人 run；ROOM-01 场景与结算仍待做 |
| VS-4 核心玩法 | 法则目录、权威施法、冷却/持续效果、三组预设组合、个人机关状态机 | 服务端规则目录、权限/目标/范围校验、冷却/注视租约、机关状态隔离与三组组合已合并；客户端 LawController 已接入并通过 CI；数值/坐标仍为 TUNING_REQUIRED，场景表现待做 |
| VS-5 发现与结算 | discovery、world_archive、settlements、score_events、进度快照、奖励与三榜 | 服务端已合并并通过迁移/集成/Compose CI；积分权重、正式奖励定义和部分目标内容仍待配置 |
| VS-6 联调验收 | 真机包、自动化报告、性能/断线测试 | 本文验收项通过或阻塞缺陷有负责人 |

## 3. 客户端任务（Cocos Creator 3.x）
- [x] 建立 TypeScript core/network/player/world 基础模块；level/rules/ui 随后续玩法切片增加。
- [x] REST client：Bearer 鉴权、X-Request-Id、超时、错误映射（客户端基础）。
- [x] 玩家资料、角色目录与角色选择 REST API；服务端返回的解锁/当前角色为权威状态。
- [x] WorldPlaySession：共享地图进入、角色/关卡数据加载、个人 run 启动、法则会话和地图移动/动作/心跳的应用层编排。
- [x] LawController：根据服务端 READY/解锁状态控制施法，校验点/物体目标输入形状，按服务端 lease_timeout 维护 GAZE，并缓存个人机关状态。
- [x] WebSocket client：AUTH 首包、单调 seq、消息 envelope 校验、心跳/移动/动作/离开命令；意外断线后复用原 instance/session，在服务端 grace period 内指数退避重连；主动离开不重连。
- [ ] 移动状态机；客户端预测仅用于表现，服务端位置权威。
- [ ] 法则施放输入与冷却 UI；回声命中后显形反馈。
- [x] Cocos Creator 3.8.8 项目结构、Boot 场景、微信登录/共享地图/远端占位角色/点击移动/个人房间进入与放弃的几何原型。
- [ ] Cocos 编辑器实际导入、场景序列化、目标 hit-testing、机关动画/音效与 HUD；微信开发者工具构建和真机验证。
- [ ] 关卡目标/机关表现由配置和服务端状态驱动，不硬编码完成条件。
- [ ] 加载、断网、重连、结算与错误状态。

## 4. 服务端任务
- [x] 建立 Python 模块化单体基础：app/api、core、modules/auth、modules/players、modules/characters、schemas、workers、tests。后续按领域增加 map、level、rules 等模块。
- [x] 使用 FastAPI + Uvicorn；VS-1 登录/玩家接口已更新 OpenAPI 契约。
- [x] 使用 SQLAlchemy 2.x async + asyncpg；Alembic 0001/0002 已在 CI 干净 PostgreSQL 上执行。
- [x] VS-2 WebSocket 处理器采用 async I/O；CPU 密集计算不得阻塞事件循环。当前连接管理器仅支持单 API 进程，水平扩展前必须接入 Redis presence/pub-sub。
- [x] RabbitMQ 与 Python Worker：版本化任务 envelope、持久化队列/消息、Publisher Confirms、手动 ACK、数据库记录的有限指数退避重试与 DLQ（VS-6A）。
- [x] 赛季周期到期与结算任务通过 PostgreSQL task_outbox 同事务写入；Relay 仅在 RabbitMQ publisher confirm 后标记 PUBLISHED；Worker 使用 worker_task_receipts 幂等处理（VS-6A）。
- [ ] 其他未来异步业务副作用按需接入同一 Outbox/幂等消费者模式；当前关卡结算主体仍在 API 数据库事务内同步完成。
- [x] 玩家身份只从 JWT 认证上下文取得；每个受保护请求查询账号状态，封禁账号立即拒绝。
- [ ] REST 写请求验证 schema、频率限制与幂等键。
- [x] WS 首包 AUTH、消息序列号、方向/动作白名单、MOVE/ACTION 频率限制；当前 AOI 使用同实例全可见回退，精确半径/网格待联调。
- [x] level_run 归属检查；机关状态通过 (run_id, player_id) 复合外键隔离。
- [x] VS-3：levels目录、入口校验、level_enter_requests业务幂等、单玩家单活跃run、CREATED/RUNNING/ABANDONED状态流转。
- [x] VS-4：服务端 rule_catalog / combo_catalog / player_unlocked_rules；施法验证 run 归属、法则权限、冷却、目标类型/范围、幂等键；机关状态按 (run_id, player_id, mechanism_config_id) 隔离。
- [x] VS-4：回声显形、注视维持/中断、逆流反转/超时恢复；组合顺序/时间窗校验与机关状态机联动（正式数值/坐标仍待配置）。
- [x] 玩法事件由服务端推导 discovery；客户端不能直接写发现事实。
- [x] 结算事务：锁定 run → settlement → 发现/收藏 → world_archive INSERT ON CONFLICT → 积分流水 → progress_version + 1 → snapshot。
- [x] 周榜/月赛季分别写 period_id；全服首发现仅荣誉，不计分。
- [x] 结算重试返回同一结果；跨 run 复用同一结算幂等键返回 409。

## 5. 测试清单

### 数据库
- [x] 空库执行 0001–0008 成功并登记迁移版本；0008 增加赛季审核字段、task_outbox 与 worker_task_receipts。
- [ ] 外键、枚举、CHECK、唯一约束正反例测试。
- [ ] 同一玩家重复进入同一关卡生成不同 run_id。
- [ ] 同一机关配置在不同 run 可独立保存；同 run 重复配置被拒绝。
- [ ] 玩家 A 无法读写玩家 B 的 run、发现、奖励或进度。
- [ ] 并发抢占同一 world_archive.discovery_id 只产生一个首位。
- [ ] score_events 同榜同周期幂等键重复被拒绝；不同周期允许独立写入。
- [ ] 广告/付费/世界首发现不产生榜单流水。
- [ ] 结算失败时事务回滚，不留下部分副作用。

### REST / WebSocket
- [x] 无效/过期 token 与封禁玩家的请求被拒绝（VS-1 集成测试）。
- [ ] 副作用请求缺少 Idempotency-Key 时被拒绝。
- [ ] 同键同请求体重试返回同一结果；同键不同请求体返回 409。
- [x] WebSocket AUTH 后才允许 ENTER/MOVE/ACTION；双连接集成测试覆盖同实例广播。
- [x] C2S 伪造 MECH_STATE 被拒绝（服务端只接受白名单协议消息，不接受客户端写入机关状态）。
- [x] MOVE_SYNC 非法坐标/方向、超速、超频和乱序输入由服务端拒绝或丢弃；逻辑地图边界仍待地图资源确定。
- [ ] AOI 半径/网格与边界测试（当前原型采用同实例全可见回退，不代表最终 AOI）。
- [x] 重连重新鉴权并校验 membership session；保留期内获得同实例在线快照。未完成谜题临时状态不恢复。

### 玩法与关卡
- [ ] ROOM-01 回声命中范围内目标后显形。
- [ ] 未命中、冷却中、目标禁用时不改变机关状态。
- [ ] 出口前置目标未完成时拒绝开启。
- [ ] 同一 run 客户端状态一致，不同 run 不串状态。
- [ ] 未完成退出后重新进入创建新 run。
- [x] 重复结算不重复产生发现、积分、奖励（VS-5 集成测试）。
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


## 8. VS-6A 赛季结算与异步任务闭环（已合并 PR #52）
- [x] 赛季边界扫描：worker 按 SERVER_TIMEZONE 创建周/月周期并发现到期 ACTIVE 周期。
- [x] Transactional Outbox：业务事务写入 task_outbox，RabbitMQ relay 使用持久化消息与 publisher confirms。
- [x] Worker task receipt：task_id/idempotency_key 数据库去重，重复投递不重复执行结算。
- [x] 赛季最终快照：三榜分别聚合 score_events 并写 leaderboard_snapshots。
- [x] REVIEW 审核期：到期赛季进入 SETTLING/REVIEW，review_until_utc 可配置。
- [x] 内部审核接口：API Key 保护 APPROVE/REJECT；无审核动作时到期自动批准。
- [x] 排名奖励：按 SEASON_RANK 条件授予非付费外观/称号/宠物/徽章，发放幂等。
- [x] Worker 有限指数退避重试；超过最大次数后进入 RabbitMQ DLQ，并保留 FAILED outbox 记录。
- [ ] RabbitMQ 真实服务故障/重启、发布确认丢失、重复投递、DLQ 恢复演练。
- [ ] 赛季审核窗口内的积分纠错流水及重算审批；当前支持批准/驳回，尚未开放纠错写接口。
- [ ] 正式积分权重、排名奖励档位和时区配置由策划/运维确认后启用。
- [ ] Cocos 编辑器导入、场景 hit-testing/HUD/动画、微信开发者工具与真机联调。
