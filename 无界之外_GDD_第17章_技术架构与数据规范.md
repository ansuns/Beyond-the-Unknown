# 《无界之外》GDD V0.2

## 第17章 技术架构与数据规范

## 变更日志

| 版本 | 日期 | 变更内容 |
|---|---|---|
| V0.1 | 2026-10-30 | 建立技术架构与数据规范初稿 |
| V0.2 | 2026-10-30 | 统一个人发现/收藏/机关状态/奖励/成就/积分/进度数据字典；补齐业务接口映射 |

-   **文档版本：** GDD V0.2
-   **章节版本：** 第17章 V0.2
-   **日期：** 2026-10-30
-   **适用岗位：** 服务端程序、客户端程序、技术美术、DevOps、测试、系统策划
-   **章节状态：** V0.2修订稿（待技术评审）
-   **优先级标记：**【MVP必须】、【可选扩展】、【不在本期范围】

------------------------------------------------------------------------

### 17.0 本章范围与技术基线

本章定义《无界之外》微信小游戏的技术架构、模块划分、数据库表结构、接口与消息协议、权限校验、断线恢复、备份安全、日志监控等规范，为程序开发与联调提供基线。

本章不定义具体玩法数值（见第2–15章）、UI视觉规范（见第16章）与美术资源制作规格（见第18章）。

**技术基线（建议方案，待最终确认）：**

  类别          建议方案
  ------------- ------------------------------------------------
  客户端引擎    Cocos Creator 3.x（建议，待最终确认）
  客户端语言    TypeScript
  服务端语言    Node.js + TypeScript
  实时通信      WebSocket
  关系数据库    PostgreSQL
  缓存          Redis
  异步任务      BullMQ
  部署          Docker
  后端架构      模块化单体（建议，待最终确认）

说明：以上技术选型均为建议方案，最终以技术评审与压测结论为准，不在本章固化为不可变更约束。凡涉及性能、容量、分库分表的硬指标，统一标注「待压测确定 / 待最终确认」。

------------------------------------------------------------------------

## 17.1 系统架构图

**优先级：【MVP必须】**

### 【功能说明】

描述客户端到服务端、数据层与异步任务层的总体拓扑，明确各组件职责边界（建议方案，待最终确认）。

### 【系统架构图】

``` mermaid
flowchart LR
    C["客户端 Cocos Creator 3.x / TS"] -->|HTTPS REST| GW["API网关 / 鉴权"]
    C -->|WebSocket| WS["WebSocket网关"]
    GW --> SVC["游戏服务（模块化单体）"]
    WS --> SVC
    SVC --> PG["PostgreSQL"]
    SVC --> RD["Redis 缓存/会话"]
    SVC --> MQ["BullMQ 异步任务"]
    MQ --> SVC
    SVC --> OSS["对象存储（资源/CDN）"]
    PG --- BAQ["备份与审计"]
    RD --- BARD["持久化/AOF"]
```

### 【组件职责】

  组件            职责
  --------------- --------------------------------------------------
  客户端          渲染、输入、本地预测、资源加载
  API网关         鉴权、限流、路由REST请求
  WebSocket网关   长连接管理、消息上行下行
  游戏服务        登录、地图实例、关卡、法则、机关、发现、排行榜等
  PostgreSQL      玩家/角色/地图/关卡/排行等持久化数据
  Redis           会话、在线状态、排行榜缓存、限流计数
  BullMQ          结算重试、赛季结算、奖励发放等异步任务
  对象存储        美术/音频资源与CDN分发

------------------------------------------------------------------------

## 17.2 模块划分

**优先级：【MVP必须】**

### 【功能说明】

明确客户端与服务端的功能模块边界，便于并行开发与接口对齐（建议方案，待最终确认）。

### 【客户端模块】

  模块            职责
  --------------- --------------------------------------------------
  启动/登录       微信登录、初始化、资源预载
  角色            角色选择、模型/动画加载（第3章）
  地图            主地图渲染、斜45度投影、摄像机（第4章）
  移动            虚拟摇杆、状态机、碰撞（第2章2.5/第3章3.4）
  交互            入口/机关/物体交互按钮（第9章/16章）
  法则            三条法则触发与特效（第7章）
  关卡            个人探索关卡运行（第6章）
  社交            动作/表情广播（第3章3.7/第14章）
  结算/图鉴       结算界面、收藏图鉴（第10章/11章）
  排行榜          UI展示（第13章）
  网络            WebSocket连接、断线重连（第5章）
  资源            资源加载、占位与缺失日志（第18章）

