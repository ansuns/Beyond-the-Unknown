# 工程落地附件（V0.1）

- 项目：无界之外 / Beyond the Unknown
- 基线：GDD V0.2；Cocos Creator 3.x + TypeScript；Node.js + TypeScript；PostgreSQL；WebSocket
- 状态：工程实现基线草案，需随代码评审迭代
- 日期：2026-10-30

## 目录
- `database/0001_initial_schema.sql`：PostgreSQL 初始结构迁移
- `api/openapi.yaml`：REST API OpenAPI 3.1 契约
- `realtime/websocket.schema.json`：WebSocket 消息 JSON Schema
- `levels/level.schema.json`：关卡配置 Schema
- `levels/levels.v1.json`：五个常规房间与隐藏结局配置
- `vertical-slice/plan.md`：第一阶段垂直切片计划与验收清单
- `decisions.md`：技术决策、边界与待定项

## 使用约定
1. API、消息与关卡配置均以契约文件为准；修改时同步更新版本和兼容性说明。
2. 数据库迁移只允许向前追加；已应用迁移不得原地改写。
3. SQL 使用 UTC 的 `timestamptz`；周期边界由服务器配置时区计算。
4. 玩家身份只从认证上下文取得，客户端传入的 player_id 一律忽略。
5. 所有有副作用请求必须使用 `Idempotency-Key`；`request_id` 仅用于追踪。
6. 首期不接入广告 SDK、不实现成就系统；预留数据边界。
