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
subtitle-dataset render --clean clean.png --config configs/styles/default.json --outdir out/
subtitle-dataset generate --clean clean.png --config configs/sampling/default.json --outdir out/ --n 20
subtitle-dataset probe video.mp4
subtitle-dataset extract-frames --video video.mp4 --config configs/ingest/default.json --outdir frames/
subtitle-dataset detect-subtitles --video video.mp4 --config configs/filtering/default.json
subtitle-dataset source-registry validate
subtitle-dataset source-registry check --source-id bilibili-demo
subtitle-dataset collect --source-id test-src --source-id test-src-2 --adapter local-http --base-url http://127.0.0.1:8000 --outdir raw/ --registry configs/sources/registry.json --concurrency 2
subtitle-dataset collect-delete --source-id test-src --item-id v001 --outdir raw/
subtitle-dataset dedup --manifests frames/video-a/manifest.json --manifests frames/video-b/manifest.json --outdir dedup/
subtitle-dataset split --clusters dedup/clusters.json --config configs/splits/default.json --outdir splits/
subtitle-dataset export-parquet --samples out/manifest.json --frames frames/manifest.json --outdir parquet/
```

`render` 输出 `rendered.png`（合成字幕图）、`alpha.png`（alpha mask）、
`mask.png`（inpaint mask，带膨胀）和 `metadata.json`（effect/line bbox、
配置哈希），并保证 clean 与 rendered 在 mask 外逐像素一致（见 `qa` 模块）。

`generate` 是采样闭环：按时长分桶、文本语料（`assets/texts/sample_corpus.txt`）、
样式分布和位置分布采样，渲染后校验边界与严格配对，失败自动重试；每个样本
使用独立种子（`seed + index * 7919`），输出到 `out/samples/{index}/` 并在
`out/manifest.json` 汇总。样本级文字过滤（§7 精筛）默认开启：clean 帧的字幕
目标区域内检出原生字幕文字时拒绝并重试；`--split-map` 可把划分结果写入
每个样本的 `split` 字段。文本规范化按 `(language, version)` 规则集执行
（`normalization` 模块，默认 zh/1.0：全角 ASCII、全角空格、空白、换行、去空白），
样本同时保留 `text`（raw）与 `text_normalized`，并记录 `language`/`script`/
`normalization_version`；渲染器支持 `language`/`direction` 透传（raqm 塑形，
为阿拉伯文等复杂脚本预留）。

`extract-frames` 是阶段三 pilot：ffprobe 探测原生帧率/time_base/色彩 → showinfo
建立帧索引↔PTS↔毫秒时间轴 → scene 滤镜切分场景 → 每场景抽代表帧 → 保持几何比例的
裁剪（center/random/mixed，默认 20% 随机裁剪增加构图多样性，记录 crop_mode），
输出帧文件与 `manifest.json`（含每个帧的原生 PTS、裁剪信息、图像哈希）。
抽出的帧目录可以直接作为 `generate --clean` 的输入，把真实帧接进采样闭环。

`source-registry` 管理来源登记表（§4）：`validate` 校验字段一致性，
`check` 检查来源在当前日期是否通过授权；`generate --source-id` 在生成前
强制执行授权门禁，未通过直接拒绝。

`collect` 是采集框架（§5）：下载前检查来源授权，支持 HTTP Range 断点续传
（`.part` 续传 + 原子替换）、来源级与全局并发限速、指数退避重试、幂等
（`collected.json` 状态，重复执行不重复下载）；`--source-id` 可重复指定
多来源，`--concurrency` 控制并发数。`collect-delete` 删除条目及其状态。
当前内置 `local-http` 适配器（本地目录 + manifest.json），真实平台适配器
待授权来源接入后补充。

`dedup` 做 SHA-256 精确去重（视频级 + 帧级，输出内容簇）；`split` 在**内容簇**
层面划分 train/val/test（簇不可拆分），按比例贪心分配、种子可复现，并尽量满足
平台/作者/视频分组上限（不满足时记录警告）。感知哈希近重复聚类接口已提供
（`dedup.hashing.DifferenceHash` + `build_near_clusters`），待真实视频池接入；
`split` 同时输出 `item_splits.json`（条目 → split），供 `generate --split-map` 使用。

`export-parquet` 把样本/帧/场景/失败清单导出为 Parquet（显式 schema、字段拍平，
可直接用 DuckDB/Spark 查询分析），图像字节仍由 WebDataset 导出另行处理。

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

## 字体

- 登记表：[assets/fonts/registry.json](assets/fonts/registry.json)，记录字体文件的
  SHA-256 与许可证（是否允许再分发、是否允许用于 ML 训练）。
- 未登记字体禁止进入渲染管线；渲染前会做 glyph 覆盖检查，主字体缺字时按
  `font_ids` 顺序 fallback，并在输出中记录实际使用的字体与缺字清单。
- 许可证明细见 [assets/fonts/LICENSES/](assets/fonts/LICENSES/)。
