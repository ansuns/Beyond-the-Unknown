# 本轮执行状态（2026-10-31）

对应提交：`342c7cd`、`2f15aa6`、`bd2b6c7`（分支 `fix/landscape-layout`，PR #146）
CI：client-ci / server-ci / art-tools-ci / package-budget 四项全绿。

## 一、已完成并有证据

| 项 | 结果 | 证据 |
|---|---|---|
| Git 交付 | 8 个本地提交拆成 4 个分支全部推送，PR #143/#144/#145/#146 | `git ls-remote`、PR 链接 |
| 主包体积 | 主包 **2.11 MB**、分包 **761 KB**、合计 2.85 MB | `tools/build-wechat.sh` 输出 |
| 微信本地分包 | 真实生成 `subpackages/resources/`，`game.json` 有声明，`settings.assets.subpackages` 已登记 | 开发者工具 `cli preview` → `√ preview` |
| 横屏布局 | 五种比例 16 控件零越界；844×390 下地图占屏 60%（原 43%） | `build/verify/landscape/*.png`、`build/verify/phone/*.png` |
| 房间端到端 | 登录→世界→进房→走近→回声→隐藏符号显现 | `build/verify/phone/05-echo-cast.png` |
| 五个房间 | ROOM-01～05 全部走进、施放组合、结算 `COMPLETED` | `tests/integration/test_all_rooms.py` 7 项 |
| 隐藏结局 | 五关通关后 `HIDDEN-ROUTE-01` 解锁，进入 `LV-HIDDEN-01` 触发 `H01-END` 并结算 | 同上 `test_five_rooms_unlock_the_hidden_ending` |
| 隐藏关门槛 | 新玩家直接进 `LV-HIDDEN-01` 返回 403 `Level is locked` | 同上 |
| 排行榜并发 | 幂等重算、不碰流水、同分同排名、回滚保留旧快照、4 路并发不重复不丢人 | `tests/integration/test_leaderboard_concurrency.py` |
| 事件源 | LOGIN / MOVE / RULE_CAST 三源接通 | PR #143 |
| RabbitMQ 重试 | 真 broker 上 失败→重试队列→TTL→回主队列→第三次进死信 | PR #143 |
| 加载服务 | 进度、缓存、在途去重、重试、耗尽、超时、版本不符、引用计数释放、资源加载、缺失回退 共 10 项 | `client/tests/asset-service.test.ts` |

测试总数：客户端 154、工具 82、服务端 97（含集成）。

## 二、明确没做成的

### 2.1 开发者工具模拟器截图

`cli preview` 能编译分包包体，但 `miniprogram-automator` 0.11 与 0.13 都能连上、所有指令超时：

```
connected
systemInfo failed: timeout waiting for automator response
currentPage failed: timeout waiting for automator response
```

所以横屏截图来自**同一份 Cocos 构建的 Web 目标**，在 844×390 视口下截取，不是开发者工具模拟器。真机未验证。

### 2.2 美术资源

按仓库清单当前真实状态：

```
Asset manifest: 112 required entries; 0 READY, 5 REVIEW, 0 GENERATED,
                1 PROCESSING, 106 MISSING, 0 BLOCKED.
```

垂直切片的 6 个文件（CHR_001 三张、MAP_MAIN_001 场景、机关两态、回声特效）已交付并在场景中加载（运行状态行显示「美术资源 6/6」），但**只有 REVIEW 而不是 READY**。

原因不是懒：清单对 READY 的要求是 `provenance.license`、`license_evidence`、`acceptance_evidence` 全部非空，且 `source_type` 属于批准集合。这些图是模型生成的，**目前没有任何证据能证明生成服务商的条款允许本项目商用**。按指令"不能在没有证据时宣称版权和商用授权完全合规"，状态保持 REVIEW 是唯一诚实的选项。

106 项 MISSING 是剩余最大工作量。

### 2.3 远程 Bundle

代码路径（配置、版本校验、超时、重试、失败回退）在 PR #145 里，但没有 CDN、没有备案域名、没有微信后台白名单，**一次真实远程加载都没跑过**。这部分只能是外部待办。

### 2.4 数值

`rule_catalog` 保持 `TUNING_REQUIRED`，测试用 `tuned_rules` 夹具临时注入并在结束时还原。GDD 13.2 的正式数值仍是待策划确认，没有编造。

## 三、本轮修掉的真问题

1. **布局写死常量**：所有 HUD 偏移按 960×640 预览调，手机横屏只有 443 高，导致地图只占 43%、性能面板压住登录按钮、房间按钮落在房间中央。改为按可用高度两段堆叠 + 紧凑档。
2. **房间缩放重复扣预留**：世界区已经扣过一遍 240 px，缩放函数又扣一次，房间被压到视口五分之一。
3. **`profiler.hideStats()` 缺失**：调试构建的性能面板覆盖按钮。
4. **回声失败提示是 API 原文**：`Rule target is invalid or outside the configured scope` 看起来像崩溃，其实是半径 2.0 的合法拒绝。改为"回声范围外：先走近隐藏的符号再施放"。
5. **截图脚本点空**：写死页面像素 (597,410)，在 844×390 下根本没点进房间。改为点 `HiddenObject` 节点。
6. **CI 类型与断言过时**：`asset-manifest-contract.d.mts` 只声明 4 个状态而实现统计 7 个；`validate-cocos-project.mjs` 用未压缩 uuid 断言场景，与引擎实际按压缩类 id 解析不符。

## 四、关于"全是黑的"

那张截图里 3/4 的黑是开发者工具面板底色 `(46,47,48)`，游戏画布是 `(10,18,32)`，占 `x 17–589 / y 136–399` = 572×263，宽高比 2.17，正好是 844×390 横屏手机。画面是铺满的。

但截图里确实有碰撞问题，见第三节第 1 条，已修。详细数据在 `2026-10-31-landscape-layout.md`。
