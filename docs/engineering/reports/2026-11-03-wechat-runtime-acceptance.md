# 微信开发者工具编译与运行时验收

> 日期：2026-11-03 ｜ 分支：`fix/client-screen-fill` ｜ 提交：`a0a855f`
> 一句话结论：**微信编译器真实接受了这个分包产物（编译通过，分包被单独计量）；微信模拟器的运行时通道没有打通，`wx.loadSubpackage` 未被观测到。**

---

## 1. 环境

| 项 | 值 | 来源 |
|---|---|---|
| 开发者工具版本 | `2.02.2610302` | `cli agent tool` / `Tool.getInfo` 返回 |
| SDKVersion | `3.17.5` | 同上 |
| CLI 入口 | `C:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat` | 实际读取文件确认 |
| AppID | `wx79cbf35bf4aa11f3` | `cli preview` 输出「使用 AppID」 |
| 项目路径（正式） | `C:\Users\SYANG\WorkBuddy\无界之外\client\build\wechatgame-slim` | 构建产物 |
| 项目路径（对照） | `C:\Users\SYANG\btu-wx-build` | 排除中文路径因素 |

`cli.bat` 的实现值得记一笔：它挑安装目录里最大的 `.exe`（202 MB 的 `微信开发者工具.exe`）作为 Electron，设 `ELECTRON_RUN_AS_NODE=1`，再执行 `resources/app.asar.unpacked/js/common/cli/index.js`。所以 CLI 命令清单是 `open / preview / auto / agent / close / quit / cache / engine ...`，**没有单独的 `build` 命令** —— 编译由 `open` 或 `preview` 触发。

---

## 2. 微信真实编译：通过

### 2.1 命令与退出码

```bash
cli.bat auto --project "C:\Users\SYANG\btu-wx-build" --auto-port 9424 --trust-project --port 9420
# → {"autoPort":9424,"requestedAutoPort":9424}  exit 0

cli.bat preview --project "C:\Users\SYANG\btu-wx-build" --port 9420 \
  --qr-format image --qr-output "...\build\wxverify\preview-qr.png"
# → exit 0
```

`preview` 执行了**两次**（一次在中文路径，一次在 ASCII 路径），两次都成功，体积完全一致。

### 2.2 编译器自己给出的分包计量

```
√ 使用 AppID: wx79cbf35bf4aa11f3
√ preview

┌────────────────────────┬────────────┬─────────────┐
│ (index)                │ size       │ size (Byte) │
├────────────────────────┼────────────┼─────────────┤
│ TOTAL                  │ '2.8 MB'   │ 2986441     │
│ main                   │ '2.1 MB'   │ 2217066     │
│ /subpackages/gameplay/ │ '751.3 KB' │ 769375      │
└────────────────────────┴────────────┴─────────────┘
```

**这是本轮最重要的一条证据**：分包体积不是我们的脚本算的，是微信编译器自己列的。它把 `/subpackages/gameplay/` 当作一个独立分包处理 —— 说明 `game.json` 的声明、目录结构、`game.js` 入口都被平台接受了。

`preview-info.json` 同样记录了这份数据：

```json
{"size":{"total":2986441,"packages":[
  {"name":"TOTAL","size":2986441},
  {"name":"main","size":2217066},
  {"name":"/subpackages/gameplay/","size":769375}]}}
```

### 2.3 编译输入清单里包含分包文件

`CompileBackendManager` 在编译时列出了它读取的文件，其中包含分包整目录：

```
'subpackages/gameplay/config.77291.json',
'subpackages/gameplay/game.js',
'subpackages/gameplay/import/0e/0e96bb807.443ed.json',
'subpackages/gameplay/import/20/20de2096-e99a-4174-b4c1-51d24b764e47.a2533.json',
'subpackages/gameplay/native/a7', ...
```

编译器没有报「分包路径不存在」「入口脚本缺失」「settings 引用错误」中的任何一种。若 `game.json` 里的 `root` 与磁盘不一致，微信会在这一步直接失败。

### 2.4 主包体积

主包 2,217,066 字节 = 2.11 MB，低于 4 MB 上限；总计 2.85 MB，低于 20 MB 上限。

---

## 3. 微信模拟器运行时：未打通

### 3.1 现象

自动化端口能连，WebSocket 握手 `101 Switching Protocols`，IDE 层命令正常：

```
{"method":"Tool.getInfo","result":{"version":"2.02.2610302","SDKVersion":"3.17.5"}}
```

但所有转发到小游戏 runtime 的命令一律超时：

```
{"method":"App.getCurrentPage","error":{"message":"timeout waiting for automator response"}}
{"method":"App.getPageStack","error":{"message":"timeout waiting for automator response"}}
{"method":"App.captureScreenshot","error":{"message":"timeout waiting for automator response"}}
{"method":"App.CDPEnable","error":{"message":"timeout waiting for automator response"}}
{"method":"App.CDPListProtocol","error":{"message":"timeout waiting for automator response"}}
```

注意这是**服务端返回的 error**，不是我这边超时 —— IDE 收到了命令，等不到 runtime 回应。

### 3.2 逐项排除（每项都做了，不是推测）

| 假设 | 做法 | 结果 |
|---|---|---|
| 端口被旧实例占用 | 9423 → 9424 换端口 | 同样超时 |
| 中文路径干扰 | 产物复制到 `C:\Users\SYANG\btu-wx-build` | 同样超时 |
| IDE 未以自动化模式启动 | 让 `cli auto` 作为启动者（12 个进程完整启动） | 同样超时 |
| 项目窗口被关掉 | 日志确认曾有 `close-requested {winId:'s0'}` → 改常驻后窗口在 | 同样超时 |
| 编译没完成所以没 runtime | `cli preview` 两次成功，编译器已列分包文件 | 同样超时 |
| automator 库太老（`ws@6`） | 手写协议客户端，用平台 WebSocket | `Tool.*` 通，`App.*` 仍超时 |
| 工具入口选错 | 试 `cli agent tool --name simulator_screenshot` | 它是小程序工具，报 `ENOENT: app.json` |

