# 测试报告

- 执行时间：2026-10-31 09:47 – 10:10（GMT+8）
- 环境：Windows / Git Bash，Python 3.13.14，Node 22.22.2，npm 10.9.7
- 基线：`06187d4`（main）；另在 PR #126 分支 `c26d51e` 上跑过客户端全量

## 1. 客户端（PR #126 分支）

依赖装配：`npm install` 在 Node 22.22.2 下报 arborist `edgesOut` 错误，
改用 `npm install --legacy-peer-deps` 成功（47 包）。

| 命令 | 结果 |
|---|---|
| `npm run validate:project` | 通过：`Cocos Creator 3.8.8 project metadata, Boot scene, component UUID and local imports are valid.` |
| `npm run validate:content` | 通过：五常规房间 + 一隐藏房间，ID 唯一，目标与组合技、隐藏路线映射合法 |
| `npm run validate:assets` | 通过：112 条；0 READY / 0 IN_PROGRESS / 112 MISSING |
| `npm run typecheck` | 通过，无输出 |
| `npm test` | **143 通过 / 22 文件**（main 为 139，差异来自 #126 新增 4 项） |

单文件明细（`vitest run`）：

```
tests/p0-visual-placeholders.test.ts       4
tests/cocos-scene.test.ts                  2
tests/level-progression.test.ts            6
tests/gaze-lease-timing.test.ts            11
tests/world-play-session.test.ts           5
tests/level-content-contract.test.ts       10
tests/progress-client.test.ts              3
tests/room01-presentation.test.ts          3
tests/law-controller.test.ts               8
tests/prototype-combos.test.ts             3
tests/prototype-rule-options.test.ts       3
tests/progress-summary.test.ts             2
tests/map-socket.test.ts                   2
tests/prototype-layout.test.ts             11
tests/character-selection-session.test.ts  3
tests/wechat-network.test.ts               2
tests/prototype-mechanism-visual.test.ts   26
tests/asset-manifest-contract.test.ts      14
tests/rest-client.test.ts                  13
tests/map-session-reconnect.test.ts        2
tests/latest-position-sync-queue.test.ts   7
tests/game-entry-contract.test.ts          3
```

### 1.1 PR #126 变异检验

目的：确认新增的 4 项测试真的能拦住缺陷，而不是恒真断言。

1. 保留新测试，把 `client/scripts/level-content-contract.mjs` 回退为 main 版本；
2. 运行 `npx vitest run tests/level-content-contract.test.ts`：

```
 Tests  4 failed | 6 passed (10)
```

回退实现后 4 项新测试全部失败，恢复实现后 10 项全部通过。测试有效。

### 1.2 修复后复验

`join("\\n")` 修正为 `join("\n")` 后：

```
 ✓ tests/level-content-contract.test.ts (10 tests)
```

## 2. 服务端

依赖装配：`uv sync --group dev`（需 `pip install uv`；本机原先没有 uv）。

| 命令 | 结果 |
|---|---|
| `uv run ruff check .` | `All checks passed!` |
| `uv run pytest tests/unit tests/test_health.py tests/test_task_worker.py` | 修复前 **26 通过 1 失败**；修复后 **27 通过** |
| `uv run pytest tests/integration` | **17 skipped**（无 `TEST_DATABASE_URL` / `TEST_REDIS_URL`） |
| `alembic upgrade head` | 未执行，本机无 PostgreSQL |
| `docker compose` smoke | 未执行，本机无 Docker |

修复前失败详情：

```
FAILED tests/test_health.py::test_liveness_is_available_without_external_services
redis.exceptions.ConnectionError: Error 22 connecting to localhost:6379
```

根因：`app.main` 在模块导入时解析设置，lifespan 在 `APP_ENV != "test"` 时启动
Redis presence listener。CI 导出 `APP_ENV=test`，干净检出没有，所以该测试只在 CI 成立。

修复：`server/tests/conftest.py` 用 `setdefault("APP_ENV", "test")` 建立默认值。

## 3. 未执行的验证（不得视为通过）

| 验证 | 原因 |
|---|---|
| Alembic 升级/回滚 | 无 PostgreSQL |
| 服务端集成测试 17 项 | 无 PostgreSQL / Redis |
| outbox → RabbitMQ 投递 | 无 Docker |
| Cocos Creator 导入与构建 | 未安装 Cocos Creator |
| 微信开发者工具导入 | 未安装该工具 |
| Android / iOS 真机 | 无设备与 AppID |
| 资源导入无 UUID 冲突 | 依赖 Cocos 导入 |

## 4. 结论

可在本机复现的检查全部通过：客户端 143 项单测、类型检查、三项内容校验，服务端 27 项单测与 lint。
发布门禁仍有 112 项资源未 READY，因此**不具备发布条件**，这与测试通过并不矛盾。

## 5. 第二轮（2026-10-31 10:30–10:55）

拿到可写 PAT 后，改为「本地能跑的先跑、必须数据库的交由 CI」两段式验证。

| 检查 | 位置 | 结果 |
|---|---|---|
| PR #126 合并后 client CI | GitHub Actions | success |
| PR #127 `python` + `compose-smoke` | GitHub Actions | success |
| PR #128 `python` + `compose-smoke` | GitHub Actions | success |
| PR #129 `python` + `compose-smoke` | GitHub Actions | success |
| PR #130 `python` + `compose-smoke` | GitHub Actions | success |
| PR #131 首次 `python` | GitHub Actions | **failure**，见下 |
| PR #131 修复后 `python` + `compose-smoke` | GitHub Actions | success |
| `ruff check .` | 本机 | 通过 |
| `pytest tests/unit` | 本机 | **23 通过** |
| `pytest tests/integration` | 本机 | **19 skipped**（无 `TEST_DATABASE_URL`） |

