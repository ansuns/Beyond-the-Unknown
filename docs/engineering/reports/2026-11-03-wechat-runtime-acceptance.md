# 微信开发者工具编译与运行时验收

> 日期：2026-11-03 ｜ 分支：`fix/client-screen-fill` ｜ 被测提交：`746ea89`
> 结论：**微信编译器真实接受了这个分包产物（两次编译，分包独立计量且数字一致）；微信模拟器运行时仍未打通，`wx.loadSubpackage` 未被观测到；真机未跑。**

本文档记录的是"到了哪一步"，不是"完成了什么"。所有未验证项都明确标了未验证。

---

## 1. 环境

| 项 | 值 | 来源 |
|---|---|---|
| 开发者工具版本 | `2.02.2610302` | `Tool.getInfo` 返回 |
| SDKVersion | `3.17.5` | 同上 |
| CLI 入口 | `C:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat` | 读文件确认 |
| AppID | `wx79cbf35bf4aa11f3` | `cli preview` 输出 |
| 构建产物 | `client/build/wechatgame-slim` | `node scripts/build-wechat.mjs` |
| 预览码 | `client/build/wxverify/preview-qr.jpg` | `cli preview --qr-output` |

`cli.bat` 的实现：挑安装目录里最大的 `.exe`（202 MB 的 `微信开发者工具.exe`）当 Electron，设 `ELECTRON_RUN_AS_NODE=1`，执行 `resources/app.asar.unpacked/js/common/cli/index.js`。命令清单是 `open / preview / auto / agent / close / quit / cache / engine`，**没有独立的 `build`** —— 编译由 `open` 或 `preview` 触发。

> 微信 CLI 的 `--qr-output` 不管扩展名写什么，落盘的都是 JPEG 字节流。第一次生成的 `preview-qr.png` 其实是 JPEG（`ff d8 ff e0`），已按真实格式改名。

---

## 2. 微信真实编译：通过

```bash
cli.bat open    --project "…\client\build\wechatgame-slim" --port 9420
cli.bat preview --project "…\client\build\wechatgame-slim" --port 9420 \
  --qr-format image --qr-output "…\preview-qr.jpg"
```

两次独立执行（13:40 与 14:00），退出码均为 0，编译器自报的分包计量**完全一致**：

| 包 | 字节 |
|---|---|
| TOTAL | 2,986,928 |
| main | 2,217,553 |
| `/subpackages/gameplay/` | 769,375 |

```
┌────────────────────────┬────────────┬─────────────┐
│ TOTAL                  │ '2.8 MB'   │ 2986928     │
│ main                   │ '2.1 MB'   │ 2217553     │
│ /subpackages/gameplay/ │ '751.3 KB' │ 769375      │
└────────────────────────┴────────────┴─────────────┘
```

**这条是平台侧的认可**：`/subpackages/gameplay/` 是微信自己列的，不是我们的脚本算的。主包 2.11 MB < 4 MB，总计 2.85 MB < 20 MB。

`CompileBackendManager` 的编译输入清单里包含：

```
'subpackages/gameplay/config.77291.json',
'subpackages/gameplay/game.js',
'subpackages/gameplay/import/0e/0e96bb807.443ed.json',
'subpackages/gameplay/native/a7', ...
```

`game.json` 的 `root` 与磁盘不一致、或缺 `game.js` 入口，微信会在这一步就失败。

> 口径差异：`tools/package_gate.py` 统计磁盘文件（total 2,999,338 / 分包 769,746），微信统计编译后的包（2,986,928 / 769,375）。差 10 KB 左右，属正常，不要拿两个数字互相校验。

---

## 3. 设备侧诊断（本轮新增）

真机上没有控制台，验收人不可能打开 devtools，所以把判据放到屏幕和日志两处：

**状态行**（横屏屏幕上看得到）：

```
美术资源 6/6 · 场景包 412ms
```

前半是精灵数量（6 = 六个都从 `gameplay` 取到），后半是分包本身耗时。

**控制台**（真机调试时可见）：

```
[art] gameplay ready: bundle 412ms, sprites 6/6, total 690ms, resident [internal, resources, main, gameplay]
[art] gameplay reused from memory          ← 第二次进入
[art] gameplay failed after 12000ms: …     ← 失败时带原因
```

