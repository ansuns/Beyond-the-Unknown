# 微信小游戏包体优化与分包交付报告

> 本报告的所有数字都来自 `client/build/wechatgame-slim` 这一份真实构建产物（2026-10-31 15:32 构建），
> 由 `tools/wechat_package_report.py` 与 `tools/package_gate.py` 现场测量，不存在手工填写的体积。
> 此前的 `docs/engineering/reports/2026-10-31-package-budget.md` 里的 2.10 MB / 0.74 MB 是上一份产物
> 的读数，两份报告口径不一致时**以本报告为准**。

## 一、四个口径必须分开

| 口径 | 大小 | 说明 |
|---|---:|---|
| 项目源码目录 `client/assets` | 929 KB | 不含 `.meta`（16 KB），其中脚本 166 KB、`resources` 772 KB |
| Cocos 构建输出 `client/build/wechatgame-slim` | 2 988 602 B（2.85 MB） | 43 个文件，微信上传统计的就是这个 |
| 微信小游戏**主包** | 2 209 483 B（2.11 MB） | 4 MB 硬限、3.5 MB 内部预算的对象 |
| 微信小游戏**普通分包** `resources` | 779 119 B（761 KB） | 6 张正式美术 + 配置索引 |

源码体积与上传体积不是一回事：`.meta`、`library`、未引用资源都不进包，而引擎与微信适配层只在构建产物里出现。
把这两者混着说，就会得出"图太多导致超限"的错误结论——真正的超限原因是引擎全量打包。

## 二、包体构成（实测）

| 类别 | 大小 | 占比 |
|---|---:|---:|
| engine | 1.54 MB | 53.9% |
| image | 774 KB | 26.5% |
| code | 302 KB | 10.4% |
| config | 262 KB | 9.0% |
| other | 6 KB | 0.2% |

图片分布是"分包归位"的直接证据：产物中 9 张图，**7 张（766 418 B）在 `subpackages/resources/`**，
主包内只剩 25 978 B（引擎与适配层自带的小图标）。这一点以前是矛盾的——旧报告既说 `resources` 在主包里，
又给出 2.85 MB 的总量；现在两者不再打架：主包 2.11 MB 不含美术，美术在分包。

## 三、分包的真实配置

`game.json`：

```json
{
  "deviceOrientation": "landscape",
  "subpackages": [{ "name": "resources", "root": "subpackages/resources/" }]
}
```

`src/settings.json` 的 `assets`：

| 字段 | 值 |
|---|---|
| `preloadBundles` | `["main"]`（`resources` 已移除） |
| `subpackages` | `["resources"]` |
| `bundleVers` | `internal: e92ff`、`main: 4989b`、`resources: 6c149` |

三件事必须同时成立，缺一个微信就会按主包路径加载：

1. 目录真实搬到 `subpackages/resources/`（由 `tools/wechat_subpackage.py` 完成）；
2. `game.json` 声明 `subpackages`；
3. `settings.assets.subpackages` 登记且在 `preloadBundles` 里剔除。

Cocos 3.8.8 的 CLI 构建接受 `bundles[].isSubpackage` 却**不生成** `subpackages/`（日志里有字段、产物里没有目录），
所以这三步由构建脚本显式补齐。微信还要求分包根目录有 `game.js` 入口，否则报
`未找到 subpackages/resources/game.js`——资源包没有代码，写入空入口即可。

## 四、独立分包与远程资源

| 项 | 状态 |
|---|---|
| 普通分包 | 1 个（`resources`，761 KB） |
| 独立分包 | **0 个**。独立分包不能依赖主包资源，当前唯一的分包是美术资源，放成独立分包没有收益，故未拆 |
| 远程资源 | **0 字节**。`asset-config.ts` 的远程路径（HTTPS、版本校验、超时、重试、失败回退）已实现但 `remote.enabled = false`，没有 CDN、没有备案域名、没有微信后台白名单，**一次真实远程加载都没跑过** |
| 主包 + 全部分包 | 2.85 MB，远低于微信 20 MB 的本地总量限制 |

## 五、首屏实际加载什么

启动阶段（首帧之前）加载的 bundle 由 `settings.assets.preloadBundles` 决定，实测值只有 `main`。
`tools/verify-bundle-loading.mjs` 对运行中的客户端做了被动观测（每 50 ms 读一次已加载 bundle 缓存）：

| 时刻 | 事件 |
|---|---|
| 807 ms | `internal` 与 `main` 就绪（引擎内置 + 主 bundle） |
| 7 011 ms | 第一次点击（"登录并进入世界"） |
| 7 376 ms | `resources` 就位（进入共享世界需要美术时按需加载） |
| 进房间 | 无新增加载记录——缓存命中 |

也就是说：**主包只装引擎、脚本、配置与 `main` bundle；美术在第一次真正需要时才下载**，
而之前的客户端在 `onLoad` 里无条件 `ensureBundle("resources")`，等于开机就把整个分包拉下来，
分包形同虚设。这一点已改为首次使用时加载（见第六节）。

## 六、为让分包真正按需而改的代码

`GameEntry.prepareArt()` 原来在 `onLoad()` 里直接调用。现在改为：

- `onLoad()` 不再请求任何资源；
- 新增 `ensureArt()`：记忆化 + 失败后可重试，`artStatus` 记录 `idle/loading/ready/failed`；
- 进入共享世界时 `void ensureArt()`（首次需要美术）；
- 进入房间前若尚未就绪则 `await ensureArt()`，状态行显示"正在加载场景资源…"，失败会显示真实原因而不是白屏。

代价与事实：退出房间**不释放** bundle（`releaseBundle` 从未调用），这是有意的——只有 6 张图共 761 KB，
重复进出房间不应重复下载。`asset-service` 的引用计数与释放接口存在但游戏未使用，
所以"退出房间资源释放正确"这一条**没有实际执行过**，不做正面结论。

## 七、门禁与 CI

| 检查 | 结果 |
|---|---|
| `tools/build-wechat.sh` | 构建 + 分包 + 统计一条命令，必定打印体积 |
| 主包 ≤ 3.5 MB 预算 | 通过（2.11 MB，余量 1.39 MB） |
| 主包 ≤ 4 MB 平台上限 | 通过（余量 1.89 MB） |
| 分包目录/入口/索引/settings 登记 | 4 项全部校验，缺一即失败 |
| 重复资源 | 0 字节 |
| 门禁自身的测试 | `tools/tests/test_package_gate.py` 13 项，覆盖每种失败模式 |
| CI | `package-budget` 在资源或构建配置改动时运行 |

## 八、明确没有完成的（不计入交付）

1. **微信开发者工具里的运行画面仍未拿到**：`cli preview` 能编译通过（含分包），但
   `miniprogram-automator` 连接后所有指令超时（见 `2026-10-31-devtools-automation.md`），
   所以"分包在真机/模拟器上按需下载"只有产物结构与引擎代码路径为证，没有运行截图。
2. **远程 Bundle 未启用**：无 CDN、无备案域名、无白名单，属于外部条件。
3. **独立分包未拆**：当前资源结构下没有收益，也未验证过独立分包的启动路径。
4. **真机首屏耗时未验证**：7.3 s 这个数字来自桌面 Chrome 的 Web 目标，不是手机，也不是微信环境。