### 【服务端模块】

  模块            职责
  --------------- --------------------------------------------------
  登录            微信凭证校验、玩家初始化（第2章2.2）
  地图实例        实例创建/分配/容量控制（第4章4.6/4.7）
  关卡            个人关卡运行实例与结算（第2章2.8）
  法则            法则效果计算与校验（第7章）
  机关            机关状态与触发（第9章）
  发现            隐藏发现记录与去重（第10章）
  排行榜          三榜计算与赛季排名（第13章）
  赛季            周榜/月赛季周期与结算（G-013）
  奖励            外观/称号/宠物/徽章发放（第12章）
  社交            动作/表情事件广播（第14章）
  广告            接口预留，暂不开（G-016/第15章）

------------------------------------------------------------------------

## 17.3 数据库表结构（V0.2统一数据字典）

**优先级：【MVP必须】**

### 【功能说明】

本节为跨章节唯一权威数据字典。第10–13章描述业务语义，本节定义落库字段、主键、唯一约束和索引；如旧段落或其他章节的示例字段与本节不一致，以本节为准。下列为逻辑模型，PostgreSQL物理类型可在技术评审后映射；所有时间字段统一使用timestamptz（UTC）。

### 【核心关系与字段】

#### players（玩家账号）
- player_id uuid PK
- wx_openid varchar UNIQUE；仅服务端保存，不下发客户端
- current_character_id varchar nullable
- progress_version bigint；进度版本号/乐观锁
- status enum NORMAL/BANNED
- created_at、updated_at timestamptz UTC

不设置跨榜单的total_score权威字段。三榜分数分别按score_events.board_type + period_id汇总；展示缓存可重建，不得作为积分权威来源。

#### player_characters（玩家已解锁角色）
- player_id uuid FK players
- character_id varchar FK characters
- unlocked_at timestamptz UTC
- source varchar DEFAULT/REWARD/EVENT
- PK(player_id, character_id)

#### level_runs（个人关卡运行）
- run_id uuid PK
- player_id uuid FK players
- level_id varchar
- instance_id uuid nullable
- status enum CREATED/RUNNING/COMPLETED/FAILED/ABANDONED
- started_at、ended_at timestamptz UTC
- completion_time_ms bigint nullable
- result_id uuid nullable
- created_at timestamptz UTC
- INDEX(player_id,status), INDEX(player_id,created_at)

同一玩家的历史运行记录不得覆盖。退出时永久保存已确认的发现、收藏、奖励、积分和已完成关卡；首期不承诺恢复尚未结算的机关/谜题临时状态，见第6章与第11章。

#### mechanism_states（个人机关运行状态）
- mechanism_state_id uuid PK
- run_id uuid FK level_runs
- player_id uuid FK players，必须与run归属一致
- mechanism_config_id varchar
- mechanism_type varchar
- state jsonb
- updated_at timestamptz UTC
- UNIQUE(run_id, mechanism_config_id)

不得以mechanism_config_id单独作为主键；相同机关配置在不同玩家run中必须分别保存。

#### discovery_catalog（发现内容配置）

- discovery_id varchar PK；全服唯一发现ID
- discovery_type varchar；DIS_HIDDEN_OBJ/DIS_HIDDEN_AREA/DIS_RULE_EFFECT/DIS_COMBO/DIS_PUZZLE/DIS_ENDING
- level_id varchar nullable
- location jsonb；地图/区域配置定位
- related_rule varchar nullable
- display_name varchar
- is_enabled boolean
- UNIQUE(discovery_id)

#### collection_catalog（图鉴藏品配置）

- collection_id varchar PK
- codex_category varchar CAT_AREA/CAT_RULE/CAT_CREATURE/CAT_RELIC/CAT_ENDING
- source_discovery_id varchar nullable FK discovery_catalog
- display_name varchar
- description text
- asset_id varchar nullable
- sort_order integer
- is_enabled boolean