### 5.1 PR #131 的失败与修复（如实记录）

首次 CI 失败在 `Unit and integration tests`，日志中的断言：

```
assert login.status_code == 200
E  assert 503 == 200
tests/integration/test_progress_flow.py:619
```

原因：新增的重算集成测试调用 `/api/v1/auth/login` 时没有像同文件其他测试那样覆盖
`get_wechat_code_provider`，微信 provider 未配置，登录返回 503。

修复：补上 `app.dependency_overrides[get_wechat_code_provider] = lambda: FakeWeChatProvider()`
并在 `finally` 中清理。修复后本地 19 项集成测试可正常收集，CI 转绿后合并。

### 5.2 新增的自动化守卫

`server/tests/unit/test_openapi_route_parity.py` 断言 `app.openapi()` 的路径集合与
`docs/engineering/api/openapi.yaml` 完全一致，且 `operationId` 不重复。

变异检验（按行插入，避开 CRLF 陷阱）：

| 动作 | 结果 |
|---|---|
| 在规范里插入 `/ghost-endpoint` | 失败：`documented but not served: ['/ghost-endpoint']` |
| 恢复后 | 2 项通过 |

该守卫在本地就拦住了 PR #131 新增端点未同步规范的问题，未进入 CI 环节。

## 6. 第三轮（2026-10-31 11:20–11:30）：修复 P0-1 与合规记录

### 6.1 修复的缺陷

`tools/strip_overlay.py` 第一版用**同一把尺子**（区域不透明占比）判断三种模式。
`crop` 模式对普通 RGB 图恒返回 100% 不透明，于是**文档里那条不带 `--force` 的裁边命令必然失败**。
此前每次执行都带 `--force`，把这个问题掩盖了。

修复后每种模式检查各自的失败条件：`alpha` 查角落是否被美术占据；`crop` 查裁切深度是否盖住角标
且不过量；`inpaint` 查输入是否可用。

### 6.2 新增测试

| 命令 | 结果 |
|---|---|
| `python -m pytest tools/tests -q` | **23 passed** |

覆盖：RGB 裁边不带 `--force`（该缺陷的回归用例）、裁切过浅/过深、alpha 清角与拒绝、
RGB 误用 alpha 模式、全透明图、异常尺寸（16×16 / 17×13 / 31×999 / 999×31）、
以及**直接以子进程执行 README 里原样命令并校验输出文件**。

变异检验：把旧逻辑（非 RGBA 直接判 100% 不透明）重新注入后 **14 项失败**，恢复后 23 项通过。

### 6.3 文档命令实跑

```
python tools/strip_overlay.py <背景原图> out.png --mode crop
  → wrote out.png (mode=crop crop_depth=7.000%, 1536x953)  exit=0

python tools/chroma_key.py <肖像原图> keyed.png --key 235,31,191
python tools/strip_overlay.py keyed.png out.png --mode alpha --box 0.84,0.93,1.0,1.0
  → wrote out.png (mode=alpha opaque_ratio=6.52%, 1024x1024)  exit=0
```

两条都**未使用 `--force`**，符合文档写法。

### 6.4 仍不能声称的部分

工具测试通过只说明工具行为正确，**不说明资源可发布**。授权与 AI 生成内容标识事项记录在
`assets/AI-content-compliance.md`，其中 C-1～C-4 未确认前，生成资源保持 `IN_PROGRESS`。

## 7. 第四轮（2026-10-31 11:35–11:50）：GDD 11.7 SCORE 奖励条件

### 7.1 结果

| 检查 | 结果 |
|---|---|
| `ruff check .` | 通过 |
| `pytest tests/unit` | 23 通过 |
| `pytest tests/integration`（本机） | 20 skipped，无 PostgreSQL |
| CI `python` | 通过（第 3 次提交后） |
| CI `compose-smoke` | 通过 |

### 7.2 连续三次 CI 失败记录

这一项改了三次才绿，前两次都是我的测试缺陷，全部保留记录：

| 次数 | 失败现象 | 根因 |
|---|---|---|
| 1 | `A value is required for bind parameter '8'` | `condition_config` 以内联字面量写入，SQLAlchemy 的 `text()` 把 `:8` 当绑定参数。改为 `CAST(:config AS jsonb)` + 参数绑定 |
| 1（连带） | `test_rule_flow` 三项失败（503/422/position 0.0） | 种子数据写在 `try` 之外，异常后 `finally` 未执行，`_set_test_content(True)` 留在共享库，污染后续模块 |
| 2 | `got Future attached to a different loop` | 复用应用全局 `engine`，它在 TestClient 的事件循环里创建；改在 `asyncio.run` 里用会跨循环并毁掉连接池 |

第 2 次失败同样连带 `test_rule_flow`——说明**集成测试之间共享数据库状态**，一处未清理会波及其他模块。
修复方式是各自建独立引擎并 `dispose()`，且种子一律放在 `try` 内。

### 7.3 局限

第 7.1 节的本机结论只有单测；集成测试的通过证据全部来自 CI。本机没有 PostgreSQL，**无法复现**，
这一点不能含混。
