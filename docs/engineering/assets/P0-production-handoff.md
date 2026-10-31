# P0 美术资源制作交付单

- 版本：P0-HANDOFF-1.0
- 日期：2026-10-31
- 工程基线：Cocos Creator 3.8.8 / 微信小游戏
- 关联：GDD V0.2、第18章 V0.3、`asset-manifest.v1.json`
- 状态：制作规格冻结候选；所有资源仍按 manifest 状态管理，不代表已交付。

## 1. 交付目标与边界

P0 是首个可在 Cocos Creator 编辑器中展示并体验的视觉垂直切片。完成后必须从主地图进入 ROOM-01，控制 CHR_001 移动，使用回声显形机关、完成机关交互、打开出口并结算；三条法则反馈、关键 UI、网络状态和基础音效均可观察/听见。

P0 不要求交付 CHR_002～CHR_012，也不代表五个房间和隐藏结局美术完成。P1/P2 资源仍按 manifest 原优先级执行。

## 2. 视觉与坐标约束

1. 统一原创 Q 版奇幻风格；不得临摹第三方 IP、角色或现成游戏素材。
2. ROOM-01 使用 GDD 规定的 45° 等距投影。服务端逻辑坐标为唯一权威坐标；屏幕投影采用 `screenX=(x-y)*S`、`screenY=(x+y)*S`。不得将屏幕坐标写回服务端。
3. 角色 Sprite 锚点落在脚底接地点；角色、机关底座、可遮挡装饰按纵深排序。HUD 始终位于屏幕空间。
4. 机关视觉尺寸、动画和特效不得改变服务端交互半径、目标状态或法则判定。
5. 所有图层拆分须保留独立碰撞/可行走数据；美术遮挡不等于逻辑阻挡。

## 3. P0 资源逐项交付表