#### player_discoveries（玩家个人发现）
- player_id uuid FK players
- discovery_id varchar；第10章全局发现配置ID
- discovery_type varchar
- level_id varchar nullable
- run_id uuid nullable FK level_runs
- location jsonb；地图/关卡/区域定位
- related_rule varchar nullable
- first_discovered_at timestamptz UTC
- trigger_count integer DEFAULT 1
- PK(player_id, discovery_id)

#### player_collections（玩家收藏）
- player_id uuid FK players
- collection_id varchar
- codex_category varchar CAT_AREA/CAT_RULE/CAT_CREATURE/CAT_RELIC/CAT_ENDING
- source varchar DISCOVERY/SETTLEMENT/REWARD
- source_id varchar
- obtained_at timestamptz UTC
- PK(player_id, collection_id)

#### world_archive（世界传奇档案）
- discovery_id varchar PK；全服每个发现仅一条
- first_player_id uuid FK players
- first_discovered_at timestamptz UTC
- location jsonb NOT NULL；world/map/level/region定位
- related_rule varchar nullable
- created_at timestamptz UTC

全服首次采用数据库原子插入/唯一键冲突判定；并发事件只允许一名玩家成为首位。档案永久保留。首次发现只授予荣誉标记/展示，不增加任何排行榜积分。

#### score_events（三榜积分不可变流水）
- event_id uuid PK
- player_id uuid FK players
- board_type enum EXPLORE/CLEAR/COLLECT
- period_id varchar；周榜或月赛季周期ID，同一上游事件在当前周榜与月赛季各写一条独立流水
- delta bigint；正常业务非负，纠错使用反向追加流水
- reason varchar；仅EXP_DISCOVER/CLEAR_STAGE/COLLECT_NEW，不含WORLD_FIRST
- source_event_id varchar
- run_id uuid nullable
- idempotency_key varchar NOT NULL
- created_at_utc timestamptz UTC
- UNIQUE(board_type, period_id, idempotency_key)
- INDEX(player_id, board_type, period_id, created_at_utc)

流水仅追加，不更新/删除；重算以流水为唯一权威来源。广告、付费、全服首次荣誉事件不得写入积分流水。

#### seasons / leaderboard_snapshots（赛季与榜单快照）
- seasons：season_id PK、season_type WEEKLY/MONTHLY、start_at_utc、end_at_utc、status、settlement_status、settled_at_utc
- leaderboard_snapshots：season_id、board_type、player_id、score、rank、snapshot_at_utc；UNIQUE(season_id,board_type,player_id)

#### rewards（奖励配置）
- reward_id varchar PK
- reward_type enum RT_APPEARANCE/RT_TITLE/RT_PET/RT_BADGE/RT_ACHIEVE
- reward_name varchar
- condition varchar；第11章condition_id引用
- grant_mode enum AUTO/CLAIM
- payload jsonb
- is_paid boolean
- is_enabled boolean

#### player_rewards（玩家奖励持有/待领取）
- player_reward_id uuid PK
- player_id uuid FK players
- reward_id varchar FK rewards
- grant_mode enum AUTO/CLAIM
- status enum OWNED/PENDING_CLAIM
- source varchar；ACHIEVEMENT/SEASON/EVENT等
- source_id varchar
- idempotency_key varchar NOT NULL
- granted_at timestamptz UTC
- claimed_at timestamptz UTC nullable
- UNIQUE(player_id,reward_id,source_id)

#### achievements / player_achievements（成就配置与个人进度）
- achievements：achievement_id PK、name、condition_ref、progress_rule jsonb、reward_id FK rewards、is_enabled
- player_achievements：player_id FK、achievement_id FK、progress jsonb、status IN_PROGRESS/COMPLETED、completed_at timestamptz；PK(player_id,achievement_id)

#### player_tasks / progress_snapshots / settlements（任务、持久进度与结算）
- player_tasks：player_id、task_id、status、progress jsonb、updated_at；PK(player_id,task_id)
- progress_snapshots：snapshot_id PK、player_id、progress_version、completed_level_ids jsonb、permanent_progress jsonb、created_at；UNIQUE(player_id,progress_version)
- settlements：result_id PK、run_id UNIQUE、player_id、level_id、result_status、completion_time_ms、score_payload jsonb、created_at、idempotency_key UNIQUE

