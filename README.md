# 视频字幕识别训练数据集构建管线

用于构建视频字幕识别（OCR）与字幕去除（inpainting）训练数据：从已授权视频来源出发，
经过去重、过滤、原生时间轴保留、场景裁剪和合成字幕渲染，生成严格对齐的训练样本。

当前状态：**初始骨架 + 数据契约（Pydantic）落地中**。详细设计见
[docs/video_subtitle_dataset_pipeline.md](docs/video_subtitle_dataset_pipeline.md)。

## 环境

```bash
python3.12 -m venv .venv          # 或使用 uv / conda，见 requirements.txt
source .venv/bin/activate
python -m pip install -r requirements.txt
```

开发模式安装（启用 `subtitle-dataset` 命令）：

```bash
python -m pip install -e ".[dev]"
```

## 常用命令

```bash
pytest                      # 运行单元测试
ruff check src tests        # lint
ruff format --check src     # 格式检查
mypy                        # 类型检查
subtitle-dataset validate-sample sample.json
subtitle-dataset validate-manifest manifest.json
```

## 目录结构

```text
src/subtitle_dataset/
├── contracts/    # Pydantic 数据契约、确定性哈希、manifest
├── ingest/       # 数据发现、元数据解析与下载（平台适配器）
├── media/        # ffprobe、原生时间轴、解码、场景、裁剪
├── filtering/    # 字幕、文字、质量和安全过滤
├── dedup/        # 文件哈希与视频近重复聚类
├── sampling/     # 文本、样式、位置、时长采样
├── rendering/    # layout、RGBA、composite
├── annotations/  # bbox、polygon、mask
├── export/       # Parquet、WebDataset
├── qa/           # 自动质检与分布报告
└── workflows/    # 可恢复的数据构建流程
```

设计约定速查（详见设计文档）：

- 时间：跨视频统一使用 `duration_ms`/毫秒；`native_frame_index` 仅用于索引和回放。
- 坐标：像素 bbox 使用 `[x0, y0, x1, y1)` 半开区间，同时保存 `[0, 1]` 归一化坐标。
- 配对：`clean_image` 与 `rendered_image` 必须来自同一次解码结果，pilot 阶段使用
  PNG/无损 WebP，禁止分别有损编码。
- 可复现：`sample_id` 与 `config_sha256` 由确定性哈希生成，不含存储路径。