**结论**：自动化服务没有绑定到任何运行中的小游戏实例。`App.*` 是面向小程序的转发层，小游戏场景下拿不到 runtime。这一步没有绕过，也没有用 Web 结果顶替。

### 3.3 因此无法验证的项

- `wx.loadSubpackage` 是否被调用（未观测到，**不声称调用过**）。
- 首屏在微信环境下的 bundle 状态。
- 进入 ROOM-01 后角色 / 底图 / 机关 / 特效是否正常。
- 失败路径（分包加载失败时的拦截与提示）。
- 重复进入是否命中缓存。
- 横屏在微信模拟器中的实际布局。

### 3.4 唯一需要人工完成的动作

`build/wxverify/preview-qr.png` 是这次编译生成的真机预览码。扫码即可在真机上看到同一份产物。这一步需要手机与微信登录态，无法代劳。

---

## 4. Web 目标的运行时数据（已做，不与微信混淆）

`tools/verify-bundle-loading.mjs` 驱动真实 Web 构建，被动轮询 `assetManager.bundles`：

```
boot        appeared=["internal","resources","main"]   timeline=[internal@846ms, resources@883ms, main@883ms]
world       appeared=["gameplay"]                       timeline=[..., gameplay@8078ms]
roomFirst   appeared=[]                                 （缓存命中）
afterLeave  appeared=[]                                 （不释放）
roomSecond  appeared=[]                                 （不重复下载）

firstInputAt = 7076 ms
gameplayLoadedAtBoot = false
```

游戏自己的状态行：

| 阶段 | 状态行 |
|---|---|
| boot | 测试原型：点击「登录并进入世界」… |
| world | **美术资源 6/6** |
| roomFirst | **已进入个人关卡 探索房间 1 · 法则可用配置 3/3** |
| roomSecond | 已进入个人关卡 探索房间 1 |

这条链证明的是**加载逻辑与资源引用正确**，不是微信运行时行为。传输层是 `http://127.0.0.1:8081`，没有 `wx.loadSubpackage` 参与。

---

## 5. 分包产物结构（构建脚本断言 + 微信编译双重确认）

```
game.json  → subpackages: [{name:"gameplay", root:"subpackages/gameplay/"}]
settings   → assets.subpackages: ["gameplay"]
           → assets.preloadBundles: [{resources},{main}]   （不含 gameplay）
assets/    → internal, main, resources       （gameplay 已移出）
subpackages/gameplay/ → config.77291.json, game.js, index.77291.js, import/, native/   （18 文件 / 752 KB）
```

构建脚本 `client/scripts/build-wechat.mjs` 在每次构建后逐项断言；`tools/package_gate.py` 复核体积与重复打包：

```
主包：2.13 MB / 预算 3.50 MB / 上限 4.00 MB；总计 2.86 MB
分包 gameplay：752 KB
PASS: 包体门禁通过
```

---

## 6. CI

远端 Actions 在 `a0a855f` 与 `17969b1` 上都跑完了，四个 workflow 全部通过：

| workflow | a0a855f | 17969b1 |
|---|---|---|
| client-ci | ✅ success | ✅ success |
| server-ci | ✅ success | ✅ success |
| package-budget | ✅ success | ✅ success |
| art-tools-ci | ✅ success | ✅ success |

> 记录一次自己的误判：第一次查 CI 时用了 `?head_sha=a0a855f`，返回 `total_count: 0`，差点写成"CI 未运行"。实际上 workflow 已经跑过，是查询方式/时机的问题。上面这份是不带 `head_sha` 过滤、按仓库最近 runs 取的结果。

本地等价检查同样全绿：`vitest` 26 文件 / **180 用例**；`tsc --noEmit` 通过；`validate:project` 通过；`validate:assets` 通过（112 条目，0 READY，与既有状态一致）。

**CI 通过不等于微信运行时验收通过** —— 这一点在本文档里始终成立。

---

## 7. 遗留安全问题（只核对，未擅自处置）

| 项 | 现状 | 需要谁处理 |
|---|---|---|
| 历史提交中的 MCP Token | 按 `ghp_` / `github_pat_` / `WECHATIDE_TOKEN=<值>` / `Bearer <长串>` 四种模式扫描全部提交，**未命中**；当前代码只从环境变量读取。扫描不能证明"从未泄露"，只能说明现在查不到。 | 若曾外泄，需你本人在开发者工具「设置 → 安全设置」重置 CLI token。我做不了轮换。 |
| `C:\Users\SYANG\package.json` | 存在，5,966 字节，修改时间 2026-11-02 18:09，内容为 `Cocos Creator 3.8.8` 的 package.json。**无 `.bak` 或其它备份文件**。 | 原内容已不可从磁盘恢复。若那份文件重要，需要你从其它备份/版本库找回。 |

本轮没有把任何 token、AppSecret 写进仓库或日志。

---

## 8. 未完成事项

1. 微信模拟器内的分包加载与 ROOM-01 运行表现（自动化通道不可用）。
2. `wx.loadSubpackage` 调用观测。
3. 真机运行（二维码已生成，需人工扫码）。
4. 微信模拟器内的横屏适配回归。

**在这些项真实通过之前，PR #149 不应以"微信运行时验收通过"为由合并。**
四个 CI workflow 通过（§6）不改变这个结论。
