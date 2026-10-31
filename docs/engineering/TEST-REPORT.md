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
