# 横屏有效画面铺满 — 验收报告

> 分支：`fix/client-screen-fill` ｜ PR：#149 ｜ 目标：`main`
> 生成时间：2026-11-02 ｜ 作者：执行工程师（阿则）

本报告严格区分以下状态，**不把前一项推导成后一项**：

| 状态 | 结论 |
|---|---|
| 代码已修改 | ✅ 是 |
| 单元测试通过 | ✅ 是（24 文件 / 172 用例） |
| CI 通过 | ⏳ 未验证（本轮未触发远端 CI 结果） |
| Cocos 构建通过 | ✅ 是（wechatgame + web-mobile，真实构建 exit 0） |
| 微信开发者工具运行通过 | ⚠️ 部分（导入 + 模拟器已渲染登录页，见 §8；横屏 ROOM-01 / 移动 / 交互未验证） |
| 真机运行通过 | ❌ 未完成 |
| 视觉验收通过 | ⚠️ 部分（5 视口真实截图已产出，人工终审待你确认） |

---

## 1. 问题根因

项目场景是 **2D-UI 架构**：`worldRoot` 是屏幕大小的 UI 节点，房间用 `Graphics` 画等距菱形，背景原本是一块纯色矩形。PR #146 只把 Canvas 设计分辨率对齐到窗口（UI 控件不再越界），但**场景本身**仍有三处问题：

1. `calculatePrototypeRoomScale` 用 **FIT**（`Math.min`），把房间缩成居中一小块菱形。
2. `worldRoot` 被硬 cap 在 `900 × 420`，横屏下房间只剩中间一块，四周是纯色 = “中间小地图 + 周围空”。
3. 背景是纯色矩形，不是场景内容。

→ 根因不是 Canvas，而是**场景缩放策略 + 背景资源**。

## 2. 修改前后差异

| 维度 | 修改前 | 修改后 |
|---|---|---|
| 房间缩放 | FIT（`min`），居中小菱形 | COVER（`max`）+ **内容可见性钳制** |
| 房间尺寸 | 被 cap 在 900×420 | 占满标题与操作行之间的整条 band |
| 背景 | 纯色 `Color(10,18,32)` | 真实场景底图（`MAP_MAIN_001_SCENE_01.jpg`）+ 程序化环境层兜底 |
| worldRoot | 有纯色填充、裁剪房间 | 透明，房间/背景都可透出 |
| 角色/机关 | 固定像素，但可能随 COVER 被裁到屏外 | 固定像素，且**钳制后保证在屏内** |
| 角色/移动比例 | `worldPixelsPerUnit` 固定 40，与房间缩放脱节 | 与 `levelRoomScale` 同步，头像不漂出地板 |

## 3. 修改文件

- `client/assets/scripts/world/prototype-layout.ts`：`calculatePrototypeRoomScale` 改为 COVER + 新增 `RoomScaleContentOptions`（`mustSee` / `safeHalfWidth` / `safeHalfHeight` / `contentMargin`）内容钳制。
- `client/assets/scripts/world/environment.ts`（新增）：`paintEnvironment` 程序化环境层（渐变 + 柔光 + 网格 + 浮尘 + 暗角），覆盖视口 ×1.1。
- `client/assets/scripts/engine/GameEntry.ts`：worldRoot 改透明、去 cap、背景改用环境层、`worldPixelsPerUnit = levelRoomScale`、resize 重绘、房间居中、`updatePrototypeRoomScale` 传入 spawn + 全部机关 + 真实窗口半宽高。
- `client/tests/prototype-layout.test.ts`：新增真实几何 / 内容可见性 / 移动一致性 / 坐标往返测试。
- `client/docs/landscape-acceptance-report.md`（本文件）、`client/docs/screen-fill-landscape-analysis.md`。

## 4. 地图与背景的设计方案

- **可行走区**：房间等距菱形（服务器 `prototype_bounds` = 0..12 × 0..8，GDD 4.2 投影）。地板用菱形 tile 绘制，边缘有描边，明确“可走”。
- **不可行走背景**：屏幕其余部分由 `MAP_MAIN_001_SCENE_01.jpg`（真实场景底图：神庙废墟）铺满，叠加程序化环境层（渐变/暗角）保证任何比例都不露底。背景区域明显区别于地板（色调/纹理不同），不会被误认为可行走。
- **不做横向/纵向拉伸**：所有精灵按原始宽高比 `fitWithin`，只做等比缩放。

## 5. 不同分辨率的适配策略

