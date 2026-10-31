# 资源清单与交付门禁

## 当前事实

截至本清单版本，Cocos 工程只有 Boot 几何原型和 TypeScript 脚本，没有正式角色、地图、机关、特效、UI 图片或音频文件。服务端角色种子包含 CHR_001–CHR_012，但头像、模型、动画组和预览资源 ID 仍为空。

因此本清单中的资源均以 `MISSING` 登记。这不是验收通过，也不代表已经生成了占位美术。未取得实际文件、来源和验收记录前，不得把状态改成 `READY`。

## 状态定义

| 状态 | 含义 | 允许进入正式包 |
|---|---|---|
| MISSING | 尚无可验收文件 | 否 |
| IN_PROGRESS | 制作中，尚未通过验收 | 否 |
| READY | 文件已提交，命名/格式/画面/运行验收通过 | 是 |
| BLOCKED | 被规格、授权、技术或依赖问题阻塞 | 否 |

每个条目必须维护 `files`（相对 client/ 的真实文件路径）、`status`、`expected_directory`。只有文件存在且完成对应验收，才允许置为 `READY`。

## 制作计划

详细制作优先级、P0/P1/P2 资源范围、交付格式、分包建议和 READY 验收证据见 [production-plan.md](./production-plan.md)。

资源 manifest 的每个条目都必须包含 priority 与 delivery_phase；客户端契约校验器固定校验批次成员和阶段，防止关键 P0 资产被误降级。当前批次：P0 37、P1 24、P2 51；优先级不改变 required=true，也不解除发布门禁。

## Cocos / 微信小游戏包体基线

- Cocos Creator 3.8 微信小游戏主包平台上限 4 MB、全部分包合计上限 30 MB；项目安全预算分别为 3.2 MB 和 24 MB。
- 使用 Cocos Asset Bundle 将主地图、房间和隐藏结局按需分包；微信本地分包不能配置为远程包。资源 bundle 尽量不包含相互依赖的脚本。
- 微信小游戏纹理压缩格式和 ASTC 真机限制参见 [Cocos Creator 3.8 压缩纹理文档](https://docs.cocos.com/creator/3.8/manual/zh/asset/compress-texture.html) 与 [小游戏分包文档](https://docs.cocos.com/creator/3.8/manual/zh/editor/publish/subpackage.html)。
- 包体限制属于平台基线；项目安全预算属于内部约束。每次构建必须记录真实构建产物大小。

## 资源范围

- 角色：12 个角色，每个至少头像、主体模型/2D角色资源、预览和动画组；动画组必须包含 8 方向 IDLE、8 方向 MOVE、INTERACT、ACT_001–ACT_004。
- 主地图：MAP_MAIN_001 的场景、地面、装饰、碰撞、可行走区域、出生点、入口、摄像机和配置。
- 关卡：5 个常规房间和 1 个隐藏结局的逻辑几何/空间资源。
- 机关：逐一对应 `levels.v1.json` 中的机关 ID，不能只按机关类型交付一个不区分实例的文件。
- 特效：回声、注视、逆流、五个房间结算和隐藏结局反馈。
- UI：登录、角色选择、主地图 HUD、交互、法则、发现、结算、排行榜、图鉴、奖励、个人信息、网络状态。
- 音频：UI/交互、三条法则、发现、结算成功/失败、社交动作、断线/重连及三类 BGM。

## 校验命令

在 `client/` 目录执行：

```bash
npm run validate:assets
npm run validate:release-assets
```

- `validate:assets` 检查清单结构、角色/关卡/机关 ID 一致性、路径安全和 READY 文件存在性；允许缺失资源被登记，供日常开发持续追踪。
- `validate:release-assets` 是发布门禁，要求所有 MVP 必需资源均为 READY 且文件真实存在。当前必然失败，直到资源制作与验收完成。

## 制作与验收流程

1. 美术/音频按 GDD 18 章及各资产目录制作原创资源。
2. 提交文件到 `client/assets/resources/` 对应目录，禁止把未授权素材放入仓库。
3. 更新本清单的 `files`，保持路径相对 `client/`。
4. 技术美术检查格式、命名、图集、压缩、分辨率和设备档位。
5. 客户端验证 Cocos Creator 3.8.8 导入、资源引用、状态切换和缺失降级。
6. 测试按 GDD 18.16 验收并记录证据后，将条目改为 READY。
7. 发布前执行 strict 门禁；任何 MISSING/IN_PROGRESS/BLOCKED 均阻止正式资源包。

纹理格式、模型面数、图集尺寸、音频编码、帧率和内存预算仍由技术美术及实机压测确定，不在此虚构数值。
