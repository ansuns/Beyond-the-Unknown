# 《无界之外》资源制作与交付计划

- 版本：ASSET-PLAN-1.0
- 日期：2026-10-31
- 适用工程：Cocos Creator 3.8.8 / 微信小游戏
- 当前清单：112 项，全部为 MISSING；正式资源发布门禁必须保持 BLOCKED，直到所有 MVP 资源通过验收。

## 1. 资产盘点

| 类别 | 数量 | 交付范围 | 当前状态 |
|---|---:|---|---|
| 角色 | 48 | 12 角色 × 头像/模型/预览/动画组 | 全部 MISSING |
| 主地图 | 9 | 场景、地面、装饰、碰撞、可行走区、出生点、入口、镜头、配置 | 全部 MISSING |
| 关卡空间 | 6 | ROOM-01～05 + 隐藏结局的正式场景美术 | 全部 MISSING |
| 机关 | 14 | 按唯一机关 ID 交付，不能用同一张通用图冒充多个实例 | 全部 MISSING |
| 特效 | 9 | 三法则、五房间结算、隐藏结局 | 全部 MISSING |
| UI | 12 | 登录、角色选择、主地图 HUD、交互、法则、发现、结算、排行榜、图鉴、奖励、个人信息、网络状态 | 全部 MISSING |
| 音频 | 14 | UI/交互、法则、发现、结算、社交、网络、三类 BGM | 全部 MISSING |
| **合计** | **112** | 资源清单中全部 MVP 必需条目 | **BLOCKED** |

说明：服务端已存在关卡坐标、出生点、机关配置和几何玩法原型；这不等于正式背景、角色、机关图像、特效、UI 或音效文件已经交付。资源清单的 MISSING 状态不得因为几何原型可运行而修改。

## 2. 制作优先级

### P0：首个美术垂直切片

目标：能够在 Cocos Creator 编辑器中展示并完整体验一条视觉闭环，不追求一次性完成全部角色。

- MAP_MAIN_001：场景背景、地面、基础装饰、碰撞/可行走区域、出生点、入口、摄像机。
- CHR_001：头像、角色主体、预览、IDLE/MOVE/INTERACT 和四种社交动作的最小完整集。
- ROOM-01：场景背景、M01-HIDEABLE-01、M01-LIGHT-01、M01-EXIT-01 三种状态表现。
- FX_ECHO_PULSE_01、FX_GAZE_BEAM_01、FX_REVERSE_FLOW_01。
- UI_LOGIN、UI_MAIN_MAP_HUD、UI_INTERACTION、UI_LAW_BAR、UI_SETTLEMENT、UI_NETWORK_STATE。
- AUD_UI_CLICK、AUD_INTERACTION、AUD_ECHO、AUD_GAZE、AUD_REVERSE、AUD_DISCOVERY、AUD_SETTLEMENT_CLEAR、AUD_NETWORK_DISCONNECT、AUD_NETWORK_RECONNECT、AUD_BGM_MAIN_MAP、AUD_BGM_ROOM。

P0 验收后才能进入 P1 的房间美术批量制作。P0 资源不代表最终 112 项已完成。

### P1：五房间与隐藏结局

- ROOM-02：M02-BRIDGE-01 的常态/显形/激活/锁定视觉。
- ROOM-03：M03-ENERGY-01、M03-DOOR-01 的能量联动状态和门开启动画。
- ROOM-04：M04-PLATFORM-01、M04-PLATFORM-02 的移动、反转、终点锁定状态。
- ROOM-05：M05-BRIDGE-01、M05-ENERGY-01、M05-REVERSE-01、M05-HIDDEN-GATE 的组合反馈。
- 隐藏结局：H01-GATE、H01-END、FX_HIDDEN_ENDING、结局 UI/BGM。
- FX_ROOM_CLEAR_01～05、AUD_SETTLEMENT_FAIL、AUD_BGM_SETTLEMENT。

### P2：完整角色与外围 UI

- CHR_002～CHR_012 的完整资源。
- UI_CHARACTER_SELECT、UI_DISCOVERY、UI_LEADERBOARD、UI_COLLECTION、UI_REWARD、UI_PROFILE。
- AUD_SOCIAL_ACTION 及 P0 未覆盖的所有音频资源。
- 所有 12 个角色的 8 方向 IDLE/MOVE、INTERACT、ACT_001～ACT_004 动画状态回归。

## 3. 统一技术交付基线

### 等距投影与逻辑坐标（GDD 4.2）

