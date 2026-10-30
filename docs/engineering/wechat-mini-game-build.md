# 微信小游戏构建与联调手册

- 适用工程：无界之外（Beyond the Unknown）
- 客户端：Cocos Creator 3.8.8 + TypeScript
- 服务端：Python 3.12+ / FastAPI / PostgreSQL / RabbitMQ / Redis
- 当前状态：工程原型已提交；本手册描述本地构建与真实微信联调步骤，不代表已在 Cocos 编辑器、微信开发者工具或真机上完成验证。

## 1. 使用哪个微信测试账号

本项目是**微信小游戏**，构建时应使用此前提供的“小游戏测试号”AppID，而不是另一个通用“小程序测试号”AppID。客户端构建配置只需要 AppID；AppSecret 只能放在服务端环境变量中。

此前 AppSecret 已经出现在聊天内容中。正式联调前应在微信平台轮换测试密钥，再把新密钥写入本地服务端环境文件。不要将 AppSecret、微信 session_key、JWT 私钥或内部审核 API Key 写入客户端、仓库、日志、截图或提交记录。

## 2. 准备服务端

在仓库根目录执行：

```bash
cp server/.env.example server/.env
```

编辑 `server/.env`，至少配置以下值：

- `WECHAT_APP_ID`：小游戏测试号 AppID。
- `WECHAT_APP_SECRET`：轮换后的小游戏测试号 AppSecret。
- `JWT_SECRET`：独立随机值，至少 32 字符。
- `OPENID_HMAC_SECRET`：与 JWT_SECRET 不同的独立随机值，至少 32 字符。
- `INTERNAL_API_KEY`：独立随机值；用于内部赛季审核接口，不能交给客户端。
- `SERVER_TIMEZONE`：赛季周/月周期使用的 IANA 时区；默认 UTC。上线前由运营环境明确选择，数据库仍统一保存 UTC。
- `SEASON_REVIEW_WINDOW_SECONDS`：默认 600 秒。

启动服务并应用迁移：

```bash
docker compose --env-file server/.env up --build -d
docker compose --env-file server/.env run --rm api uv run --no-sync alembic -c alembic.ini upgrade head
docker compose --env-file server/.env ps
```

检查：

- API liveness：`http://localhost:8000/health/live`
- API readiness：`http://localhost:8000/health/ready`
- OpenAPI：`http://localhost:8000/docs`
- RabbitMQ 管理界面：`http://localhost:15672`

本地环境的默认数据库和 RabbitMQ 凭证仅用于开发，部署前必须替换。不要把本地开发密码复用到公网环境。

## 3. 打开并构建 Cocos Creator 工程

1. 安装 Cocos Creator **3.8.8**。
2. 在 Cocos Creator 项目管理器中选择“打开其他项目”，打开仓库中的 `client/` 目录。
3. 等待资源导入完成，确认 `assets/scenes/Boot.scene` 能正常打开。
4. 在构建面板选择微信小游戏平台。
5. AppID 填入第 1 节所说的小游戏测试号 AppID。
6. 构建输出目录建议使用 `build/wechatgame`；构建后不要把带有本地密钥的配置文件提交到 Git。
7. 使用微信开发者工具导入构建输出目录，选择小游戏项目类型。

当前仓库中的 Boot 场景是几何占位原型，不是最终美术场景。Node CI 已验证场景 JSON 可解析、脚本 UUID 与 `GameEntry.ts.meta` 一致；这不能替代 Cocos 编辑器实际导入与构建。

## 4. 配置 API 与 WebSocket 地址

选中 Boot 场景中的 `BeyondTheUnknownGameEntry` 组件，在 Inspector 中配置：

- `apiBaseUrl`
- `websocketBaseUrl`

本地微信开发者工具调试默认值：

- API：`http://127.0.0.1:8000/api/v1`
- WebSocket：`ws://127.0.0.1:8000`

这两个地址只适合开发者工具与本机服务端联调。**真实手机不能把 127.0.0.1 当成开发电脑地址**。真机/线上环境必须使用公网可访问、证书有效的 HTTPS 与 WSS 域名，并在微信平台配置 request/socket 合法域名。不要通过关闭域名校验来替代生产域名配置。

微信开发者工具的“忽略合法域名、TLS 版本及 HTTPS 证书校验”仅可用于本地临时调试，不得作为上线配置。

## 5. 首轮联调顺序