| Asset ID | 类别 | 交付目录 | 来源章节 | 最低验收要求 |
|---|---|---|---|---|
| `CHR_001_PORTRAIT` | character_portrait | `assets/resources/characters/CHR_001/portrait` | GDD 3.9 / 18.1 | 角色头像可按资源ID加载 |
| `CHR_001_MODEL` | character_model | `assets/resources/characters/CHR_001/model` | GDD 3.9 / 18.1 | 角色模型或2D角色主体资源可加载 |
| `CHR_001_PREVIEW` | character_preview | `assets/resources/characters/CHR_001/preview` | GDD 3.9 / 18.1 | 角色选择预览资源可加载 |
| `CHR_001_ANIMATION_SET` | character_animation | `assets/resources/characters/CHR_001/animation` | GDD 3.4 / 3.9 / 18.2 | 包含8方向IDLE、8方向MOVE、INTERACT及ACT_001至ACT_004 |
| `MAP_MAIN_001_SCENE` | main_map | `assets/resources/maps/MAP_MAIN_001/scene` | GDD 4.10 / 18.3 | 主地图scene资源与地图版本一致 |
| `MAP_MAIN_001_GROUND` | main_map | `assets/resources/maps/MAP_MAIN_001/ground` | GDD 4.10 / 18.3 | 主地图ground资源与地图版本一致 |
| `MAP_MAIN_001_PROPS` | main_map | `assets/resources/maps/MAP_MAIN_001/props` | GDD 4.10 / 18.3 | 主地图props资源与地图版本一致 |
| `MAP_MAIN_001_COLLISION` | main_map | `assets/resources/maps/MAP_MAIN_001/collision` | GDD 4.10 / 18.3 | 主地图collision资源与地图版本一致 |
| `MAP_MAIN_001_WALKABLE` | main_map | `assets/resources/maps/MAP_MAIN_001/walkable` | GDD 4.10 / 18.3 | 主地图walkable资源与地图版本一致 |
| `MAP_MAIN_001_SPAWN` | main_map | `assets/resources/maps/MAP_MAIN_001/spawn` | GDD 4.10 / 18.3 | 主地图spawn资源与地图版本一致 |
| `MAP_MAIN_001_ENTRANCES` | main_map | `assets/resources/maps/MAP_MAIN_001/entrances` | GDD 4.10 / 18.3 | 主地图entrances资源与地图版本一致 |
| `MAP_MAIN_001_CAMERA` | main_map | `assets/resources/maps/MAP_MAIN_001/camera` | GDD 4.10 / 18.3 | 主地图camera资源与地图版本一致 |
| `MAP_MAIN_001_CONFIG` | main_map | `assets/resources/maps/MAP_MAIN_001/config` | GDD 4.10 / 18.3 | 主地图config资源与地图版本一致 |
| `LV-ROOM-01_GEOMETRY` | level_geometry | `assets/resources/levels/LV-ROOM-01` | GDD 6 / 18.3 | 关卡逻辑尺寸、出生点、机关坐标和可行走区域完整 |
| `M01-EXIT-01` | mechanism | `assets/resources/mechanisms/M01-EXIT-01` | GDD 9 / 18.5 | 机关M01-EXIT-01具备状态表现、触发动效和逻辑视觉分离 |
| `M01-HIDEABLE-01` | mechanism | `assets/resources/mechanisms/M01-HIDEABLE-01` | GDD 9 / 18.5 | 机关M01-HIDEABLE-01具备状态表现、触发动效和逻辑视觉分离 |
| `M01-LIGHT-01` | mechanism | `assets/resources/mechanisms/M01-LIGHT-01` | GDD 9 / 18.5 | 机关M01-LIGHT-01具备状态表现、触发动效和逻辑视觉分离 |
| `FX_ECHO_PULSE_01` | effect | `assets/resources/effects` | GDD 7 / 18.6 | 特效可独立播放，不承担逻辑判定 |
| `FX_GAZE_BEAM_01` | effect | `assets/resources/effects` | GDD 7 / 18.6 | 特效可独立播放，不承担逻辑判定 |
| `FX_REVERSE_FLOW_01` | effect | `assets/resources/effects` | GDD 7 / 18.6 | 特效可独立播放，不承担逻辑判定 |
| `UI_LOGIN` | ui | `assets/resources/ui` | GDD 16 / 18.7 | UI_LOGIN具备安全区适配、加载态和缺失降级 |
| `UI_MAIN_MAP_HUD` | ui | `assets/resources/ui` | GDD 16 / 18.7 | UI_MAIN_MAP_HUD具备安全区适配、加载态和缺失降级 |
| `UI_INTERACTION` | ui | `assets/resources/ui` | GDD 16 / 18.7 | UI_INTERACTION具备安全区适配、加载态和缺失降级 |
| `UI_LAW_BAR` | ui | `assets/resources/ui` | GDD 16 / 18.7 | UI_LAW_BAR具备安全区适配、加载态和缺失降级 |
| `UI_SETTLEMENT` | ui | `assets/resources/ui` | GDD 16 / 18.7 | UI_SETTLEMENT具备安全区适配、加载态和缺失降级 |
| `UI_NETWORK_STATE` | ui | `assets/resources/ui` | GDD 16 / 18.7 | UI_NETWORK_STATE具备安全区适配、加载态和缺失降级 |
| `AUD_UI_CLICK` | audio | `assets/resources/audio` | GDD 18.8 | AUD_UI_CLICK触发点、音量、循环/优先级符合音频规范 |
| `AUD_INTERACTION` | audio | `assets/resources/audio` | GDD 18.8 | AUD_INTERACTION触发点、音量、循环/优先级符合音频规范 |
| `AUD_ECHO` | audio | `assets/resources/audio` | GDD 18.8 | AUD_ECHO触发点、音量、循环/优先级符合音频规范 |
| `AUD_GAZE` | audio | `assets/resources/audio` | GDD 18.8 | AUD_GAZE触发点、音量、循环/优先级符合音频规范 |
| `AUD_REVERSE` | audio | `assets/resources/audio` | GDD 18.8 | AUD_REVERSE触发点、音量、循环/优先级符合音频规范 |
| `AUD_DISCOVERY` | audio | `assets/resources/audio` | GDD 18.8 | AUD_DISCOVERY触发点、音量、循环/优先级符合音频规范 |
| `AUD_SETTLEMENT_CLEAR` | audio | `assets/resources/audio` | GDD 18.8 | AUD_SETTLEMENT_CLEAR触发点、音量、循环/优先级符合音频规范 |
| `AUD_NETWORK_DISCONNECT` | audio | `assets/resources/audio` | GDD 18.8 | AUD_NETWORK_DISCONNECT触发点、音量、循环/优先级符合音频规范 |
| `AUD_NETWORK_RECONNECT` | audio | `assets/resources/audio` | GDD 18.8 | AUD_NETWORK_RECONNECT触发点、音量、循环/优先级符合音频规范 |
| `AUD_BGM_MAIN_MAP` | audio | `assets/resources/audio` | GDD 18.8 | AUD_BGM_MAIN_MAP触发点、音量、循环/优先级符合音频规范 |
| `AUD_BGM_ROOM` | audio | `assets/resources/audio` | GDD 18.8 | AUD_BGM_ROOM触发点、音量、循环/优先级符合音频规范 |

## 4. 角色 CHR_001 交付要求

- 头像、角色主体、角色选择预览必须使用同一角色设计稿和色彩规范。
- 动画状态至少覆盖 IDLE、8 方向 MOVE、INTERACT、ACT_001 挥手、ACT_002 点头、ACT_003 开心、ACT_004 疑问；方向缺帧必须明确记录，不得静默替代。
- 动画状态由客户端播放，不参与服务端权威状态判断。
- 交付源文件、透明导出文件、动画切片/帧率说明、锚点说明和预览图。
- 角色主体必须在等距场景中通过脚底锚点和深度排序测试。

