# SRT Whiteboard Animation v2

将 SRT 口播文本制作成可验证、可审阅的白板手绘动画。v2 是一次破坏式重构：不保留旧 Schema 和旧脚本兼容层。

## v2 解决了什么

- 使用维护良好的 `srt` 库解析字幕，以全局动态规划取代贪心切幕。
- 使用 Pydantic 定义 annotation v2，并生成可供编辑器使用的 JSON Schema。
- `elements` 数组是唯一绘制顺序；删除重复的 `sequence`。
- 时间必须单调、不重叠，区域必须在画布内，图片尺寸必须与 annotation 完全一致。
- 删除未生效或仅用于假预览的 `reveal`、`direction`、`handPath`、`maskPaddingPx`、`type`。
- macOS、Linux、Windows 自动发现字体；找不到字体时安全回退。
- 浏览器编辑器只声明自己是布局/时序编辑器；真实效果必须通过低清 MP4 验收。
- 依赖由 `pyproject.toml` + 跨平台 `uv.lock` 管理。
- 统一为一个 `srt-whiteboard` CLI，删除五个相互独立的脚本入口。
- GitHub Actions 在 Linux、macOS、Windows 和 Python 3.11/3.13 上执行 lint 与测试。

## 快速开始

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。系统 FFmpeg 可选；没有时使用锁定的 PyAV 回退。

```bash
uv sync --locked
uv run --locked srt-whiteboard doctor
```

## 完整工作流

### 1. SRT 分镜建议

```bash
uv run --locked srt-whiteboard parse narration.srt -o scene-plan.json
```

`warnings` 会明确列出因字幕边界而无法落在目标时长范围内的场景。

### 2. 创建并验证 annotation v2

```bash
uv run --locked srt-whiteboard schema -o annotation-v2.schema.json
uv run --locked srt-whiteboard validate scene-01.annotation.json --image scene-01.png
uv run --locked srt-whiteboard editor
```

编辑器使用 Chrome/Edge File System Access API 写回用户明确选择的目录；其它浏览器会下载 JSON。

### 3. 静态区域审计

```bash
uv run --locked srt-whiteboard preview \
  scene-01.png scene-01.annotation.json scene-01-regions.jpg
```

### 4. 真实低清效果验收

```bash
uv run --locked srt-whiteboard render \
  scene-01.png scene-01.annotation.json scene-01-proof.mp4 \
  --cap-long-edge 640 --fps 24
```

### 5. 最终渲染与合并

```bash
uv run --locked srt-whiteboard render \
  scene-01.png scene-01.annotation.json scene-01-final.mp4

uv run --locked srt-whiteboard merge \
  --inputs scene-01-final.mp4 scene-02-final.mp4 \
  --output final.mp4
```

合并前会验证尺寸和帧率；不同视频合同不会被静默缩放或重编码成看似成功的结果。

## Annotation v2

```json
{
  "schemaVersion": 2,
  "sceneId": "scene-01",
  "canvas": { "width": 1672, "height": 941 },
  "storyBasis": "本幕只表达一个核心事件。",
  "sceneDurationMs": 8600,
  "holdMs": 500,
  "elements": [
    {
      "id": "setting",
      "label": "场景铺垫",
      "narrativeRole": "建立地点和人物关系",
      "subtitle": "对应的原始字幕文本。",
      "region": { "x": 20, "y": 120, "width": 540, "height": 780 },
      "timing": { "startMs": 300, "durationMs": 2600 },
      "protectedRegions": []
    }
  ]
}
```

完整机器规范位于 [`src/srt_whiteboard/schemas/annotation-v2.schema.json`](src/srt_whiteboard/schemas/annotation-v2.schema.json)。

## 命令

| 命令 | 职责 |
| --- | --- |
| `parse` | 解析 SRT 并优化场景边界 |
| `validate` | 校验 Schema、时序、区域和图片尺寸 |
| `schema` | 输出 annotation v2 JSON Schema |
| `editor` | 打开本地区域/时序编辑器 |
| `preview` | 生成带编号、时间和保护区的静态审计图 |
| `render` | 生成真实连续笔迹 MP4 |
| `merge` | 合并视频合同一致的场景 |
| `doctor` | 检查依赖、编码器、字体和内置资产 |

## 边界

本项目生成无声动画视频。SRT 用于叙事、分镜与时序，不会自动生成配音，也不会把字幕文字烧录进画面。音频与字幕交付应由上层视频制作流程明确处理。

白板笔迹来自栅格线稿的网格或骨架追踪，不是从原图恢复真实创作者的矢量笔顺。因此每个场景必须先做低清真实渲染验收。

## 开发

```bash
uv sync --locked
uv run --locked ruff check src tests
uv run --locked pytest
```

## License

MIT。原项目由 [geeklee/srt-whiteboard-animation](https://github.com/geeklee/srt-whiteboard-animation) 创建；本 fork 的 v2 由 [wispig66](https://github.com/wispig66) 完成破坏式工程化重构。