1. 启动 PostgreSQL、RabbitMQ、Redis、API、Worker，确认 readiness 正常。
2. 微信开发者工具运行小游戏，确认 `wx.login` 返回 code，服务端完成 code 换取 openid，客户端获得 JWT。
3. 让两个测试客户端登录，确认同一主地图中的玩家互相可见。
4. 移动一个玩家，确认另一个客户端收到服务端位置同步。
5. 断开一个客户端网络，在服务端 reconnect grace period 内恢复，确认复用原 instance/session。
6. 如使用多 API 节点，确认两个节点连接同一 Redis，跨节点在线快照和事件广播正常；Redis Pub/Sub 是瞬时消息，断线后仍以 PostgreSQL 成员关系和重连握手恢复状态。
7. 进入个人关卡，再放弃返回主地图，确认共享地图席位释放。
8. 调用进度、图鉴、奖励和排行榜接口，确认玩家数据隔离。

## 6. 当前不能误判为已完成的玩法

当前主分支已经具备**服务端权威的几何玩法原型**，但这不等于正式游戏内容或微信真机版本已经完成。

已具备并有自动化覆盖的部分：

- ROOM-01：回声显形、出口前置条件、位置校验、交互幂等和结算闭环。
- ROOM-02～ROOM-05：组合控件、目标机关、法则顺序与持续凝视要求从服务端关卡配置读取；移动出生点、边界、速度、交互半径、位置同步间隔和机关坐标也由关卡配置驱动。
- ROOM-03 能量机关联动门、ROOM-04 平台联动终点机关；ROOM-05 三组组合使用独立 M05 机关 ID。ROOM-04/05 的持续凝视由客户端按服务端租约自动续期。
- 隐藏结局：服务端端到端集成测试已覆盖 ROOM-01～05 完成、ROOM-05 三组组合按序触发、HIDDEN-ROUTE-01 解锁、进入 LV-HIDDEN-01、交互 H01-END 并完成独立 run；客户端结算反馈也会显示隐藏结局已解锁。
- Alembic 0001–0016 在 CI 干净 PostgreSQL/Compose 环境执行；JSON Schema、levels.v1.json、数据库配置和客户端控件之间有自动化契约校验。 Compose smoke 还会对 0016 执行 downgrade -1，验证早期原型配置保留，再 upgrade head 验证同步间隔恢复。
- 法则、组合、机关和关卡目标已有原型数值/坐标配置；这些数值仍须策划体验、调优和签字验收，不能视为最终平衡值。

以下仍未达到正式可玩/发布标准：

- 关卡几何、移动碰撞、机关动画、镜头表现、正式 HUD、反馈特效与结算 UI 尚未完成最终实现和编辑器验收。
- 美术/音效资源清单当前有 112 项，状态均为 `MISSING`；不能将几何占位或文档清单计作正式资源交付。
- Cocos Creator 编辑器实际导入/构建、微信开发者工具构建、Android/iOS 真机联调仍未由 CI 或人工验收证明。
- Redis 多节点 presence/pub-sub 已有实现和双节点集成测试；Redis 生产 HA/TLS/鉴权、故障演练、最终 AOI、生产部署、弱网/负载/安全测试仍未完成。
- 广告 SDK、广告位策略、广告回调验签、频控、隐私合规与运营配置尚未接入。

因此，当前可以准确表述为：**服务端五房间几何玩法原型已接入，客户端已有配置驱动的操作入口；尚不能宣称 Cocos 编辑器和微信真机上的完整游戏已经可玩。**

## 7. 发布前检查

- [ ] 轮换此前暴露过的测试 AppSecret。
- [ ] 生产环境使用独立数据库、RabbitMQ 用户密码、JWT_SECRET、OPENID_HMAC_SECRET 和 INTERNAL_API_KEY。
- [ ] API/Socket 域名使用 HTTPS/WSS、有效 TLS 证书并完成微信合法域名配置。
- [ ] 完成 Cocos 编辑器导入、微信开发者工具构建和真机冒烟。
- [ ] 完成法则/机关/关卡内容配置与策划验收。
- [ ] 完成赛季时区、积分权重、奖励档位与审核流程配置。
- [ ] 完成 RabbitMQ 故障恢复、重复投递、DLQ 恢复演练。
- [ ] 完成 Redis 生产 HA/TLS/鉴权与多节点故障演练。
- [ ] 完成 AOI、性能、安全、隐私与小游戏平台审核。
