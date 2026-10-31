# 已知问题

- 更新：2026-10-31
- 分级：**P0** 阻断发布 / **P1** 阻断阶段目标 / **P2** 需跟踪

## 本轮修复

| 编号 | 问题 | 证据 | 处理 |
|---|---|---|---|
| KI-01 | PR #126 新增测试用转义字面量 `"\\n"` 拼接错误信息，与同文件既有测试不一致 | `client/tests/level-content-contract.test.ts` 第 60–84 行 | 已改为真实换行，10 项测试通过 |
| KI-02 | 服务端测试套件不自治：`test_liveness_is_available_without_external_services` 在未导出 `APP_ENV=test` 时连 Redis 失败 | 干净环境下 26 通过 1 失败 | 新增 `server/tests/conftest.py` 默认 `APP_ENV=test`，27 通过 |
| KI-03 | `.gitignore` 的 `*` 规则使 `docs/` 目录不再被 git 进入，**新增文档无法提交** | `git check-ignore -v` 命中 `*` | 增加 `!docs/` 与 `!docs/**` |

## 待处理

| 编号 | 级别 | 问题 | 证据 | 影响 | 下一步 |
|---|---|---|---|---|---|
| KI-04 | P0 | P0 正式资源 0 项 READY | `npm run validate:assets` → 112 条全 MISSING | 发布门禁 `validate:release-assets` 无法通过 | 见 KI-05/06/07 |
| KI-05 | P0 | 生图后端不返回 alpha 通道，`background=transparent` 只画棋盘格 | 5 次生成全部为 PNG color type 2；棋盘格采样 `(252,251,249)` / `(229,227,223)` | 资源无法直接导入与排序 | 已提供 `tools/chroma_key.py` 色键方案 |
| KI-06 | P0 | 每张生成图右下角烘焙 `AI生成` 与 WorkBuddy 标识 | 原图裁切复核 | 资源不可作为正式美术；擦除属处置合规标识 | **需项目方决策**，工程侧不擅自处理 |
| KI-07 | P0 | 独立调用之间角色形象漂移 | 披风青绿/深绿/绿，眼睛蓝/绿/棕 | 无法满足第 18 章“同一设计稿” | 确定基准图后改图生图 |
| KI-08 | P1 | 17 项服务端集成测试在无数据库时全部跳过 | `pytest tests/integration` → 17 skipped | 结算/排行/赛季只有集成覆盖，本机不可验证 | 提供 PostgreSQL+Redis 或 Docker |
| KI-09 | P1 | 结算、三榜、赛季缺少纯函数级单测 | 仅 `tests/integration/test_progress_flow.py` | 逻辑回归只能在有库环境发现 | 抽出评分与排名纯函数并补单测 |
| KI-10 | P2 | `npm install` 在 Node 22.22.2 下报 arborist `edgesOut` 错误 | `npm error Cannot read properties of null (reading 'edgesOut')` | 本地装配需 `--legacy-peer-deps`；CI 用 Node 20 未复现 | 择机提交 lockfile 并复核 CI |
| KI-11 | P2 | 仓库无 `package-lock.json`，CI 用 `npm install` 非确定性装配 | `.github/workflows/client-ci.yml` | 依赖漂移风险 | 生成并提交锁文件后改用 `npm ci` |
| KI-12 | P2 | 事务性 outbox 只在 CI 的 docker smoke 中验证 | `server-ci.yml` 的 outbox relay 步骤 | 本机无法复现 | 同 KI-08 |
| KI-13 | P2 | 客户端仅 1 个场景 `Boot.scene`，艺术资源目录为空 | `client/assets/scenes`、`client/assets/resources` | 运行期看到的是程序化占位表现 | 随 KI-04 一并推进 |

## 环境限制（非缺陷）

| 项 | 现状 |
|---|---|
| Docker | 未安装，`docker compose` smoke 无法本地执行 |
| Cocos Creator 3.8.8 | 未安装，导入/构建无法验证 |
| 微信开发者工具 | 未安装，小游戏导入与真机无法验证 |
| GitHub 凭据 | 无，无法推送与合并 PR |
