# 垂直切片验证记录（2026-10-31）

本文件只记录**本轮实际跑出来的证据**，以及**没有跑出来的部分**。判定标准沿用
`PROJECT-STATUS.md`：代码存在但未在本机跑通的一律记为“已实现未验证”。

## 1. 服务端

| 项目 | 结果 | 证据 |
|---|---|---|
| 单元 + 集成测试 | **76 passed**（连续两轮） | `pytest tests -q`，`TEST_DATABASE_URL` / `TEST_REDIS_URL` / `TEST_RABBITMQ_URL` 全部指向真实容器 |
| 数据库迁移 | 16 个 Alembic 版本在 `beyond` 与 `beyond_test` 上全部 upgrade 成功 | `alembic upgrade head` 日志 |
| RabbitMQ 重试与死信 | **真实 broker 通过** | `tests/integration/test_rabbitmq_retry.py`：失败 → 重试队列 → TTL 到期回主队列 → 第 3 次进 DLQ，`x-retry-count` 与 `x-failure-reason` 逐跳校验 |
| 三个事件源 | LOGIN / MOVE / RULE_CAST 全部接入任务进度 | `tests/integration/test_level_event_flow.py`：教学任务四项从 0/4 变为 4/4 并置为 COMPLETED；重复上报不重复累加；玩家间隔离 |
| 静态检查 | `ruff check app tests` 通过 | 无告警 |

容器：`docker compose up -d postgres redis rabbitmq`，均为 healthy。

## 2. 客户端（Cocos Creator 3.8.8）

| 项目 | 结果 | 证据 |
|---|---|---|
| 工程导入 | 通过 | 编辑器命令行构建读取 `Boot.scene`，无导入错误 |
| 脚本编译 | 通过 | 构建产物含 `BeyondTheUnknownGameEntry` |
| Web 构建 | 通过 | `client/build/web-desktop` |
| 微信小游戏构建 | 通过 | `client/build/wechatgame-slim`（3.88 MB） |
| 真实运行 | 通过（Web） | 见第 4 节截图，由 headless Chrome 驱动真实点击得到 |

### 本轮修复的真实缺陷

这些都不是“代码没写”，而是“写了但跑不起来”，只有在真机/真构建里才会暴露：

1. **场景组件被判为损坏**：`Boot.scene` 里脚本组件的 `__type__` 是完整 UUID，
   引擎按压缩类 ID（`8f7d9sTOlRPdZuDD3p+nYwx`）解析，导致整个入口组件被丢弃，
   构建成功但运行时黑屏。
2. **按钮文字不显示**：`Label` 与 `Graphics` 挂在同一节点，引擎拒绝第二个渲染组件，
   按钮只剩一个蓝色方块。
3. **UI 完全不响应点击**：运行时节点都在 `DEFAULT` 层，而 Cocos 只把指针事件派发给
   `UI_2D` 层节点。表现是画面正常、按钮按了没反应。
4. **改成 UI_2D 后全黑**：场景自带相机是透视相机且不含 UI_2D 可见性，Canvas 需要
   自己的正交 UI 相机，已补齐。
5. **背景图铺成一条窄带**：房间是等距投影，菱形区域的包围盒不是矩形，按矩形铺图
   就会变成斜条。改为整幅铺满视口、菱形轮廓叠在上层。

## 3. 包体

微信开发者工具实测：**首次提交被拒绝**，报错原文
`源码包超出最大限制, source size 5336KB exceed max limit 4MB`。

处理路径与结果：

