# 微信原生分包：独立 Bundle 资源迁移与构建取证

> 分支：`fix/client-screen-fill` ｜ PR：#149 ｜ 日期：2026-11-03
> 结论先行：**分包已经真实产出**（`game.json.subpackages` 非空、`subpackages/gameplay/` 有文件、`settings.assets.subpackages` 已注册、首屏不下载）。
> **微信模拟器内的分包下载仍未验证** —— 详见 §8，不拿 Web 目标的结果冒充。

---

## 0. 目标与状态

| 目标 | 状态 | 证据 |
|---|---|---|
| 新建独立 Asset Bundle（非 `resources`） | ✅ | `client/assets/gameplay.meta`，`bundleName: gameplay` |
| 非首屏资源迁入新 Bundle | ✅ | 19 个 `.meta` 全部迁移，见 §3 |
| 保留原 `.meta` 与 UUID | ✅ | 19/19 保留，0 个重生成，见 §3.2 |
| `compressionType: "subpackage"` | ✅ | `gameplay.meta` 的 `userData` |
| 构建器真实识别该 Bundle | ✅ | `projectBundles` 含 `gameplay`；产物 `subpackages/gameplay/` 非空 |
| `game.json.subpackages` 非空 | ✅ | `[{"name":"gameplay","root":"subpackages/gameplay/"}]` |
| 发布目录存在 `subpackages/` | ✅ | 18 个文件 / 752 KB |
| 主包体积合规 | ✅ | 2.13 MB / 上限 4 MB |
| 首屏不依赖分包 | ✅ | 运行时实测：首帧内存中无 `gameplay`（§7） |
| 进入功能前加载分包 | ✅ | 点击「登录并进入世界」后 1.0 s 内加载完成 |
| 加载失败不继续 | ✅ | `enterFirstRoom` 增加了硬拦截（§7.3） |
| 两次清理构建结果一致 | ✅ | 三次构建逐文件 SHA256 相同（§6） |
| **微信模拟器内真实 `wx.loadSubpackage`** | ❌ **未验证** | DevTools 自动化通道仍不可用（§8） |
| **真机运行** | ❌ **未验证** | 同上 |

---

## 1. 为什么不把 `resources` 当分包

`resources` 是 Cocos 的**内置 Bundle**。它在 `settings.assets.preloadBundles` 里默认带自己：

```json
"preloadBundles": [{"bundle": "resources"}, {"bundle": "main"}]
```

实测（本次构建产物）：`resources` 在首帧就被加载，时间戳 `@883 ms`，与 `main` 同批。
把它标成 `subpackage` 只会得到一个"声明是分包、行为是预加载"的包 —— 既没有拆包收益，也和微信原生分包的语义相反。

上一轮 `3a30de3` 把 `resources.meta` 设成 `isSubpackage: true` + `compressionType: "subpackage"`，构建产物里 `game.json.subpackages` 仍是 `[]`。这次在独立目录上重做了同一件事，并补上了缺失的构建步骤。

---

## 2. 资源盘点

首屏（`Boot.scene`）**不引用任何图片资源**：界面全部由 `Graphics` + `Label` 程序化绘制。因此没有"必须留在主包的图片"。

| 类别 | 何时需要 | 体积 | 归属 |
|---|---|---|---|
| `maps/MAP_MAIN_001/scene`（房间底图） | 进入 ROOM-01 | 183 KB | 分包 |
| `characters/CHR_001/model`（角色） | 进入世界/房间 | 149 KB | 分包 |
| `characters/CHR_001/preview` | 角色选择 | 137 KB | 分包 |
| `mechanisms/M01-LIGHT-01/*`（机关两态） | 进入 ROOM-01 | 143 KB | 分包 |
| `effects/FX_ECHO_PULSE_01`（回声特效） | 房间内施放 | 74 KB | 分包 |
| `characters/CHR_001/portrait` | 当前运行时未使用 | 61 KB | 分包 |
| `P0-visual-placeholders.json` | 美术交付契约，`runtime_loadable: false` | 13 KB | 主包（`resources`） |

判断依据不是"看起来像首屏"，而是 `art-assets.ts` 的 `ART_PATHS`：六个 sprite 全部在 `prepareArt()` 里按需加载，`onLoad()` 不碰它们。