- ROOM-01～05 与隐藏结局使用 45° 等距投影；逻辑坐标仍为服务端的 `x/y`，禁止把投影后的屏幕坐标写入服务端。
- 客户端统一使用 `screenX = (x - y) * S`、`screenY = (x + y) * S`；房间逻辑矩形在屏幕上呈菱形，触摸输入必须通过逆变换回到逻辑坐标并裁剪到关卡边界。
- 地面/墙体/机关底座应沿等距轴对齐；角色 Sprite 的锚点以脚底/接地点为准，避免角色漂浮或穿入地面。
- 角色、机关与可遮挡装饰需要按投影后的纵深坐标排序；UI/HUD 保持 Canvas 屏幕空间，不参与世界投影。
- 美术资源不得把透视效果烘焙成与逻辑坐标不一致的斜视角；机关视觉尺寸仍不得改变服务端交互半径。

### 图片与纹理

- 源图：透明资源优先 PNG；不透明大背景可用 JPG；源图必须保留可编辑文件。
- 微信小游戏 GPU 纹理：以 ASTC 6x6 作为首轮默认评估；文字/细线/高对比边缘出现明显损失时回退 ASTC 5x5 或 PNG。
- 所有关键资源必须保留通用 PNG 回退；开发者工具不支持 ASTC，ASTC 通过必须以真机为准。
- ASTC、ETC1、ETC2、PVR 的平台支持与 Cocos 构建过滤必须以 Cocos Creator 3.8 文档为准。
- 图集按角色、UI、主地图、单个房间和法则特效拆分；2048×2048 为本项目首轮上限，实机验证后允许下调。
- 透明资源必须验证 Alpha 边缘，不允许黑边、白边或透明通道丢失。

### 微信小游戏包体

- 平台基线：主包不超过 4 MB，所有分包合计不超过 30 MB。
- 项目安全预算：主包不超过 3.2 MB，所有分包合计不超过 24 MB。
- 资源分包建议：bundle-world、bundle-rooms-01-02、bundle-rooms-03-05、bundle-hidden-ending。
- 微信本地小游戏分包不可作为远程 Asset Bundle；脚本尽量保留在主包，房间 bundle 以资源为主。
- 每次正式构建记录主包/每个分包/总包体积，不允许只统计图片源文件大小。

### 音频

- 先提交无损母带和触发点表，再按微信小游戏真机兼容性确定最终编码、采样率、声道和响度。
- 不在缺少设备测试时擅自把某一种编码写成唯一交付格式。
- BGM 必须无缝循环；SFX 优先级高于 BGM；静音状态下不得继续播放。
- 每个音频文件必须记录时长、峰值/响度、循环标记、触发事件和授权来源。

## 4. 交付目录与命名

统一根目录：client/assets/resources/

- characters/CHR_###/{model,animation,portrait,preview}/
- maps/MAP_MAIN_001/{scene,ground,props,collision,areas,spawn,entrances,camera,config}/
- levels/LV-ROOM-01/ ... levels/LV-ROOM-05/ ... levels/LV-HIDDEN-01/
- mechanisms/{H01-END,H01-GATE,M01-EXIT-01,M01-HIDEABLE-01,M01-LIGHT-01,M02-BRIDGE-01,M03-DOOR-01,M03-ENERGY-01,M04-PLATFORM-01,M04-PLATFORM-02,M05-BRIDGE-01,M05-ENERGY-01,M05-HIDDEN-GATE,M05-REVERSE-01}/
- effects/FX_*/
- ui/UI_*/
- audio/AUD_*/

文件名严格遵循 GDD 第18章：角色 CHR_、机关 MEC_、特效 FX_、UI UI_、音频 AUD_ 前缀。机关文件名以 canonical mechanism_id 为类型段，例如 `MEC_M01-HIDEABLE-01_REVEALED_01.png`；但 manifest 的 `asset_id` 和机关目录名必须保持服务端 canonical mechanism_id（如 `M01-HIDEABLE-01`），不得把 `MEC_` 文件名前缀写入服务端机制 ID。

## 5. 资源验收证据

每项资产 READY 前必须提供：

1. 真实文件路径（相对 client/），源文件与运行时导入文件。
2. 资产 ID、版本、制作人/供应方、授权来源。
3. 分辨率/帧率/时长/格式/透明通道等适用规格。
4. Cocos Creator 3.8.8 导入成功证据。
5. 至少一台 Android 微信真机和一台 iOS 微信真机的显示/播放验证；不适用的平台需说明。
6. 对应场景截图或录屏、异常降级结果和验收人。
7. 资源 manifest 更新及 validate:assets 成功结果。

## 6. 发布门禁

- 日常开发：npm run validate:assets；允许缺失条目继续追踪，但不得把 MISSING 改为 READY。
- 发布候选：npm run validate:release-assets；任何 required=true 的 MISSING/IN_PROGRESS/BLOCKED 或文件缺失均阻止发布。
- 当前 112 项全部 MISSING，发布门禁应当失败。这是预期结果，不得通过降低 required、伪造路径或把程序几何占位标记为 READY 绕过。