## 5. ROOM-01 场景与机关

关卡逻辑边界、出生点和机关位置以 `levels.v1.json` 为准，不能由美术自行移动逻辑坐标。当前原型配置为边界 x=0..12、y=0..8，出生点 (1,4)；机关位置分别为 M01-HIDEABLE-01 (5,4)、M01-LIGHT-01 (7.5,4)、M01-EXIT-01 (10.5,4)。这些是逻辑坐标，不是像素坐标。

机关最低状态表现：
- M01-HIDEABLE-01：隐藏、回声显形、已显形；显形前后轮廓应清楚区分。
- M01-LIGHT-01：未激活、激活；交互反馈不得替代服务端状态。
- M01-EXIT-01：锁定、可开启、已开启；锁定原因须能被玩家理解。
- 状态过渡需有起止帧/时长说明；具体时长由客户端体验评审后配置，不能擅自改变服务端逻辑窗口。

场景至少拆分背景/地面/装饰/遮挡层/碰撞与可行走数据。碰撞和可行走数据必须与逻辑地图版本一致。

## 6. 特效要求

- FX_ECHO_PULSE_01：以目标为中心的扩散脉冲环，具有起始、峰值、消散阶段。
- FX_GAZE_BEAM_01：角色至目标的持续光束；停止注视、租约失效或离开关卡时立即停止并释放节点。
- FX_REVERSE_FLOW_01：具有明确方向反转的流动粒子反馈。
- 所有特效仅做表现，不携带命中、范围、冷却或状态判定。
- 交付透明通道、播放时长、循环方式、锚点/挂点、资源占用说明。

## 7. UI 与音频要求

UI_LOGIN、UI_MAIN_MAP_HUD、UI_INTERACTION、UI_LAW_BAR、UI_SETTLEMENT、UI_NETWORK_STATE 必须覆盖加载、正常、禁用、错误/断线等相关状态；适配刘海屏与底部安全区。按钮视觉状态与实际可交互状态一致。

音频须提交无损母带、最终运行时文件、时长、峰值/响度、循环标记、触发事件、优先级和授权信息。BGM 无缝循环；SFX 优先级高于 BGM；静音后不得继续播放。不得在没有真机验证前将某一种编码写成唯一格式。

## 8. 通用文件交付

每个资产必须包含：
1. 可编辑源文件及运行时导出文件；
2. 文件清单、分辨率/帧率/时长/格式/透明通道等适用规格；
3. 版本号、制作者/供应商、来源引用、授权文本和授权证据；
4. Cocos Creator 3.8.8 导入结果；
5. 场景截图或录屏、异常降级结果和验收记录；
6. Android 微信真机与 iOS 微信真机验证记录；不适用平台必须写明原因；
7. manifest 的真实文件路径和 READY 证据路径。

资源文件必须放在 manifest 指定目录下；文件名遵循第18章命名规范。禁止复用同一文件路径冒充不同资产，禁止把程序几何占位标记为正式 READY。

## 9. 技术美术待决项（禁止臆造）

以下事项需以真实设备、Cocos 导入与构建结果确定，不在制作单中伪造硬指标：
- 各类角色/机关/特效的最终像素尺寸、帧率、帧数与图集拆分；
- ASTC 6x6 / 5x5 / PNG 回退质量及设备覆盖；
- 音频运行时编码、采样率、声道和响度目标；
- 单场景纹理内存、Draw Call、CPU/GPU 帧耗时预算；
- 微信主包、分包的最终构建体积。

## 10. P0 验收顺序

1. 文件与授权证据检查通过；
2. Cocos Creator 3.8.8 导入无资源丢失、UUID 冲突或序列化错误；
3. 主地图与 ROOM-01 坐标/碰撞/深度排序一致；
4. CHR_001 动画状态切换和触屏移动正常；
5. 三个机关状态表现与服务端权威状态一致；
6. 三法则特效不阻塞输入、不改变逻辑；
7. 六个 P0 UI 覆盖安全区、加载、禁用和网络异常；
8. 音频触发、循环、静音、优先级通过真机检查；
9. Android 与 iOS 微信真机录屏/截图和验收记录归档；
10. manifest 对应条目具备实际文件与完整证据，才允许从 MISSING 改为 READY。

## 11. 当前阻断

本制作单只把 P0 的 37 项资源转成可交付任务，不表示资源已经制作。正式资源发布仍由 `npm run validate:release-assets` 严格门禁控制；任何 required 资源缺失、授权证据缺失或验收证据缺失均不得发布。
