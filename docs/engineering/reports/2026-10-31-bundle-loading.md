# 分包加载取证：什么时候真正下载 `resources`

## 为什么需要这份记录

`game.json` 和 `settings.json` 只能证明包**被拆成了**什么，不能证明客户端**什么时候**去下载它。
旧实现里 `GameEntry.onLoad()` 无条件 `await assetService.ensureBundle("resources")`，
意味着开机就把整个分包拉下来——分包存在、但没有起到按需加载的作用。

## 测量方法

`tools/verify-bundle-loading.mjs` 用 CDP 驱动真实构建（Web 目标，1280×1100 窗口），
在页面里**被动轮询** `cc.assetManager.bundles._map`，记录每个 bundle 第一次出现的时刻，
同时由驱动在第一次点击前打时间戳。

> 早期版本尝试替换 `assetManager.loadBundle` 做拦截，结果**直接破坏了启动**：
> 引擎持有原函数引用，游戏停在加载页、只有 `internal` 被加载。因此改为纯被动观测。

## 实测结果

| 阶段 | 已加载 bundle | 时间线 |
|---|---|---|
| 首帧（未点击） | `internal`, `main` | `internal@807ms`, `main@807ms` |
| 点击"登录并进入世界" | — | 首次输入 `@7 011 ms` |
| 进入共享世界 | `internal`, `main`, `resources` | `resources@7 376 ms`（点击后 365 ms） |
| 进入房间（第一次） | 同上 | 无新记录——缓存命中 |
| 放弃返回后再进房间 | 同上 | 无新记录——缓存命中 |

**首次输入之前加载的 bundle：`internal` 和 `main`。`resources` 不在其中。**

## 结论

1. 启动阶段只加载 `main`（`internal` 是引擎内置）。启动不误拉 `resources`：✅
2. `resources` 在**第一次需要美术时**加载，当前流程是进入共享世界那一刻，而不是启动。
3. 进入房间不会重复下载：缓存命中，时间线没有新条目。
4. 退出房间不释放：`releaseBundle` 从未被调用（`releases = 0`）。这是有意为之——
   6 张图 761 KB，重复进出不应反复下载；`asset-service` 的引用计数/释放接口存在但游戏未使用。

## 这份证据的边界（必须说清楚）

- 传输层是 **Web 目标**（`http://127.0.0.1:8081`），不是微信运行时，
  所以**没有观察到 `wx.loadSubpackage` 调用**，也没有微信环境的耗时。
- Web 产物默认 `preloadBundles = ["resources","main"]`，即引擎会在启动时预加载它。
  为了让这次测量对应微信产物的配置，测量前把 Web 产物的 `preloadBundles` 对齐为 `["main"]`
  （与 `tools/wechat_subpackage.py` 对微信产物所做的一致），原始文件保存在
  `build/verify/bundles/settings-web-original.json`。
- 微信分包的真实下载时机、分包加载失败后的表现、真机首屏耗时，**仍未在开发者工具或真机上验证**。
  `cli preview` 通过不等于运行通过。

## 复现

```bash
# 1. 构建 Web 目标并起静态服务
bash tools/build-wechat.sh                     # 微信产物（含分包）
python -m http.server 8081 --bind 127.0.0.1    # 在 client/build/web-desktop 下

# 2. 测量
node tools/verify-bundle-loading.mjs "http://127.0.0.1:8081/index.html" build/verify/bundles
```

输出：`build/verify/bundles/bundle-loading.json`。