三条日志分别对应成功、复用、失败。`resident` 列表里没有 `gameplay` 就说明分包没进内存。

改动没有触碰加载逻辑：同一处 `ensureBundle`、同样的重试语义、同样的"没资源就不进房间"硬拦截。日志里不含 token、id、玩家数据。

---

## 4. 微信模拟器运行时：未打通

### 4.1 现象

自动化端口能连，WebSocket 握手 `101`，IDE 层命令正常：

```
{"method":"Tool.getInfo","result":{"version":"2.02.2610302","SDKVersion":"3.17.5"}}
```

转发到小游戏 runtime 的命令一律超时（**服务端返回的 error**，不是本地超时）：

```
App.getCurrentPage / getPageStack / captureScreenshot / CDPEnable / CDPListProtocol
→ timeout waiting for automator response
```

### 4.2 已排除（逐项都做过）

| 假设 | 做法 | 结果 |
|---|---|---|
| 端口被旧实例占用 | 9423 → 9424 | 一样 |
| 中文路径干扰 | 产物复制到 `C:\Users\SYANG\btu-wx-build` | 一样 |
| IDE 未以自动化模式启动 | 让 `cli auto` 当启动者（12 进程完整起） | 一样 |
| 项目窗口被关 | 日志确认曾有 `close-requested {winId:'s0'}`，改常驻后窗口在 | 一样 |
| 编译没完成 | `preview` 两次成功，编译器已列分包文件 | 一样 |
| automator 库太老（`ws@6`） | 手写协议客户端直连平台 WebSocket | `Tool.*` 通，`App.*` 仍超时 |
| 工具入口选错 | `cli agent tool --name simulator_screenshot` | 小程序专用，报 `ENOENT: app.json` |

**结论**：`Tool.*`（IDE 层）有响应，`App.*`（转发到小游戏 runtime）全部无人应答 —— 自动化服务没有绑定到任何运行中的小游戏实例。这一点没有绕过。

### 4.3 因此未验证

`wx.loadSubpackage` 是否被调用、首屏 bundle 状态、ROOM-01 资源表现、失败路径、缓存行为、微信模拟器内的横屏 —— **全部未验证**。

---

## 5. Web 目标的运行时数据（与微信无关，不可混用）

`tools/verify-bundle-loading.mjs` 驱动真实 Web 构建，被动轮询 `assetManager.bundles`：

```
boot        [internal, resources, main]        internal@846ms, resources@883ms, main@883ms
world       +gameplay                          gameplay@8078ms（首帧后 1.0s）
roomFirst   无新增                              缓存命中
afterLeave  无新增
roomSecond  无新增                              不重复下载
gameplayLoadedAtBoot = false
```

状态行：`美术资源 6/6` → `已进入个人关卡 探索房间 1`。

这证明加载逻辑与资源引用正确，**不证明微信运行时行为**。

---

## 6. 横屏布局回归

用 `tools/verify-landscape.mjs` 在五个视口驱动真实 Web 构建，六个维度分别判定：溢出、重叠、触摸冲突、被遮挡目标、最小触控尺寸、安全区。

### 6.1 当前基线（已提交代码）

| 比例 | overflow | overlaps | blocking | 被遮挡目标 | 安全区 | 最小触控 |
|---|---|---|---|---|---|---|
| 16:9 | 2 | 3 | 2 | 1 | 1 | 28 px |
| 18:9 | 2 | 3 | 2 | 1 | 1 | 28 px |
| 19.5:9 | 2 | 3 | 2 | 1 | 1 | 28 px |
| 20:9 | 2 | 3 | 2 | 1 | 1 | 28 px |
| 844×390 | 2 | 2 | 1 | 0 | 1 | 28 px |

`overflow` 的 2 项是 `WorldViewport` 和 `Room01Prototype`：前者是刻意大于视口的背景容器（铺满用），后者是房间菱形本身，两者都不是"控件跑出屏幕"，但仍被脚本计入。

**真实缺陷**：`HiddenObject × RoomEchoButton` 重叠 504 px²，遮住隐藏物体 64%，16:9 及以上都存在。隐藏物体是 ROOM-01 里必须点击的目标，被"回声 · 显形"按钮压住。同时它只有 28×28，低于 44 px 的触控推荐值。

### 6.2 两次修复尝试（均回退）

