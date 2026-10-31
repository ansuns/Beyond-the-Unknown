# 微信小游戏包体分析与整改报告

- 日期：2026-10-31
- 基线：`439567b`（提交前实测）
- 平台：微信小游戏，主包硬上限 4 MB
- 内部预算：**3.5 MB**（留构建波动余量）

## 1. 结论

| 指标 | 数值 |
|---|---:|
| 整改前提交包 | **5.34 MB**，被开发者工具拒绝：`source size 5336KB exceed max limit 4MB` |
| 当前提交包 | **2.85 MB**（2 985 985 字节） |
| 距 4 MB 硬限 | 剩余 1.15 MB |
| 距 3.5 MB 预算 | 剩余 0.65 MB |
| 重复内容 | 0 字节（按内容哈希去重后无相同文件） |
| 文件数 | 42 |
| 开发者工具结果 | `cli preview` 通过，生成预览码，无包体报错 |

包体已合规，但这只是入场条件；第 7 节列出仍未验证的部分。

## 2. 三种口径必须先分清

| 口径 | 大小 | 说明 |
|---|---:|---|
| 源码 `client/assets`（不含 .meta） | 940 KB | 编辑时的资产，含未被引用的文件 |
| 其中 .meta | 16 KB | 编辑器元数据，**不进包** |
| 其中 `assets/scripts` | 159 KB | TypeScript 源码，构建后编译进 `assets/main` |
| 其中 `assets/resources` | 790 KB | 会被打包的美术资源 |
| **构建产物**（`client/build/wechatgame-slim`） | **2.85 MB** | 微信实际统计的口径 |

把源码目录体积当成上传体积会严重误判：引擎（1.54 MB）只存在于构建产物里，
而 .meta、编辑器缓存、未被引用的源文件都不进包。

## 3. 分类与目录

| 类别 | 大小 | 占比 |
|---|---:|---:|
| engine（引擎运行时） | 1.54 MB | 54.0% |
| image（美术） | 774 KB | 26.5% |
| code（业务脚本 + 适配层） | 300 KB | 10.3% |
| config（场景/资源索引 JSON） | 262 KB | 9.0% |
| other | 6 KB | 0.2% |

| 目录 | 大小 | 占比 |
|---|---:|---:|
| `cocos-js/` | 1.54 MB | 54.0% |
| `assets/` | 1.14 MB | 39.1% |
| 根文件（`web-adapter.js`、首屏脚本等） | 173 KB | 5.8% |
| `src/` | 29 KB | 1.0% |

Bundle 分布：

| Bundle | 大小 | 位置 |
|---|---:|---|
| `internal`（引擎内置资源） | 289 KB | 主包 |
| `main`（场景与业务脚本） | 90 KB | 主包 |
| `resources`（美术） | 761 KB | 主包 |

## 4. 最大文件（Top 8）

| 文件 | 大小 |
|---|---:|
| `cocos-js/cc.f4447.js` | 1.54 MB |
| `assets/internal/import/0c/0cbe0b5a3.ee46a.json` | 243 KB |
| `assets/resources/native/a7/a75b862b….jpg`（主场景背景） | 183 KB |
| `assets/resources/native/20/20de2096….png`（角色立绘） | 149 KB |
| `assets/resources/native/96/96af4b29….png`（角色预览） | 137 KB |
| `web-adapter.js` | 100 KB |
| `assets/main/index.db140.js` | 87 KB |
| `assets/resources/native/c7/c78b8496….png`（石灯·未激活） | 74 KB |

## 5. 超限的真正原因

按贡献排序，不是“图片太多”这么笼统：

1. **引擎全量打包**：默认模块集包含 3D 物理（bullet wasm 458 KB）、Spine、
   DragonBones、地形、瓦片地图、粒子、视频、WebView，而游戏一样都没用。
   仅 bullet 的 wasm 就占 458 KB。
2. **美术用无损 PNG 存软渐变**：主场景背景 1024×682 存成 PNG 是 1.31 MB，
   同样内容 JPEG 只要 183 KB。角色预览 1536 高的原图 1.69 MB。
3. **首次提交还带 debug 构建**：含 sourceMap，12 MB，与线上无关但会误导判断。

## 6. 处理措施（按收益排序）

| 措施 | 收益 | 取舍 |
|---|---:|---|
| 引擎模块裁剪（`includeModules` 精确模块 id） | −2.0 MB | 裁掉物理/骨骼/地形/瓦片/粒子/视频/WebView；游戏未引用这些 API |
| 不透明背景转 JPEG（q84） | −1.1 MB | 背景无透明通道，视觉无可察差异 |
| 精灵调色板量化（256 色，保留 alpha） | −0.3 MB | 实测色差 mean≈2、p99.5≤27，远低于可见阈值 |
| 关掉 debug/sourceMap 构建 | （本就不该提交） | 发布构建固定 `debug=false` |

关键点：**没有降低分辨率、没有整图降质**。角色立绘仍是 1024 高，背景仍是 1024 宽，
只是换成了合适的存储格式；透明边缘由调色板量化保留 alpha，未被破坏。

