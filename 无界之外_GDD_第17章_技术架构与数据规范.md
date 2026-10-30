# 《无界之外》GDD V0.1

## 第17章 技术架构与数据规范

-   **文档版本：** GDD V0.1
-   **章节版本：** 第17章 V0.1
-   **日期：** 2026-10-30
-   **适用岗位：** 服务端程序、客户端程序、技术美术、DevOps、测试、系统策划
-   **章节状态：** 初稿
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

## 17.3 数据库表结构

**优先级：【MVP必须】**

### 【功能说明】

给出MVP主要数据表及关键字段建议。所有表以PostgreSQL为建议存储，字段类型与索引以最终技术评审为准；涉及容量的分库分表方案标注「待最终确认」。

### 【players｜玩家账号】

  字段                类型            说明
  ------------------- --------------- ----------------------------
  player_id           string(PK)      游戏内部玩家ID
  wx_openid           string(唯一)    微信平台标识
  current_character_id string/null     当前角色ID
  total_score         bigint          累计积分（汇总缓存）
  progress_version    integer         进度版本
  status              enum             NORMAL / BANNED
  created_at          timestamp       创建时间

### 【characters｜角色配置】

  字段                类型            说明
  ------------------- --------------- ----------------------------
  character_id        string(PK)      角色唯一ID
  character_name      string          角色名称
  portrait_asset_id   string          头像资源ID
  model_asset_id      string          模型资源ID
  animation_set_id    string          动画组ID
  preview_asset_id    string          预览资源ID
  unlock_type         enum             DEFAULT/CONDITION/EVENT
  unlock_value        string/null      解锁条件参数
  sort_order          integer          排序
  is_enabled          boolean         是否开放

### 【player_characters｜玩家角色关系】

  字段           类型        说明
  -------------- ----------- --------------------------
  player_id      string(FK)  玩家ID
  character_id   string(FK)  已解锁角色ID
  unlocked_at    timestamp   解锁时间
  source         string      DEFAULT/REWARD/EVENT

### 【maps｜地图配置】

  字段                类型            说明
  ------------------- --------------- ----------------------------
  map_id              string(PK)      地图唯一ID
  map_name            string          地图名称
  map_type            enum             MAIN/INSTANCE
  scene_asset_id      string          场景资源ID
  collision_data_id   string          碰撞数据ID
  navigation_data_id  string/null      导航数据ID
  map_width           integer         逻辑宽度
  map_height          integer         逻辑高度
  camera_config_id    string          摄像机配置ID
  spawn_group_id      string          出生点组ID
  instance_config_id  string          实例参数配置ID
  version             integer         配置版本
  is_enabled          boolean         是否开放

### 【map_instances｜地图实例】

  字段              类型            说明
  ----------------- --------------- ----------------------------
  instance_id       string(PK)      实例唯一ID
  map_id            string(FK)      地图ID
  status            enum             OPEN/FULL/CLOSING/CLOSED
  current_players   integer         当前在线人数
  max_players       integer         硬上限（压测后配置）
  target_players    integer         目标人数（MVP=20）
  created_at        timestamp       创建时间
  last_active_at    timestamp       最近活跃时间
  server_node_id    string          承载节点

### 【level_runs｜个人关卡运行】

  字段              类型            说明
  ----------------- --------------- ----------------------------
  run_id            string(PK)      关卡运行ID
  player_id         string(FK)      玩家ID
  level_id          string          关卡ID
  instance_id       string/null     关联主地图实例
  status            enum             CREATED/RUNNING/COMPLETED/FAILED/ABANDONED
  start_time        timestamp       开始时间
  completion_time   integer/null     通关耗时（秒）
  score             integer/null     通关积分
  created_at        timestamp       创建时间

### 【mechanisms｜机关状态（按关卡运行隔离）】

  字段              类型            说明
  ----------------- --------------- ----------------------------
  mechanism_id      string(PK)      机关实例ID
  run_id            string(FK)      所属个人关卡运行
  owner_player_id   string(FK)      拥有者（个人独立 G-002）
  mechanism_type    string          机关类型（第9章）
  state             jsonb           机关状态数据
  updated_at        timestamp       更新时间

说明：机关状态以 `run_id` 隔离，确保玩家之间不共享机关状态（G-002）。

### 【discoveries｜玩家发现记录】

  字段              类型            说明
  ----------------- --------------- ----------------------------
  discovery_id      string(PK)      发现记录ID
  player_id         string(FK)      玩家ID
  discovery_key     string          发现物标识
  discovery_type    string          发现类别
  level_id          string/null     所属关卡
  discovered_at     timestamp       发现时间
  is_world_first    boolean         是否全服首次

