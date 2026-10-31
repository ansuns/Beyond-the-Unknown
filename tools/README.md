# 资源后处理工具

生成后端不返回 alpha 通道（详见 `docs/engineering/assets/asset-generation-backend-findings.md`），
这里的脚本负责把生成结果转成可用于 Cocos 的真实 RGBA PNG。

依赖：Python 3.12+、`pillow`。

| 脚本 | 适用场景 | 不适用 |
|---|---|---|
| `chroma_key.py` | 生成时要求纯色背景的**独立物件**（角色、机关、特效、UI 元素） | 画面本身含接近键色的色块 |
| `matte_sprite.py` | 只有生成图带棋盘格、且轮廓内部没有背景时 | 轮廓内部存在背景（缝隙、镂空），会残留棋盘格 |
| `strip_overlay.py` | 去掉右下角固定的「AI生成」角标 | 见下：三种模式质量差异很大 |

## 色键流程（推荐）

1. 生成时要求纯色背景，避免使用“透明背景”，并在提示词里排除地面、投影和光晕：

   > ... on a perfectly flat solid magenta background, color #FF00FF ...
   > No ground, no floor, no shadow, no glow, no text, no watermark.

2. 量出实际背景色（模型不一定严格落在 `#FF00FF`）：

   ```bash
   python -c "from PIL import Image; print(Image.open('raw.png').convert('RGB').getpixel((2,2)))"
   ```

3. 抠图并输出 RGBA：

   ```bash
   python tools/chroma_key.py raw.png out.png --key 162,38,98 --inner 30 --outer 72
   ```

4. 在深色背景上复查边缘，确认没有键色残留和白色描边。

## 已知限制

- 生成结果右下角带有烘焙的合规水印，上述脚本不会也无法合规地去除它。
- 单独调用之间角色形象会漂移，成组的角色资源必须走图生图。
- 脚本只处理像素与通道，不做尺寸定档、图集拆分和 Cocos 导入；这些仍属待决事项。

## 去掉右下角水印

生成后端会把「AI生成 / WORKBUDDY」印在右下角固定位置。最优解是生成时就不带水印
（混元接口的 `LogoAdd=0`），但当前生图工具没有暴露这个开关，所以用本地兜底。

先量出水印区域，确认美术没有占进去：

```bash
python - <<'EOF'
from PIL import Image
im = Image.open('raw.png'); w, h = im.size
im.crop((int(0.72*w), int(0.86*h), w, h)).resize((600, 300)).save('corner.png')
EOF
```

| 模式 | 适用 | 结果 |
|---|---|---|
| `alpha` | RGBA 精灵：水印落在美术轮廓之外 | **生产可用**。把该区域 alpha 置 0，不生成任何像素 |
| `crop` | 不透明背景 | **生产可用**。裁掉承载水印的底边，零伪影，画布变矮约 7% |
| `inpaint` | 画布尺寸绝对不能变时 | **仅占位**。大字号笔画 + 结构化背景会糊成一片，不要当正式美术 |

```bash
# 精灵（先色键再清角标）
python tools/chroma_key.py raw.png keyed.png --key 162,38,98
python tools/strip_overlay.py keyed.png final.png --mode alpha

# 背景
python tools/strip_overlay.py raw.png final.png --mode crop
```

每种模式的防误伤检查不同，因为它们失败的方式不同：

| 模式 | 检查 | 拒绝条件 |
|---|---|---|
| `alpha` | 角落区域的不透明占比 | 超过 35%（说明该处是美术，不只是水印） |
| `crop` | 裁切深度是否够深 | 浅于 7%（盖不住水印）或深于 25%（切掉太多） |
| `inpaint` | 输入可用性 | 边长小于 16px 或区域为空 |

确认过再 `--force`。注意：**不透明占比不能用来判断 `crop` 是否安全**——普通 RGB 图没有
alpha，按占比算永远是 100%。这正是本工具第一版的缺陷，已修复并由 `tools/tests` 的 23 项测试覆盖。

## 测试

```bash
python -m pytest tools/tests -q
```

需要 `pillow numpy pytest`，`inpaint` 相关用例还需要 `opencv-python-headless`。
CI 由 `.github/workflows/art-tools-ci.yml` 在 `tools/**` 变更时执行。

## 水印与合规

去掉角标**不等于**可以把它当真人手绘。生成的资源仍必须在
`asset-manifest.v1.json` 的 `provenance` 里登记 `source_type=GENERATED_WITH_REVIEW`，
并保留生成记录。对 AI 生成内容的标识义务通过仓库内的来源记录满足，而不是靠画面角标。