#### ad_reward_grants（广告独立奖励记录）
- ad_grant_id uuid PK
- player_id uuid FK players
- placement_id varchar
- reward_type enum APPEARANCE/HINT；REVIVE_TOKEN仅后续评审后开放
- reward_value varchar
- is_value_bearing boolean，必须false
- provider_transaction_id varchar
- granted_at timestamptz UTC
- idempotency_key varchar UNIQUE

广告奖励独立于player_rewards的成就/赛季发放路径；可在奖励历史并列展示来源，但不得写入score_events。

#### 其他配置与日志表

characters、maps、map_instances、actions_log沿用本章原字段建议。地图实例目标人数20仅为压测目标；max_players由服务端配置，禁止把20写死为硬上限。

### 【索引、约束与事务要求】

1. 所有玩家归属数据必须校验player_id与run_id归属；客户端不得指定或覆盖内部玩家ID。
2. 个人发现、个人收藏、玩家成就、玩家角色均使用复合唯一键保证幂等。
3. 世界档案以discovery_id唯一键原子抢占；首次发现荣誉与档案写入在同一事务或可靠Outbox流程中完成。
4. 结算、积分流水、奖励发放使用业务幂等键；重试不得产生重复副作用。
5. score_events不可变；纠错通过追加反向/调整事件完成，并记录操作审计。
6. 所有时间戳存UTC；赛季边界按服务器配置时区计算，再转换UTC存储。
7. 高写入表索引、分区/分表、连接池和缓存策略待压测确定；首期不预先引入分库分表。
8. 本节为逻辑模型，不是可直接执行的DDL；物理SQL迁移脚本须在技术评审后单独生成。

------------------------------------------------------------------------

## 17.4 API接口规范

**优先级：【MVP必须】**

### 【规范】

-   **风格：** REST（建议，待最终确认）。
-   **Base Path：** `/api/v1`。
-   **认证：** JWT 或会话令牌（建议，待最终确认）；除登录外所有接口需携带有效令牌。
-   **通用响应：** 统一返回 `{ code, message, data, request_id }`；request_id用于单次请求追踪与日志关联。
-   **业务幂等：** 结算、积分入账、奖励发放、发现等有副作用的业务操作必须携带独立的 `idempotency_key`；同一业务事件重试必须复用该键。request_id每次网络重试可变化，不得单独作为业务去重依据。积分键唯一约束见17.3，第11章结算与奖励键也按17.3执行。
-   **频率限制：** 关键写接口服务端限流，具体阈值待压测确定。

### 【主要接口示例】

  接口                      方法   路径                             说明
  ------------------------- ------ -------------------------------- ----------------
  登录/初始化               POST   /api/v1/auth/login              微信凭证换取账号
  角色列表                  GET    /api/v1/player/characters       当前可用角色
  角色选择                  PUT    /api/v1/player/character        确认当前角色
  地图实例进入              POST   /api/v1/map/enter               分配/恢复实例
  关卡进入                  POST   /api/v1/level/enter             创建个人关卡运行
  关卡结算                  POST   /api/v1/level/settle            提交通关结算
  玩法事件/发现校验          内部   /internal/v1/discovery/event    服务端玩法事件触发；客户端不得直接写入发现
  排行榜查询                GET    /api/v1/leaderboard/{type}      三榜查询
  赛季查询                  GET    /api/v1/season                  周/月赛季信息
  奖励列表                  GET    /api/v1/reward                 已拥有/待领取奖励
  奖励领取                  POST   /api/v1/reward/claim            领取奖励
  个人发现列表              GET    /api/v1/discovery               个人发现记录
  个人收藏列表              GET    /api/v1/collection              收藏图鉴
  世界传奇档案              GET    /api/v1/world-archive           全服首次发现列表
  成就进度（扩展）          GET    /api/v1/achievement             启用成就后查询

### 【请求/响应字段示例：登录初始化】

请求：

``` json
{
  "wx_code": "string",
  "request_id": "string"
}
```

响应：

``` json
{
  "code": 0,
  "message": "ok",
  "data": {
    "player_id": "string",
    "character_id": "string/null",
    "is_new_player": true,
    "progress_version": 1,
    "server_time": 1762000000
  },
  "request_id": "string"
}
```