UI 与音频在美术清单里仍指向 `assets/resources/`。它们属于首屏，**不放进分包**，否则登录页会等一次分包下载。

---

## 3. 迁移

### 3.1 做了什么

```bash
git mv assets/resources/characters  assets/gameplay/characters
git mv assets/resources/effects     assets/gameplay/effects
git mv assets/resources/maps        assets/gameplay/maps
git mv assets/resources/mechanisms  assets/gameplay/mechanisms
```

`git mv` 保留工作区文件与 `.meta` 的一一对应，编辑器看到的仍是"同一个资源换了位置"，不是"删了再导入"。四个目录的相对层级完全不变，因此 `ART_PATHS` 的路径字符串不用改，只换 bundle 名。

### 3.2 UUID 校验

`tools/assert_asset_uuid.py` 把 `HEAD` 里的 `.meta` 与工作区逐个对比：

```
kept     19 meta files kept their uuid
changed   0 meta files got a NEW uuid
missing   1 committed meta files are absent from client/assets/gameplay
```

`missing` 那一条是 `P0-visual-placeholders.json.meta`，它本来就不迁移 —— 仍在 `assets/resources/`。

**中途发现并修掉的真问题**：第一次 `git mv` 之后，编辑器重扫目录，给 4 个**目录级** `.meta`（`characters` / `effects` / `maps` / `mechanisms`）换发了新 UUID。资源文件本身的 UUID 没动，但目录 UUID 也是 UUID。处理方式是：把这 4 个 uuid 写回 `HEAD` 的原值，删掉 `library/` 与 `temp/` 让 asset-db 完全重建，再构建 —— 之后 19 个全部稳定。不修的话，下次任何人清缓存重建都可能再次触发，且没人会注意到。

`notes:` `MAP_MAIN_001_SCENE_01.png.meta`（`e97132bc…`）没有对应图片文件，是历史遗留的空 meta。按"不删用户文件"的约定原样迁移，不参与构建，也不影响引用。

### 3.3 引用面

| 引用方式 | 位置 | 处理 |
|---|---|---|
| 代码路径加载 | `art-assets.ts` → `assetService.loadImage("resources", path)` | 改为 `GAMEPLAY_BUNDLE` |
| Bundle 加载 | `GameEntry.ts` → `ensureBundle("resources")` | 改为 `ensureBundle(GAMEPLAY_BUNDLE)` |
| Bundle 注册表 | `asset-config.ts` | 新增 `gameplay` 条目 |
| 场景引用 | `Boot.scene` | 只引用自身 + GameEntry 组件，**不含任何图片 uuid**，无需改 |
| Prefab | 项目无 Prefab | — |
| 美术清单 | `asset-manifest.v1.json`（112 条）/ `P0-visual-placeholders.json`（26 条） | 86 + 19 条 `expected_directory` 与 7 条 `files` 同步到新根 |
| 契约校验器 | `asset-manifest-contract.mjs` | 增加 `ART_BUNDLE_BY_CATEGORY` 映射，允许两个合法根 |

---

## 4. 构建器行为实测（本次最有价值的部分）

微信平台插件是 `.ccc` 字节码，无法直接阅读，因此用**四种配置分别构建**、看产物来判断。每条结论都有产物对照，不是推测。

| 配置写法 | `game.json.subpackages` | `assets/gameplay/` | `settings.assets.subpackages` | 结论 |
|---|---|---|---|---|
| 顶层 `bundles[]`（含 `name`/`root`/`isSubpackage`） | `[]` | 不存在 | `[]` | 字段名不被 schema 接受，整块忽略 |
| `.meta` 的 `userData`：`isSubpackage: true` + `compressionType: "subpackage"` | `[]` | ✅ 产出 | `[]` | Bundle 建出来了，但没当分包 |
| `bundleConfigs[]` + `compressionType: "subpackage"` | `[]` | ✅ 产出，但 **`assets/resources/` 整个消失** | `[]` | 它是白名单，未列出的 Bundle 不构建 |
| `packages.wechatgame.subpackages[]`（`{name, root}`） | ✅ 写入声明 | ✅ 仍在 `assets/gameplay/` | `[]` | **只写声明，不搬目录、不注册** |

