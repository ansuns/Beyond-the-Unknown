# 页面铺满：从「固定 1280×960 的框」到「一设计单位 = 一 CSS 像素」

日期：2026-10-31
状态：Web 目标已实测通过；微信小游戏已重建并过包体门禁，模拟器画面仍待取得

## 1. 问题与实测基线

用户反馈：页面没有铺满网页/手机。

用 `tools/verify-fullscreen.mjs` 在 6 个视口实测，修复前：

| 视口 | 窗口 | 画布 CSS 尺寸 | 画布/窗口 | 引擎/画布 | 覆盖率 |
| --- | --- | --- | --- | --- | --- |
| desktop-1280x720 | 1280×720 | 1280×960 @ (5,85) | 1.333 | 1 | **1.333** |
| phone-16x9 | 1280×720 | 1280×960 @ (5,85) | 1.333 | 1 | **1.333** |
| phone-18x9 | 1440×720 | 1280×960 @ (80,85) | 1.185 | 1 | **1.185** |
| phone-19.5x9 | 1560×720 | 1280×960 @ (140,85) | 1.094 | 1 | **1.094** |
| phone-20x9 | 1600×720 | 1280×960 @ (160,85) | 1.067 | 1 | **1.067** |
| phone-844x390 | 844×390 | 1280×960 @ (5,85) | 3.733 | 1 | **3.733** |

覆盖率 = 画布面积 / 窗口面积 × 引擎视口面积 / 画布面积。**大于 1 表示画布比窗口大**，
玩家只看到左上角一块；844×390 时是 3.73 倍。

`engine/canvas = 1`、四边 bars 全 0，说明引擎自身没有在画布内留黑边——问题在画布本身。

三个根因：

1. `build-templates` 里的 web 模板把 `#GameDiv` 写死成 `width:1280px; height:960px`，
   外加 5px 黑边框、圆角和投影。
2. 模板的 `<h1 class="header">` 和 `<p class="footer">` 占据文档流，把画布往下顶了 85 px。
3. 项目设置里的设计分辨率是常量 960×640。固定设计分辨率只能选一个缩放系数，
   只有屏幕恰好 3:2 时可视区域才等于屏幕，其余比例必然被裁切或留边。

修复前的 844×390 截图：只能看到标题的左半截和左侧两个按钮，右侧「招呼」「放弃并返回世界」
完全在窗口外，页面其余部分是白底。

## 2. 修复

### 2.1 设计分辨率跟随真实视口

新增 `client/assets/scripts/engine/screen-fit.ts`（无引擎依赖，可单测）：

- `readViewport(host)`：优先 `wx.getWindowInfo()`，其次 `innerWidth/innerHeight`，
  再次 `visualViewport`，最后 `screen`；零值和过小值（< 240×160）一律视为「还没上报」。
  微信桥抛异常时降级到浏览器视口，不让启动失败。
- `resolveDesignResolution(viewport)`：一设计单位 = 一 CSS 像素。
- `shouldRefit(current, next, tolerance=2)`：只对真实尺寸变化重排，忽略滚动条出现、
  移动端地址栏收起这类 1 px 抖动。

`GameEntry.onLoad()` 在 `buildShell()` **之前**调用 `applyScreenFit()`，
用 `ResolutionPolicy.EXACT_FIT` 安装设计分辨率。

选 `EXACT_FIT` 而不是 `SHOW_ALL` 是刻意的：`SHOW_ALL` 的语义是「保证整个设计矩形可见」，
这正是留边（letterbox）的定义；而且画布追赶 resize 的那一帧里两者必然不一致。
`EXACT_FIT` 永远覆盖画面。

### 2.2 Web 外壳

新增 `client/build-templates/web-desktop/style.css`。Cocos 会把
`build-templates/<platform>/` 覆盖到构建产物，所以这个修复随每次构建生效，
不是手改产物：

- `html, body` 100% 高、`overflow:hidden`、背景 `#0a1220`（与游戏 clear color 一致，
  避免加载瞬间的白闪）。
- `#GameDiv` 用 `!important` 覆盖模板写在行内的 `width:1280px;height:960px`，
  改成 `position:fixed; inset:0`，去掉边框、圆角、投影。
- `.header` / `.footer` 隐藏（它们占的正是那 85 px）。
- `#Cocos3dGameContainer` / `#GameCanvas` 100%×100%。

### 2.3 运行中改窗口

新增 `relayoutShell(sizeOverride?)`：所有位置都来自 `computeShellLayout()`，
它读可视尺寸，所以重排只需重跑它。背景、世界视口、6 个按钮、摇杆的 Graphics 都重绘，
房间则用相同状态重画（`lastRoomRender`）并重新挂美术。