### 【collections｜玩家收藏】

  字段              类型            说明
  ----------------- --------------- ----------------------------
  collection_id     string(PK)      收藏记录ID
  player_id         string(FK)      玩家ID
  item_id           string          藏品ID
  item_type         string          藏品类别
  obtained_at       timestamp       获得时间
  source            string          来源

### 【world_archive｜世界档案】

  字段                类型            说明
  ------------------- --------------- ----------------------------
  archive_id          string(PK)      档案ID
  discovery_key       string(唯一)    发现物标识
  first_player_id     string/null     全服首次发现玩家
  first_discovered_at timestamp/null   首次发现时间
  description         string          描述

说明：世界档案永久记录全服首次发现（G-017），不随玩家数据清理删除。

### 【score_events｜积分流水】

  字段              类型            说明
  ----------------- --------------- ----------------------------
  event_id          string(PK)      流水ID
  player_id         string(FK)      玩家ID
  event_type        string          事件类型（通关/发现/收藏）
  score_delta       integer         积分变化
  balance_after     bigint          变动后余额
  run_id            string/null     关联关卡运行
  level_id          string/null     关联关卡
  created_at        timestamp       发生时间

说明：积分流水不可篡改，作为排行榜与审计依据（G-014、第13章）。

### 【leaderboards｜排行榜】

  字段              类型            说明
  ----------------- --------------- ----------------------------
  board_id          string(PK)      榜单记录ID
  board_type        enum             EXPLORE/CLEAR/COLLECT（三榜）
  season_id         string(FK)      赛季ID
  player_id         string(FK)      玩家ID
  score             bigint          榜单积分
  rank              integer/null    排名
  updated_at        timestamp       更新时间

### 【seasons｜赛季】

  字段                类型            说明
  ------------------- --------------- ----------------------------
  season_id           string(PK)      赛季ID
  season_type         enum             WEEKLY/MONTHLY（G-013）
  start_time          timestamp       开始时间
  end_time            timestamp       结束时间
  status              enum             PENDING/ACTIVE/SETTLED
  settlement_status   enum             UNSETTLED/SETTLED

### 【rewards｜奖励配置】

  字段                类型            说明
  ------------------- --------------- ----------------------------
  reward_id           string(PK)      奖励ID
  reward_type         enum             APPEARANCE/TITLE/PET/BADGE
  reward_name         string          奖励名称
  condition_type      string          发放条件类型
  condition_value     string          条件参数
  asset_ref           string/null      资源引用
  is_enabled          boolean         是否开放

### 【player_rewards｜玩家奖励】

  字段           类型        说明
  -------------- ----------- --------------------------
  id             string(PK)  记录ID
  player_id      string(FK)  玩家ID
  reward_id      string(FK)  奖励ID
  granted_at     timestamp   发放时间
  source         string      来源
  status         enum        GRANTED/CONSIGNED

### 【achievements｜成就配置】

  字段                类型            说明
  ------------------- --------------- ----------------------------
  achievement_id      string(PK)      成就ID
  name                string          成就名称
  description         string          描述
  condition_type      string          达成条件类型
  condition_value     string          条件参数
  icon_asset_id       string          图标资源ID

### 【actions_log｜动作/表情日志】

  字段              类型            说明
  ----------------- --------------- ----------------------------
  log_id            string(PK)      日志ID
  player_id         string(FK)      发起玩家
  instance_id       string(FK)      所在地图实例
  action_type       enum             ACT_001/ACT_002/ACT_003/ACT_004
  target_player_id  string/null      可选目标玩家
  created_at        timestamp       发生时间

### 【建表与扩展要求】

-   所有 `player_id`、`character_id`、`map_id`、`instance_id`、`run_id` 等关联键建立外键或等效校验。
-   高写入表（score_events、actions_log、leaderboards）的索引与分表方案待压测确定，标注为「待最终确认」。
-   表结构调整必须通过迁移脚本，禁止手工改线。

------------------------------------------------------------------------

## 17.4 API接口规范

**优先级：【MVP必须】**

### 【规范】

-   **风格：** REST（建议，待最终确认）。
-   **Base Path：** `/api/v1`。
-   **认证：** JWT 或会话令牌（建议，待最终确认）；除登录外所有接口需携带有效令牌。
-   **通用响应：** 统一返回 `{ code, message, data, request_id }`。
-   **幂等：** 写接口建议携带 `request_id`，服务端据此去重（第5章/第11章）。
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
  发现上报                  POST   /api/v1/discovery/report        上报隐藏发现
  排行榜查询                GET    /api/v1/leaderboard/{type}      三榜查询
  赛季查询                  GET    /api/v1/season                  周/月赛季信息
  奖励领取                  POST   /api/v1/reward/claim            领取奖励

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