对照证据：`vivo-mini-game` / `oppo-mini-game` 平台插件的 `hooks.js` 是明文，二者都实现了完整的搬迁：

```js
for (const bundle of options.bundles) {
  if (bundle.isSubpackage) {
    bundle.dest = path.join(options.paths.dir, prefix + bundle.name);
    bundle.scriptDest = path.join(bundle.dest, "main.js");
  }
}
// 然后才写 game.json: { name: prefix + name, root: prefix + name + "/" }
```

微信插件没有这段。它的 `IOptions` 里确实有 `subpackages?: {name, root}[]`，但实测只作用于 `game.json`。

**所以"声明分包"和"把资源打成分包"是两件事，后者必须由项目补齐。** 现在由 `client/scripts/build-wechat.mjs` 在构建末尾完成，并逐项断言：目录非空、有 `config.*.json`、有 `game.js`、`assets/` 下无残留、`game.json` root 一致、`settings` 已注册、不在 `preloadBundles`。任一项不满足即 `exit 1`。

顺带修掉的另一个问题：原脚本用 `spawnSync(stdio: "inherit")` 等编辑器退出。编辑器是 Electron GUI，某些运行下根本不会退出，管道被它派生的 worker 持住，`| tail` 挂了 9 分钟。现在改成"日志出现完成标记 + 产物连续 4 秒不变"判定，然后主动结束进程树。

---

## 5. 产物

```
build/wechatgame-slim/
├── game.js  game.json  project.config.json
├── assets/            ← 主包只剩内置包
│   ├── internal/  main/  resources/
├── subpackages/
│   └── gameplay/      ← 18 个文件
│       ├── config.77291.json
│       ├── game.js          （微信要求分包根必须有入口）
│       ├── index.77291.js
│       ├── import/  native/
├── cocos-js/  src/  engine-adapter.js  web-adapter.js
```

`game.json`：

```json
"subpackages": [{ "name": "gameplay", "root": "subpackages/gameplay/" }]
```

`settings.assets`：

```
subpackages     = ["gameplay"]
preloadBundles  = [{"bundle":"resources"},{"bundle":"main"}]   ← 不含 gameplay
projectBundles  = ["internal","resources","main","gameplay"]
```

体积（`tools/package_gate.py`）：

| 项 | 数值 | 限制 |
|---|---|---|
| 主包 | 2.13 MB | 4 MB |
| 分包 `gameplay` | 752 KB | — |
| 合计 | 2.86 MB | 20 MB |
| 文件数 | 45 | — |

```
主包：2.13 MB / 预算 3.50 MB / 上限 4.00 MB；总计 2.86 MB
分包 gameplay：752 KB
PASS: 包体门禁通过
```

---

## 6. 可复现性

`tools/artifact_fingerprint.py` 对产物逐文件 SHA256。三次独立构建（其中两次额外清理了 `temp/`，一次清到 `library/`）：

| 构建 | 条件 | 文件数 | 体积 |
|---|---|---|---|
| #1 | 清 `build/` | 45 | 2929 KB |
| #2 | 清 `build/` + `temp/` | 45 | 2929 KB |
| #3 | 清 `build/` + `temp/` + `library/` | 45 | 2929 KB |

```
a: 45 files, 2929 KB
b: 45 files, 2929 KB
OK: both builds produced the same files
```

三次 `sha256` 完全一致，没有时间戳或随机 id 泄漏进产物。

---

## 7. 运行时加载

### 7.1 方法

`tools/verify-bundle-loading.mjs` 用 CDP 驱动真实构建（Web 目标），被动轮询 `assetManager.bundles._map`，记录每个 bundle 首次出现的时刻，同时点「登录并进入世界」→「进入探索房间」→「放弃返回」→ 再进一次。

> 本机全局设了 `HTTP_PROXY`，Chrome 会把 `http://127.0.0.1:8081` 也发给代理，渲染出代理错误页 —— 表现为"没有 canvas、没有任何 bundle"，看起来像构建炸了。脚本现在固定带 `--no-proxy-server`。

### 7.2 结果