原始无损文件保留在 `build/gen/raw/`，压缩版本与原始版本通过
`docs/engineering/assets/production/reports/*.json` 的 `raw_sha256` /
`output_sha256` / `optimized` 三段关联，可随时回溯。

## 7. 资源架构与加载

### 已落地

- `assets/resources` 是独立 Asset Bundle，主包只保留 `internal` + `main`（379 KB）。
- `app/modules/.../asset-config.ts` 用数据描述每个 bundle 的来源（包内 / 分包 / 远程），
  加载器不关心区别。
- `asset-service.ts` 统一处理：加载进度、超时（默认 12s）、指数退避重试（默认 2 次）、
  在途去重（两个界面同时请求只下载一次）、bundle 缓存、引用计数与释放、
  远程版本校验（版本不匹配直接报错而不是渲染旧图）。
- 进房间前先 `ensureBundle`，状态行显示真实进度；失败时显示具体原因并保留可操作界面。
- 构建方向已改为 `landscape`（`game.json` 实测 `deviceOrientation: landscape`）。

### 未完成，且不声称完成

1. **本地分包（WeChat subpackage）没有拆分成功**。已在构建配置中声明
   `bundles: [{root: "db://assets/resources", isSubpackage: true}]`，
   构建任务确实接收了该字段（日志可查），但产物仍无 `subpackages/` 目录，
   `game.json` 也没有 `subpackages` 段。引擎侧 `onAfterBuild` 只在
   `options.bundles[].isSubpackage` 为真且 bundle 已解析时才写入分包。
   下一步需要在编辑器构建面板勾选「配置为分包」再导出配置，或改用
   `stage=bundle` 的分包构建任务；**这不影响当前的包体合规**（2.85 MB 已在预算内）。
2. **远程资源 Bundle 未启用**。`ASSET_CONFIG.remote.enabled = false`，
   `baseUrl` 与 `version` 为空，没有 CDN、没有备案域名。代码路径（含版本校验、
   超时、重试、失败提示）已经写好，但**没有任何一次真实远程加载被执行过**，
   因此不计入“远程加载可用”。
3. **音频**：当前包内无音频，占比 0；后续加入必须走远程，否则会直接吃掉余量。

## 8. CI 门禁

- `tools/wechat_package_report.py`：按微信口径统计，输出分类、目录、Top 20、
  重复内容、源码/构建对照，可输出 JSON。
- `tools/package_gate.py`：主包超预算或超 4 MB 直接失败；声明为分包但产物缺失告警；
  重复内容超 64 KB 告警；音频超 512 KB 告警；`--strict` 时告警也算失败。
  `--from-report` 模式让 CI 在没有 Cocos 编辑器的 runner 上复检最后一次实测。
- `.github/workflows/package-budget.yml`：每次改动 `client/assets` 或构建配置时运行，
  并额外校验引擎裁剪项没有被悄悄改回来。

一键构建 + 统计（构建结束必然打印包体，不依赖人记得去测）：

```bash
bash tools/build-wechat.sh          # 默认预算 3.5 MB
# == build ==
# == package report ==
# 主包：2.85 MB / 预算 3.50 MB / 上限 4.00 MB
# PASS: 包体门禁通过
```

单独跑门禁：

```bash
python tools/package_gate.py --build client/build/wechatgame-slim \
  --config client/build-configs/wechat-slim.json
# 主包：2.85 MB / 预算 3.50 MB / 上限 4.00 MB
# PASS: 包体门禁通过
```

## 9. 验收证据

| 项 | 结果 | 证据 |
|---|---|---|
| Cocos 构建 | 通过 | `build/cocos/build-final.log`，`Finished in` |
| 包体统计 | 2.85 MB | `docs/engineering/reports/package-gate.json` |
| 微信开发者工具编译 | 通过 | `cli preview` 返回 `√ preview` 并生成预览码 |
| 4 MB 限制 | 不再触发 | 同一命令在 5.34 MB 时返回 `exceed max limit 4MB` |
| Web 运行画面 | 通过 | `build/verify/01..05*.png`，真实点击驱动 |
| 资源加载路径 | 走新服务 | 状态行显示“场景资源 / 美术资源 n/6” |

## 10. 仍未验证（不计入完成）

1. 微信开发者工具**模拟器截图**未取得：`miniprogram-automator` 连接后所有指令超时。
   因此横屏在真机/模拟器上的实际布局**未经肉眼确认**，仅有 `game.json` 的
   `deviceOrientation: landscape` 与 Web 端 1280×720 横屏截图。
2. 五个房间、隐藏结局的切换与加载耗时未测（当前只有 ROOM-01 有资源）。
3. 断网/弱网下的资源加载失败处理未在真机验证，只有代码路径与超时/重试逻辑。
4. 真机首屏加载时间未测。
5. `resources` 仍在主包内（见 7.2），因此“进入房间才下载”目前只是加载时机，
   不是真正的按需下载。