### 【请求/响应字段示例：关卡结算】

请求：

``` json
{
  "run_id": "string",
  "request_id": "string"
}
```

响应：

``` json
{
  "code": 0,
  "message": "ok",
  "data": {
    "result_id": "string",
    "level_id": "string",
    "completion_time": 42,
    "completion_score": 100,
    "discoveries": [],
    "collections": [],
    "result_status": "COMPLETED"
  },
  "request_id": "string"
}
```

------------------------------------------------------------------------

## 17.5 WebSocket消息协议

**优先级：【MVP必须】**

### 【规范】

-   **传输：** WebSocket（建议，待最终确认）。
-   **消息信封：** 统一结构 `cmd + payload + ts`，示例：`{ "cmd": "MOVE_SYNC", "payload": {...}, "ts": 1762000000 }`。
-   **方向：** `C2S` 客户端→服务端；`S2C` 服务端→客户端。
-   **鉴权：** 连接建立后必须先发送鉴权包，未通过则断开。
-   **压缩/分帧：** 具体策略待技术评审确定。

### 【消息类型表】

  消息类型      方向    说明
  ------------- ------- ------------------------------
  ENTER         C2S/S2C 进入/离开地图实例广播
  LEAVE         C2S/S2C 离开地图实例广播
  MOVE_SYNC     C2S/S2C 角色移动位置同步
  ACTION_BROADCAST C2S/S2C 动作/表情广播（第3章3.7）
  MECH_STATE    S2C     机关状态变化推送（第9章）
  RECONNECT     C2S/S2C 断线重连与状态恢复（第5章）

### 【客户端→服务端（C2S）示例】

``` json
{
  "cmd": "MOVE_SYNC",
  "payload": { "x": 120.5, "y": 88.0, "dir": "NE" },
  "ts": 1762000000
}
```

### 【服务端→客户端（S2C）示例】

``` json
{
  "cmd": "ENTER",
  "payload": { "player_id": "string", "x": 100, "y": 100, "character_id": "string" },
  "ts": 1762000001
}
```

### 【要求】

-   移动同步频率与带宽预算待压测确定。
-   广播范围遵循可见范围规则（第4章/第5章），不向全实例无差别广播。
-   所有写类消息（MOVE/ACTION）服务端需校验频率与合法性。

------------------------------------------------------------------------

## 17.6 服务端权限校验

**优先级：【MVP必须】**

### 【功能说明】

统一服务端校验规则，确保数据不被越权修改（关联第5章、第11章）。

### 【校验规则】

  校验类别              规则
  --------------------- --------------------------------------------------
  登录态校验            所有写接口/WS消息必须先验活有效令牌或会话
  角色归属校验          角色选择/更换必须校验玩家已解锁该角色
  关卡归属校验          关卡进入/结算/法则操作必须校验 run 属于该玩家
  资源归属校验          奖励领取/收藏操作必须校验玩家拥有资格
  幂等校验              写请求携带 request_id，重复提交只生效一次
  频率限制              移动/动作/交互等设频率上限，阈值待压测确定

### 【要求】

-   积分、排名、机关状态以服务端校验结果为准（G-014）。
-   客户端伪造位置、积分、状态一律拒绝。
-   越权操作返回明确错误码，不暴露内部细节。

------------------------------------------------------------------------

## 17.7 断线恢复机制

**优先级：【MVP必须】**

### 【功能说明】

定义玩家断线后的会话保留、自动重连与状态恢复流程（关联第5章、第2章2.2/2.9）。

### 【规范】

  阶段            规则
  --------------- --------------------------------------------------
  断线检测        服务端心跳超时判定离线，保留会话一段时间（时长待第5章定）
  席位保留        主地图席位是否保留按第4章实例规则与第5章会话规则执行
  自动重连        客户端检测断线后自动重连并携带会话令牌
  状态恢复        重连成功恢复角色位置/关卡运行状态（个人独立 G-002）
  重连失败        提示并返回登录，由服务端清理过期会话
  数据完整性      未提交的发现/收藏/积分不计入，已提交数据保留

### 【要求】