这里有一个实测出来的坑：**resize 时不能立刻 `view.getVisibleSize()` 读回新尺寸**。
Cocos 要到下一 tick 才把设计分辨率应用到 frame，所以那一刻读到的还是旧值。
第一版就是在 `handleViewportChange()` 里设完分辨率马上重排，结果 1280×720 缩到 844×390 后
「登录并进入世界」被算到 x=-515，整个跑到屏幕左边外面。
修复：把新尺寸作为参数显式传进 `relayoutShell(next)`。

## 3. 实测结果（修复后）

`node tools/verify-fullscreen.mjs http://127.0.0.1:8123/index.html build/verify/fullscreen-after`

| 视口 | 窗口 | 画布 | 设计分辨率 | 可视尺寸 | 覆盖率 |
| --- | --- | --- | --- | --- | --- |
| desktop-1280x720 | 1280×720 | 1280×720 | 1280×720 | 1280×720 | 1 |
| phone-16x9 | 1280×720 | 1280×720 | 1280×720 | 1280×720 | 1 |
| phone-18x9 | 1440×720 | 1440×720 | 1440×720 | 1440×720 | 1 |
| phone-19.5x9 | 1560×720 | 1560×720 | 1560×720 | 1560×720 | 1 |
| phone-20x9 | 1600×720 | 1600×720 | 1600×720 | 1600×720 | 1 |
| phone-844x390 | 844×390 | 844×390 | 844×390 | 844×390 | 1 |

四边 bars 全 0，覆盖率全 1：**画布 = 窗口 = 设计分辨率 = 可视尺寸**。

运行中 resize（不重新加载）：1280×720 → 844×390，
覆盖率 1 → 1，设计分辨率 1280×720 → 844×390，
**新视口外的控件数 0**（逐节点读 `getBoundingBoxToWorld()`，阈值 ±422 / ±195）。

节点级证据（resize 后，可视 844×390）：

```
Title              x[-151,151] y[148,185]
Status             x[-162,162] y[121,147]
ProgressSummary    x[-49,50]   y[61,84]
RulesStatus        x[-42,42]   y[-142,-116]
WorldViewport      x[-412,412] y[-105,49]
LoginButton        x[-412,-262] y[-185,-145]
EnterLevelButton   x[-70,70]    y[-185,-145]
ReturnButton       x[262,412]   y[-185,-145]
ProgressButton     x[-412,-324] y[88,118]
CharacterButton    x[-44,44]    y[88,118]
EmoteButton        x[324,412]   y[88,118]
```

全部落在 ±422 / ±195 之内。

## 4. 回归

| 检查 | 结果 |
| --- | --- |
| `npx vitest run`（客户端） | 24 文件 / **166 项通过**（新增 screen-fit 12 项） |
| `node --test tools/tests/layout-geometry.test.mjs` | 15 项通过 |
| `npx tsc --noEmit` | 通过 |
| `tools/verify-landscape.mjs` 五种比例 | 菜单/世界阶段 越界 0、重叠 0、触控冲突 0、遮挡 0、安全区 0 |
| `tools/build-wechat.sh` | 主包 2.11 MB / 预算 3.50 MB，总计 2.86 MB，PASS |

## 5. 未完成 / 边界

1. **房间状态未复测**。`verify-landscape.mjs` 的 room 阶段需要真实后端
   （`/api/v1/auth/login` → `/map/enter` → `/level/...`），而本机没有 Docker，
   PostgreSQL 起不来，所以本次 room 行实际是菜单态。日志里的
   `tap SettlePrototypeRoom: node not found` 就是证据，不能当作房间通过。
2. **微信模拟器画面仍未取得**。微信产物已重建（`deviceOrientation: landscape`、
   `subpackages: [resources]`、产物内无写死的画布尺寸），设计分辨率走同一条
   `wx.getWindowInfo()` 路径，但**没有开发者工具或真机截图**，
   所以微信端「已铺满」目前是代码路径 + 产物结构的推断，不是运行证据。
3. `cc_exact_fit_screen="false"` 保持原样：设计分辨率已由 `EXACT_FIT` 策略接管，
   改成 `true` 会让引擎绕过策略直接拉伸，反而破坏 1:1 映射。

## 6. index.html 的两处属性

CSS 改不到 `<meta>`，所以这两处由 `tools/patch-web-shell.mjs` 在构建后修补，
并带断言（目标串找不到就报错退出，不会静默失效）：

- `screen-orientation: portrait` → `landscape`。横屏游戏不该要求竖屏，
  个别移动浏览器和 App 内 webview 会照此锁定方向。
- viewport meta 追加 `viewport-fit=cover`。不加的话 iOS 会把页面塞进安全区里留边，
  正好和「铺满」相反。

没有用 `build-templates/web-desktop/index.html` 整份替换，因为那样会连编辑器生成的
script 标签一起写死，而开启 md5Cache 后这些文件名是带哈希的。