**尝试 A —— 把房间画到 playfield 带内**（`room.setPosition(0, playfieldCenterY, 0)`）：

| 比例 | overlaps | blocking | 被遮挡 |
|---|---|---|---|
| 16:9~20:9 | 3 → 1 | 2 → 1 | 1 → 0 |
| 844×390 | 2 → 6 | 1 → 4 | 0 → 1 |

大屏改善，小屏恶化。

**尝试 B —— 再把缩放按 playfield 高度钳制**（`safeHalfHeight = playfieldHeight/2`）：

| 比例 | overflow | overlaps | blocking | 被遮挡 | 安全区 |
|---|---|---|---|---|---|
| 16:9~20:9 | 2 → **0** | 1 | 1 | **0** | **0** |
| 844×390 | 2 → 0 | 2 → **10** | 1 → **10** | 0 | 0 |

大屏几乎完美，844×390 崩掉。

**结论：两次都回退。** 844×390 是 iPhone 横屏最常见的逻辑尺寸，用它的 10 处重叠换大屏的整洁不划算。当前提交仍是 6.1 的基线。

**根因判断**（下一轮用）：`roomControlLayout` 的紧凑阈值是 `size.height < 320`，844×390 的高度 390 不触发紧凑档，按钮用 42 px 高、间距 10 px，把 playfield 压到 244 px；房间再按整屏 COVER，自然压到按钮上。先按视口高度分级（844×390 走紧凑档），再谈房间上移，代价小得多。

### 6.3 未做的部分

真机横屏（刘海、圆角、底部手势条、20:9 实机）未验证 —— 依赖真机，见 §7。

---

## 7. 真机验收：未完成

已准备：`client/build/wxverify/preview-qr.jpg`（14:00 生成，与 §2 的产物同源）+ `docs/engineering/reports/2026-11-03-device-acceptance-checklist.md`（面向非开发人员，逐项打勾）。

未做：扫码、启动、观察分包下载、进入 ROOM-01、缓存、真机横屏。

**这一步只能由持手机的人完成。**

---

## 8. CI

| workflow | a0a855f | 17969b1 | 746ea89 |
|---|---|---|---|
| client-ci | ✅ | ✅ | ✅ |
| server-ci | ✅ | ✅ | ✅ |
| package-budget | ✅ | ✅ | ✅ |
| art-tools-ci | ✅ | ✅ | ✅ |

> 记录一次自己的误判：第一次查 CI 时用了 `?head_sha=` 过滤，返回 `total_count: 0`，差点写成"CI 未运行"。实际 workflow 已跑完，是查询方式的问题。上面这份不带 `head_sha` 过滤。

本地等价检查：`vitest` 26 文件 / 180 用例；`tsc --noEmit`；`validate:project`；`validate:assets`（112 条目，0 READY，与既有状态一致）。

**CI 通过不等于微信运行时验收通过。**

---

## 9. 安全事项

| 项 | 现状 | 需要谁处理 |
|---|---|---|
| MCP Token | 历史按 `ghp_` / `github_pat_` / `WECHATIDE_TOKEN=<值>` / `Bearer <长串>` 四种模式扫描，未命中；当前代码只从环境变量读。扫描不能证明"从未泄露"。 | 若曾外泄，需本人在开发者工具安全设置里重置。 |
| CLI 访问令牌 | 未设置。只在需要 CLI HTTP 自动化时才需要，本轮 `open` / `preview` / `auto` 都不需要它。 | 不需要处理。 |
| `C:\Users\SYANG\package.json` | 5,966 字节，2026-11-02 18:09，内容为 Cocos Creator 3.8.8 的 package.json。复查了 Temp 目录（11-01~11-03 无同名文件）与家目录（无 `.bak`），**无恢复线索**。 | 原内容无法从磁盘恢复，需从其它备份找回。 |

本轮没有把 token、AppSecret 写进仓库或日志。

---

## 10. 未完成

1. 微信模拟器内的分包加载与 ROOM-01 表现（自动化通道不可用）。
2. `wx.loadSubpackage` 观测。
3. 真机运行（二维码已生成）。
4. 真机横屏。
5. 布局遗留：`HiddenObject` 被按钮遮挡 64%、触控 28 px。已给出根因与下一轮方向（§6.2），本轮未修。

**在这些项真实通过之前，PR #149 不应以"微信运行时验收通过"为由合并。**
