# 美术生产流水线与资源状态

- 更新：2026-10-31
- 关联：`queue.v1.json`、`reports/`、`../asset-manifest.v1.json`、`../../../tools/asset_pipeline.py`

## 1. 后端能力盘点（实测）

| 后端 | 调用入口 | 分辨率 | 透明通道 | 参考图 | 角色一致性 | 批量 | 结论 |
|---|---|---|---|---|---|---|---|
| WorkBuddy 内置生图（混元） | `ImageGen` 工具 | 1024×1024、1024×1536、1536×1024 | **否**，`background=transparent` 只画棋盘格 | 支持（`image1..3` + `input_fidelity`） | 图生图可保持，文生图不保持 | 否，逐次调用 | **可用**，需本地抠图 |
| miora 多模态 | `connect_cloud_service` + `miora_*` | — | — | — | — | — | **不可用**：本工作区只接入了 `video-fx` 与 `3d`，没有图像命令 |
| 本地 SD/ComfyUI | — | — | — | — | — | — | 未安装 |

登记规则：只有实际调用成功并产出文件的后端才写入 `queue.v1.json` 的 `backends`。

### 1.1 实测结论

1. **无 alpha**：所有输出为 PNG color type 2。抠图必须走色键，见 `tools/README.md`。
2. **水印**：右下角固定烘焙「AI生成 / WORKBUDDY」。精灵图的水印落在键色背景上，
   色键后变成不透明灰白块，需再清角；背景图的水印压在画面上，只能裁边。
3. **角色一致性**：以 `reference/CHR_001_base.png` 做图生图，主体、头像、机关
   激活态都能保持同一设计；纯文生图会产生漂移（见 `../asset-generation-backend-findings.md` 第 2.3 节）。
4. **键色漂移**：要求 `#FF00FF`，实际落在 `(251, 48, 247)`。所以键色由工具从边框实测，
   不硬编码。

## 2. 队列结构

`queue.v1.json` 的每个任务记录：`id`、`asset_id`、`kind`（sprite / background）、
`prompt`、`reference`、`size`、`quality`、`backend`、`generated_at`、`post`（后处理参数）、
`output`、`report`、`state`、`checks`。

把生成和后处理拆成两步，是因为生成不可脚本化（走工具调用），而后处理必须可复现：
给定同一个 raw 文件，`post` 的输出是确定的。

```bash
python tools/asset_queue.py status          # 队列与 manifest 状态
python tools/asset_queue.py next -n 3       # 打印下一批要生成的提示词与参数
python tools/asset_queue.py post --id <id> --raw <生成结果路径>
python tools/asset_queue.py verify          # 队列、文件、manifest 三方一致性
```

## 3. 后处理链

`sprite`（角色、机关、特效、UI 元素）：

1. **实测键色** — 取边框像素众数，不信任提示词里的 hex。
2. **色键** — `tools/chroma_key.py`，颜色距离生成 alpha，边缘腐蚀 + 羽化。
3. **去溢色** — 色键按 RGB 距离判不出的过渡像素，用色相判定：
   `min(R,B) - G > 45` 视为背景残留。实测机关激活态顶部有 383 个
   `(157,89,145)` 像素，距键色 102，距离法保留它们，形成紫色边缘；色相法清除后剩 7 个。
4. **裁到 alpha 包围盒 + 贴底** — 底部不留内边距，脚底锚点即画布底边，
   引擎按 bottom-center 对齐即可，不需要逐资源偏移。
5. **缩放** — 只缩不放，长边不超过 `max_size`。
6. **清角** — 把右下角区域 alpha 置 0，只删水印，不重建像素。

`background`（地图、场景底板）：先按 `crop_bottom` 裁掉底部水印带，再缩放到目标尺寸。
不透明图不能做 alpha 处理，也不做锚点检查。

## 4. 检查项与判定

| 检查 | 判据 | 失败含义 |
|---|---|---|
| `has_transparency` | 存在 alpha=0 像素 | 不是抠好的精灵 |
| `has_content` | 存在 alpha=255 像素 | 整张图都在半透明，等于空图 |
| `no_key_fringe` | 轮廓带内键色像素 ≤2% | `outer` 太小，留了一圈键色描边 |
| `no_key_bleed` | 色相残留 ≤ max(16, 不透明像素/2000) | 过渡像素残留，暗背景上会显色 |
| `anchor_at_bottom` | 内容底边距画布底 ≤2px | 脚底悬空，深度排序和落地判定会偏 |

报告写入 `reports/<asset>.json`，含 `output_sha256`。`verify` 会重算哈希，
文件在报告之后被改动过就会报错。

## 5. 资源状态

生命周期：`MISSING → PROCESSING → GENERATED → REVIEW → READY`，任一状态可转 `BLOCKED`。
`IN_PROGRESS` 是 `PROCESSING` 的旧名，保留兼容。

| 状态 | 进入条件 |
|---|---|
| MISSING | 无文件 |
| PROCESSING | 已排期或正在生成 |
| GENERATED | 有文件，未跑检查 |
| REVIEW | 文件存在且全部自动检查通过 |
| BLOCKED | 检查失败，或存在明确外部阻塞 |
| READY | 另需 `license_evidence` 与 `acceptance_evidence`，且文件与 Cocos 导入均验收 |

**本流水线只能把资源推进到 REVIEW。** READY 需要授权证据和导入/真机验收，
不是工程侧能自行签发的。当前授权状态见 `../AI-content-compliance.md`。

## 6. 当前进度（2026-10-31）

| 资源 | 状态 | 说明 |
|---|---|---|
| `CHR_001_MODEL` | REVIEW | 298×512 RGBA，脚底贴底，5 项检查通过 |
| `CHR_001_PORTRAIT` | REVIEW | 195×256 RGBA，与主体同一设计稿 |
| `M01-LIGHT-01`（未激活 / 激活） | REVIEW | 200×256 / 186×256 RGBA，两态同形同角度 |
| `FX_ECHO_PULSE_01` | REVIEW | 256×253 RGBA |
| `MAP_MAIN_001_SCENE` | REVIEW | 1024×682，水印带已裁除 |

全量进度：**5 项 REVIEW、1 项 PROCESSING、106 项 MISSING**，P0 共 37 项。
`CHR_001_PREVIEW` 与 `CHR_001_ANIMATION_SET` 仍在队列外，等待主体定稿后再派生。