| 步骤 | 体积 | 说明 |
|---|---:|---|
| 初始 debug 构建 | 12 MB | 含 sourcemap |
| release 构建 | 5.34 MB | 仍是 PNG 原图 + 全量引擎 |
| 资源压缩后 | 5.34 → 4.6 MB | 背景 1.3 MB PNG → 183 KB JPEG（不透明背景本就该用 JPEG）；精灵 205/81/94/90/110 KB → 148/61/74/70/73 KB（保留 alpha 的调色板量化，色差 mean≈2、p99.5≤27） |
| 引擎裁剪 | **3.88 MB** | 通过 `client/build-configs/wechat-slim.json` 的 `overwriteProjectSettings.includeModules` 关闭物理、骨骼、地形、瓦片、粒子、视频、WebView 等未用模块 |
| 开发者工具复验 | **通过** | `cli preview` 成功生成预览二维码，未再触发 4 MB 限制 |

复现命令：

```bash
"/c/ProgramData/cocos/editors/Creator/3.8.8/CocosCreator.exe" \
  --project "D:/workbuddy/byu/client" \
  --build "configPath=D:/workbuddy/byu/client/build-configs/wechat-slim.json"
```

## 4. 截图证据

位于 `build/verify/`（`build/` 不入库，需要时按下述命令复跑）：

| 文件 | 内容 |
|---|---|
| `01-menu.png` | 标题、按钮文字、地图背景 |
| `02-world.png` | 登录成功，状态行显示“已进入共享世界 · 在线实例 1/20 · 1e3c3db7”，角色精灵站在地图上 |
| `03-room.png` | 进入 ROOM-01，房间菱形、石灯机关精灵、法则可用 3/3 |
| `04-room-moved.png` | 点击移动后角色位置变化 |
| `05-echo-cast.png` | 点击“回声·显形”后状态行显示服务端校验结果 |

复跑：

```bash
cd client/build/web-desktop && python -m http.server 8080 --bind 127.0.0.1
node tools/drive-screenshot.mjs "http://127.0.0.1:8080/index.html" "D:/workbuddy/byu/build/verify" 1280 1100
```

截图脚本通过引擎自身的 `view`/`worldToScreen` 换算坐标，不再手算设计分辨率；
手算会差几十像素，点空和“按钮坏了”在截图上看起来一样。

## 5. 没有做到的部分

按严重程度排列，均未在本文档中计入“完成”。

1. **微信开发者工具模拟器截图未取得**。CLI `open` / `preview` / `auto` 均可调用，
   项目能编译、能生成预览码，但 `miniprogram-automator` 连接后所有指令
   （`systemInfo`、`currentPage`、`screenshot`）均超时，未能拿到模拟器画面。
   真机与模拟器的运行时表现因此**未验证**。
2. **回声特效的成功帧未截到**。`05-echo-cast.png` 记录的是服务端因距离不足拒绝
   （“Rule target is invalid or outside the configured scope”），证明请求链路通，
   但驱动脚本没能把角色走到可施法范围内，脉冲特效没有出现在截图里。
   该特效的实现与服务端成功路径分别由 `art-assets.ts` 和
   `test_level_event_flow.py` 覆盖。
3. **五房间与隐藏结局流程未验证**。仅 ROOM-01 走通。
4. **美术资源 106/112 仍为 MISSING**，P0 只交付 5 项，且全部停在 REVIEW：
   没有授权与验收签认，不进入 READY。
5. **AppID 已配置但登录未联通**：构建产物使用小游戏测试号 AppID，
   服务端 `WECHAT_APP_ID/SECRET` 未配置，`wx.login` 换 code 的真实链路未跑过。
   浏览器预览走的是 `LOCAL_LOGIN_ENABLED=true` 的本地登录，不是微信登录。

## 6. 本轮新增的开关

| 开关 | 默认 | 作用 |
|---|---|---|
| `LOCAL_LOGIN_ENABLED` | `false` | 允许 `APP_ENV != production` 时用浏览器设备码登录，仅用于本地预览；`app_env` 为 production/staging/prod 时强制失效 |
| `POST /api/v1/...` CORS | 仅本地登录开启时生效 | 网页预览跨端口调用 API 所需，正则限定 `127.0.0.1`/`localhost` |