1. 设计分辨率 = 真实视口（EXACT_FIT 1:1，无二次拉伸）。
2. 房间以 COVER 为目标填满 band；随后按 **spawn + 全部机关** 的真实投影位置**钳制**缩放，保证关键内容不被裁。
3. 房间宽高比与屏幕不一致时，优先裁掉菱形**非关键**的上/下（长边），左右由场景底图延展。
4. 角色/机关/UI 固定像素尺寸，不随房间缩放变形。
5. HUD 仍在 band 外（标题/操作行/页脚），不与世界重叠。

钳制后 5 个验收视口的房间宽度占 band 宽度约 **69%–101%**（见 §6 数字与截图）：窄屏更满，20:9 更宽屏由场景底图补足两侧。

## 6. 自动化测试结果

本地 `pnpm test`（vitest）：

```
Test Files  24 passed (24)
Tests       172 passed (172)
```

新增/改写的关键用例：

- `projects a real diamond whose vertices fill the band on every acceptance viewport`：用**真实菱形四顶点**（非外接矩形）断言，纵向覆盖 band，横向 ≥ 65% band 宽。
- `keeps the spawn and every mechanism inside the visible screen with margin`：5 视口下 spawn + 3 机关全部落在安全区（含 24px 边距）内。
- `would crop the spawn without the clamp (regression guard for the cover bug)`：证明纯 COVER 会把 spawn 推出 720px 屏（|y| > 360），锁死该缺陷。
- `keeps the on-screen move speed identical on every aspect ratio`：屏幕位移速度与缩放/比例无关。
- `round-trips the spawn and every mechanism through the inverse projection` / `maps a tap on a mechanism back to its logical cell`：触控坐标 === 逻辑坐标。

> `GameEntry.ts` 仍含 `// @ts-nocheck`（历史遗留，见 §10），因此**不能**声称“GameEntry 通过完整 TypeScript 类型检查”；本轮以 vitest + 真实引擎运行为准。

## 7. Cocos 构建结果（真实）

本机 `C:\ProgramData\cocos\editors\Creator\3.8.8\CocosCreator.exe`（Electron 31.3.1 / Node 20.15.1）。

> 关键障碍与突破：WorkBuddy shell 默认设了 `ELECTRON_RUN_AS_NODE=1`，导致编辑器的 `--project/--build` 被 Node 当成非法选项（`bad option`，RC=9）。用 `env -u ELECTRON_RUN_AS_NODE -u NODE_OPTIONS` 后编辑器正常以 Electron 启动，构建成功。

| 目标 | 命令 | 结果 |
|---|---|---|
| 微信小游戏 | `--build "platform=wechatgame;debug=true;buildPath=build"` | ✅ `build Task (wechatgame) Finished in 1 min 44 s`，exit 0 |
| Web | `--build "platform=web-mobile;debug=true;buildPath=build"` | ✅ `build Task (web-mobile) Finished in 2 min 12 s`，exit 0 |

产物：`client/build/wechatgame/`（`game.js` / `game.json` / `project.config.json` / `assets` / `cocos-js` …）、`client/build/web-mobile/`（`index.html` / `assets` / `src` …）。

## 8. 微信开发者工具运行结果

**部分完成（导入 + 运行已验证；横屏 ROOM-01 / 移动 / 交互未验证）。**

- 用沙盒小游戏测试号 `wx79cbf35bf4aa11f3` 给 `build/wechatgame/project.config.json` 设置 appid，`wechatide auth -c WorkBuddy` 返回 `authorized:true, port:43982`；`open_project_window` 返回 `success:true, winId:s0` —— **项目已真实导入并打开**。
- `simulator_screenshot` 返回真实模拟器画面：`client/docs/screenshots/wechat-devtools-landscape.png`（314×677），可清楚看到登录页 UI：标题“无界之外 · Beyond the Unknown”、“我的进度 / 切换角色 / 招呼”、“登录并进入世界 / 放弃并返回世界”、“法则：尚未读取”。**这证明游戏在微信开发者工具模拟器中真实运行**。
- **横屏根因（已修）**：`build/wechatgame/game.json` 的 `deviceOrientation` 是 `portrait`（`project.config.json` 写 landscape 不够，运行以 `game.json` 为准）。改为 `"deviceOrientation":"landscape"` 后，模拟器截图从 314×677 变为 **487×225 / 308×143（2.16:1 横屏）**，并看到真实登录页 UI（截图 `wechat-landscape-login.png`）。
- 源侧：`client/build-configs/wechat-slim.json` 已声明 `orientation: landscape`；但无头 CLI 用 `--build "configPath=project://build-configs/wechat-slim.json"` 时在 `checkOptionsBeforeCommand` 校验失败（日志 `build/build-wechat-slim.log`），故本轮直接修正产物的 `game.json`。
- **仍阻塞（未验证）**：`automation_game_action` 一直返回 `cant find runtimeid by projectpath`（CJK 路径与 ASCII 路径 `C:\Users\SYANG\btu-wx` 都试过），且调用后项目窗口丢失（`project window not found`）。已尝试：`wechatide auth -c WorkBuddy`（authorized:true）、`open_project_window`（success, winId s0）、`cli.bat auto --auto-port 9420/9421`（返回 autoPort）、把构建复制到纯 ASCII 路径。仍无法在模拟器内点击登录/进入 ROOM-01/摇杆/机关。
- **最小人工步骤**：在开发者工具模拟器里点“登录并进入世界”→点“进入探索房间”，即可看到 ROOM-01；或在该机器上为 `wechatide` 开启自动化运行时（runtimeid）后再跑 `automation_game_action`。
- 5 视口横屏 ROOM-01 截图来自 web-mobile 真实引擎（§9），**不冒充**微信模拟器截图。