-   重连期间不重复发放奖励或积分（幂等）。
-   原地图实例关闭时，按第4章规则重新分配实例。
-   断线恢复的具体保留时长与心跳间隔由第5章最终确定。

------------------------------------------------------------------------

## 17.8 数据备份与安全策略

**优先级：【MVP必须】**

### 【功能说明】

保障玩家数据安全、可恢复与最小化暴露（建议方案，待最终确认）。

### 【规范】

  类别            策略
  --------------- --------------------------------------------------
  PostgreSQL备份  定时全量+增量备份；备份保留周期待运维确定
  Redis持久化     AOF/RDB持久化；会话与缓存可重建数据允许丢失短期
  敏感数据加密    微信标识等敏感字段加密存储，密钥分级管理
  最小权限        服务账号仅授予必要库表权限，禁止共用超级账号
  传输安全        REST/WS均走HTTPS/WSS，令牌不过期长期持有
  审计            积分流水与关键写操作留痕（见17.9）

------------------------------------------------------------------------

## 17.9 日志和监控

**优先级：【MVP必须】**

### 【功能说明】

建立业务日志、性能监控与告警体系，重点关注积分流水审计（关联第13章）。

### 【规范】

  类别            内容
  --------------- --------------------------------------------------
  业务日志        登录、关卡结算、发现、奖励、动作广播等关键事件
  性能监控        接口耗时、WS消息量、实例人数、CPU/内存/带宽
  告警            实例人数异常、结算失败率、断线率超阈值告警
  积分流水审计    score_events 不可篡改，支持对账与争议核查（G-014）
  监控大盘        实时在线、实例分布、赛季结算状态

### 【要求】

-   积分相关日志需支持按玩家、时间、事件类型检索。
-   监控阈值与采样率待压测与运维确定，标注「待最终确认」。

------------------------------------------------------------------------

## 17.10 本章验收总表

  测试编号   测试场景               预期结果
  ---------- ---------------------- ----------------------------------------
  ARCH-001   架构组件联通           客户端经网关/WS访问服务与数据层
  ARCH-002   玩家表创建             players 含唯一wx_openid
  ARCH-003   角色数据一致           characters 含12条有效角色
  ARCH-004   机关状态隔离           不同玩家 run 的机关状态互不影响
  ARCH-005   积分流水不可篡改        score_events 记录完整可审计
  ARCH-006   排行榜三榜             按 board_type 正确存储与查询
  ARCH-007   赛季周期               seasons 周/月周期正确
  ARCH-008   登录接口               返回玩家初始化数据
  ARCH-009   关卡结算幂等           重复结算只一份记录
  ARCH-010   WS移动同步             20人同实例移动同步正确（压测）
  ARCH-011   断线重连               重连恢复个人状态且不重复发奖
  ARCH-012   权限校验               越权操作被拒绝
  ARCH-013   备份恢复               PostgreSQL 可恢复至备份点

------------------------------------------------------------------------

## 17.11 Open Questions（本章待确认问题）

  ------------------------------------------------------------------------------------------------------------------------
  编号          待确认事项                         当前建议                               影响岗位
  ------------- ---------------------------------- -------------------------------------- ------------------
  ARCH-Q01      客户端引擎是否确认为 Cocos 3.x     建议采用，待技术评审确认               客户端、技术负责人

  ARCH-Q02      后端架构模块化单体 vs 微服务       暂定模块化单体，待规模评估             服务端、架构

  ARCH-Q03      地图实例调度与节点分配策略         按负载选实例，具体策略待定             服务端

  ARCH-Q04      单实例硬人数上限                   MVP目标20，压测后定（第4章MAP-Q04）    服务端、测试

  ARCH-Q05      高写入表分库分表方案               score_events/leaderboards 待压测确定   服务端、DBA

  ARCH-Q06      认证方式 JWT 还是会话令牌          待安全评审确定                         服务端、安全

  ARCH-Q07      断线保留时长与心跳间隔            待第5章最终确定                        服务端、客户端

  ARCH-Q08      备份保留周期与RPO/RTO             待运维与合规确定                       运维、制作人

  ARCH-Q09      WS移动同步频率与带宽预算           待压测确定                             服务端、客户端
  ------------------------------------------------------------------------------------------------------------------------

------------------------------------------------------------------------

**第17章完成。**