```
boot        appeared=["internal","resources","main"]        timeline=[internal@846ms, resources@883ms, main@883ms]
world       appeared=["gameplay"]                            timeline=[..., gameplay@8078ms]
roomFirst   appeared=[]                                      （缓存命中）
afterLeave  appeared=[]                                      （不释放）
roomSecond  appeared=[]                                      （不重复下载）

firstInputAt = 7076 ms
gameplayLoadedAtBoot = false
```

各阶段状态行（游戏自己的 HUD 文本，不是脚本推测）：

| 阶段 | 状态行 |
|---|---|
| boot | 测试原型：点击「登录并进入世界」连接微信沙盒与共享地图 |
| world | **美术资源 6/6** |
| roomFirst | **已进入个人关卡 探索房间 1 · 原型坐标/数值待实测 · 法则可用配置 3/3** |
| afterLeave | 已进入共享世界 · 在线实例 2/20 |
| roomSecond | 已进入个人关卡 探索房间 1 |

`美术资源 6/6` 是"分包加载成功后资源真的能用"的直接证据：六个 sprite 全部从 `gameplay` 取到并贴上了场景。`roomFirst` 进得去，说明底图、机关、角色都在。

### 7.3 失败路径

`GameEntry.enterFirstRoom()` 原来 `await this.ensureArt()` 之后**不看结果**就继续 —— 分包挂了也照样进房间，进去是一屋子占位图形。现在：

```ts
const ready = await this.ensureArt();
if (!ready) {
  this.setStatus(`场景资源加载失败，无法进入房间：${assetService.errorOf(GAMEPLAY_BUNDLE) ?? "未知原因"}`);
  return;
}
```

共享世界仍然容忍失败（每个 sprite 都有 `Graphics` 占位），状态行会显示原因。这个区别是刻意的：世界能用占位，房间不能。

并发与重复：`ensureArt()` 用单个 `artPromise` 去重，`assetService.ensureBundle()` 再用 `pending` map 去重，失败后 `artPromise = undefined` 允许重试。§7.2 的 `roomFirst`/`roomSecond` 两次进入都没有新增 bundle，就是这两层去重生效的结果。

---

## 8. 没做到的，以及为什么

| 项 | 状态 | 原因 |
|---|---|---|
| 微信模拟器里观察 `wx.loadSubpackage` | ❌ | DevTools 自动化三条通道都不可用：MCP `automation_game_action` 报 `cant find runtimeid by projectpath`；`cli.bat auto --auto-port` 返回端口但 `netstat` 无监听；`miniprogram-automator` 无法 spawn `.bat`。与上一轮 `client/docs/landscape-acceptance-report.md` §8 记录一致，本轮未改善。 |
| 真机运行 | ❌ | 同上，且需要真机扫码。 |
| 微信编译器是否接受该分包结构 | ⚠️ 未验证 | 未跑 `cli.bat preview`。产物结构符合微信要求（分包根有 `game.js`、root 与目录一致），但"符合规范"不等于"编译通过"。 |

**因此本文档不声称"微信运行时验收通过"。** 已证明的是：产物是结构正确的原生分包，且客户端在真实引擎里按需加载、加载后资源可用。微信沙盒里那一步仍是空白。

---

## 9. 复现

```bash
# 构建（含分包落地与断言）
cd client && node scripts/build-wechat.mjs

# 体积门禁
cd .. && python tools/package_gate.py --build client/build/wechatgame-slim \
    --config client/build-configs/wechat-slim.json --budget 3.5

# UUID 未变
python tools/assert_asset_uuid.py --before client/assets/resources \
    --after client/assets/gameplay

# 两次构建一致
python tools/artifact_fingerprint.py --build client/build/wechatgame-slim --out a.json
# 重新构建后再跑一次到 b.json
python tools/artifact_fingerprint.py --compare a.json b.json

# 加载时机（先构建 Web 目标并起静态服务）
bash tools/build-web.sh
python -m http.server 8081 --bind 127.0.0.1     # 在 client/build/web-desktop 下
node tools/verify-bundle-loading.mjs "http://127.0.0.1:8081/index.html" build/verify/bundles
```

产物：`build/reports/gate.json`、`build/reports/uuid-check.json`、
`build/reports/fingerprint-build*.json`、`build/verify/bundles/bundle-loading.json`。
