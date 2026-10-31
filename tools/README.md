# 资源后处理工具

生成后端不返回 alpha 通道（详见 `docs/engineering/assets/asset-generation-backend-findings.md`），
这里的脚本负责把生成结果转成可用于 Cocos 的真实 RGBA PNG。

依赖：Python 3.12+、`pillow`。

| 脚本 | 适用场景 | 不适用 |
|---|---|---|
| `chroma_key.py` | 生成时要求纯色背景的**独立物件**（角色、机关、特效、UI 元素） | 画面本身含接近键色的色块 |
| `matte_sprite.py` | 只有生成图带棋盘格、且轮廓内部没有背景时 | 轮廓内部存在背景（缝隙、镂空），会残留棋盘格 |

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