## 9. 五种分辨率的真实截图

来源：`build/web-mobile` 经本地静态服务器（127.0.0.1:7456）在 Chrome（Playwright 驱动，viewport 精确设置）真实运行；后端为本地真实栈（Postgres 18 + Alembic 0001→0016 + FastAPI，`LOCAL_LOGIN_ENABLED` 本地登录成功拿到 JWT）。**非 SVG / 非公式重绘。**

| 分辨率 | 比例 | 运行平台 | 场景 | Git commit | 结果 |
|---|---|---|---|---|---|
| 1280×720 | 16:9 | Chrome / Cocos web-mobile | ROOM-01 | 见 PR #149 头部 | ✅ 进入房间，角色/机关/地图可见 |
| 1560×720 | 20:9 | 同上 | ROOM-01 | 同上 | ✅ 同上，两侧由场景底图延展 |
| 844×390 | 横屏 | 同上 | ROOM-01 | 同上 | ✅ 同上 |
| 926×428 | 横屏 | 同上 | ROOM-01 | 同上 | ✅ 同上 |
| 932×430 | 横屏 | 同上 | ROOM-01 | 同上 | ✅ 同上 |

截图文件（每视口 login / world / room 三张，共 15 张）：
`client/docs/screenshots/<viewport>-3-room.png` 为本报告主证据（room 状态）。

逐张自检（视觉）：游戏有效画面已铺满；无大面积纯黑/无意义空白；背景为真实场景底图；角色完整在屏内；机关完整在屏内；角色与机关比例正常（固定像素）；UI 未被遮挡；无控件重叠。

## 10. 已知问题

1. **`// @ts-nocheck`**：`GameEntry.ts` 顶部仍是 `@ts-nocheck`。原因：该文件大量使用 Cocos 运行时类型与动态 `any`，且本地 `tsc` 无法解析 `cc`（引擎类型由编辑器/CI 提供）。风险：类型错误无法在本地被捕获。建议：在 CI 中启用 Cocos 类型声明后逐步移除；本轮未移除，**不声称其通过完整类型检查**。
2. **最宽比例下地板不占满 100% 宽度**：20:9 时菱形地板占 band 宽约 82%（窄屏 69%–101% 区间），两侧由真实场景底图延展。这是“内容不被裁”与“地板铺满”的几何取舍；若要求地板本身铺满 100%，需要引入相机跟随或加宽地图（属于玩法/关卡改动，本轮未做）。
3. **移动/交互的输入驱动未截图留证**：房间已进入、角色与机关已渲染、交互按钮存在；但“摇杆拖动移动 + 成功触发一次机关交互”的运行时留证本轮未完成（服务器权威校验距离，需要脚本化输入）。列为未验收。
4. **`~/package.json` 覆盖事故（需你确认）**：排查 Cocos CLI 时，`asar extract-file` 忽略了目标路径，把 Cocos 的 `package.json` 写到了 `C:\Users\SYANG\package.json`。该目录下**没有 `node_modules`/`.git`**（大概率不是活跃 npm 工程），但若你原本有个人 `~/package.json`，内容已被覆盖。我没有删除它，请你确认；需要的话我可以尝试从 Windows 卷影副本恢复。

## 11. 尚未完成的事项

- 微信开发者工具导入 `build/wechatgame/` 并截 5 视口图（§8）。
- 真机运行。
- 摇杆移动 + 机关交互的运行时留证（§10.3）。
- 远端 CI 结果（PR #149 已创建，等 CI 跑完）。
- 正式美术资源替换程序化环境层（当前用既有 `MAP_MAIN_001_SCENE_01.jpg` + 程序化层，未新增生成图；`assets/resources/P0-visual-placeholders.json` 仍标记为占位）。

## 12. PR 地址与提交 SHA

- PR：https://github.com/ansuns/Beyond-the-Unknown/pull/149
- 分支：`fix/client-screen-fill`
- 提交 SHA：见 PR 头部最新 commit（本报告随该 commit 提交）。
