# 视频字幕识别训练数据集构建管线设计

> 状态：初始设计稿  
> 最后更新：2026-07-31  
> 用途：作为后续数据管线实现、代码评审、数据验收和版本迭代的共同基准。

## 1. 背景与目标

本项目用于构建视频字幕识别和字幕去除训练数据。计划从多个已授权视频来源采集原始视频，经过去重、质量过滤、字幕过滤、原始时间轴保留、场景裁剪和合成字幕渲染，最终生成严格对齐的训练样本。

核心任务包括：

1. OCR 微调：使用加字幕图像、字幕文本和字幕位置标注。
2. Inpainting 微调：使用加字幕图像、无字幕底图和字幕区域 mask。

当前目标场景以短剧字幕为主，已知约束如下：

- 不对所有视频做固定帧率重采样；保留视频原生帧率、PTS 和 time base。
- 字幕事件的主约束使用真实时间长度，而不是跨视频通用的帧数。原先基于 30fps 的 4～120 帧范围，若要保持其物理时长含义，初始可转换为约 133～4000 ms，最终应以测试集的时间戳统计为准。
- `native_frame_index` 只表示某个视频中的原生帧索引，不再作为跨视频比较时长的统一单位。
- 字幕可见区域中心的纵坐标位于最终图像高度的 60%～90%。
- 字体、位置、字号、字距、行距、描边、阴影等字幕属性需要覆盖充分。
- 视频来源、作者、内容场景、分辨率和宽高比需要避免严重偏斜。

## 2. 关键定义与设计决策

### 2.1 “过滤含有字幕的视频”的含义

本设计将其定义为：**从严格配对数据中排除带有原生硬字幕的视频或帧**。

如果视频本身已经带有硬字幕，就无法直接获得严格对齐的无字幕底图。因此数据应拆成两条独立的数据线：

| 数据线 | 输入 | 主要用途 | 是否要求无字幕底图 |
|---|---|---|---|
| 合成配对数据集 | 无原生字幕、无干扰文字的视频 | OCR 主训练、inpainting 主训练 | 是 |
| 真实字幕数据集 | 带原生字幕的视频 | 域适配、人工评测、真实验证集 | 否 |

两类数据不得使用同一套监督假设。真实字幕数据不能在缺少可靠干净底图时充当配对 inpainting 数据。

### 2.2 `original_image` 的准确含义

样本中的“原始图像”统一命名为 `clean_image`。它不是未经处理的原视频帧，而是已经完成下列操作、但尚未添加字幕的最终底图：

- 原生时间轴下的帧选择和时间戳记录；
- 场景切分；
- 裁剪和缩放；
- 颜色空间处理；
- 允许的图像增强或压缩预处理。

`rendered_image` 必须直接在这个 `clean_image` 的同一解码结果上合成字幕，以保证两张图严格对齐。

### 2.3 Inpainting 使用 mask 而不是只有 bbox

最终样本除了用户要求的四项数据，还必须增加：

- `alpha_mask`：字幕填充、描边、阴影等可见像素的透明度图。
- `inpaint_mask`：基于 alpha mask 生成的二值 mask，可以按配置适当膨胀。

仅使用矩形 bbox 会删除大量不需要修复的背景，且不易完整覆盖阴影和描边。

## 3. 总体数据流

```text
授权来源登记
  -> 视频发现与下载
  -> 解码检查与元数据探测
  -> 精确去重与近重复聚类
  -> 原生字幕、场景文字、水印及质量过滤
  -> 按原视频/作者/近重复簇划分 train、val、test
  -> 读取原生 PTS/time base 并建立可追溯的时间映射
  -> 场景切分和多宽高比裁剪
  -> 字幕文本、样式、位置、时长采样
  -> 渲染独立 RGBA 字幕层
  -> 合成图像并生成 bbox、polygon、alpha mask、inpaint mask
  -> 自动质检和分层人工抽检
  -> Parquet manifest 和 WebDataset shard 导出
```

必须在所有裁剪、字幕渲染和数据增强之前完成数据集划分，避免同一原始内容的不同变体跨越 train/val/test。

## 4. 数据来源与合规要求

公开视频不自动等于允许下载、生成衍生数据、用于机器学习训练或重新分发。每个来源必须建立来源登记，并保存至少以下字段：

```text
source_id
platform
source_url_or_hash
creator_id_or_hash
license_status
allowed_to_download
allowed_for_derivative_work
allowed_for_ml_training
allowed_to_redistribute
authorization_reference
authorization_start_at
authorization_expire_at
crawled_at
```

实现约束：

- 优先使用平台开放接口、已授权账号、版权合作方或自有视频。
- 遵守服务条款、robots 规则、访问频率限制和个人信息保护要求。
- 不实现绕过登录、验证码、签名、DRM 或其他访问控制的能力。
- 下载任务必须支持来源级限速、退避、暂停和删除请求。
- 原始 URL、Cookie、账号信息等敏感数据不得进入训练 manifest。
- 对人脸、用户名、联系方式、未成年人和其他隐私内容制定保留及删除策略。

## 5. 爬取与下载架构

### 5.1 平台适配器

不同平台使用独立适配器，不把网站细节写入公共管线：

```python
class SourceAdapter:
    def discover(self, request): ...
    def resolve_metadata(self, item): ...
    def download(self, item, destination): ...
    def normalize_metadata(self, raw_metadata): ...
```

发现、元数据解析和媒体下载是三个独立步骤。某个平台实现失效时，不应影响后续视频处理和数据生成模块。

### 5.2 推荐技术栈

| 场景 | 推荐工具 | 说明 |
|---|---|---|
| 静态页面、公开接口、任务调度 | Scrapy + httpx | 支持并发、重试、限速和请求中间件 |
| 必须执行 JavaScript 的页面 | Playwright | 只用于确实依赖浏览器的发现或解析步骤 |
| 媒体解析和下载 | yt-dlp 适配器 | 固定版本并做小样本 canary 测试，不作为核心数据模型 |
| 视频元数据探测 | ffprobe | 获取编码、时长、原生帧率、VFR/CFR 状态、时间基和色彩信息 |
| 转码、裁剪和抽帧 | FFmpeg | 作为主要音视频处理工具；不强制使用 fps 重采样 |
| Python 帧级解码 | PyAV | 在原生时间轴上解码，并保留 PTS、time base 等时间信息 |

Playwright 不用于承担大规模媒体流下载。`yt-dlp` 的平台支持可能随网站变化，必须放在可替换适配器后面，并记录工具版本和下载结果。

### 5.3 下载任务的幂等性

下载任务必须满足：

- 相同来源 ID 重复执行不会重复创建原始对象。
- 下载中断可恢复。
- 下载完成后计算 SHA-256。
- 保存原始元数据快照和失败原因。
- 对 HTTP、平台限制、解码失败等错误分别统计。
- 未通过授权检查的数据不能进入下载队列。

## 6. 视频元数据与原生时间轴

### 6.1 不做全局 30fps 重采样

管线默认不生成 CFR 30fps 派生视频。保留来源视频的原生帧率；对于 VFR 视频，保留每一帧的 PTS，而不是把帧强行映射到等间隔时间网格。

处理时必须：

- 使用 `ffprobe` 记录 `avg_frame_rate`、`r_frame_rate`、`time_base`、时长、VFR/CFR 状态和色彩信息。
- 使用 PyAV 或 FFmpeg 在原生时间轴上解码，并保存每个选中帧的 `native_frame_index`、`pts` 和 `timestamp_ms`。
- 保证选中帧的 PTS 单调递增；对缺失 PTS、解码异常和时间戳回退进行拒绝或单独标记。
- 记录 FFmpeg/PyAV 版本、完整处理配置和输入文件哈希。
- 固定颜色空间、色彩范围和像素格式策略，避免不同批次颜色漂移。
- 如果某个下游模型明确要求固定帧率，单独建立该模型的导出步骤，不改变本数据集的原始时间轴。

### 6.2 字幕事件时间定义

字幕事件在主 manifest 中使用时间长度作为跨视频统一单位：

```text
start_time_ms = event_start_pts * time_base
end_time_ms = event_end_pts * time_base
duration_ms = end_time_ms - start_time_ms
```

事件仍可以保存原生帧边界，但帧数只用于索引和回放：

```text
native_duration_frames = end_native_frame_exclusive - start_native_frame
```

不应使用同一个 `4～120 帧`范围约束所有来源，因为 24fps、30fps、60fps 和 VFR 视频中相同帧数对应的真实时长不同。若需要兼容既有测试集统计，先将测试集中的帧数按每个事件的实际 FPS/PTS 转换为毫秒，再拟合 `duration_ms` 分布。没有更准确统计时，可暂以 133～4000 ms 作为原 30fps 约束的物理时长近似。

### 6.3 相对固定 30fps 方案的代码变化

相比固定 30fps 的旧方案，后续实现应遵循以下变化：

- 不创建或不依赖 `cfr30.py`、`normalize_fps.py` 一类的全局帧率标准化模块。
- 增加独立的 `media/timeline.py`，统一处理 PTS、time base、原生帧索引和毫秒换算。
- 增加或明确 `sampling/duration_sampler.py`，以 `duration_ms`/秒为主采样单位。
- `contracts` 中的 `frame_index_30fps` 改为 `native_frame_index`。
- `start_frame`、`end_frame_exclusive` 改为 `start_native_frame`、`end_native_frame_exclusive`，并同时保存起止 PTS 和毫秒时间。
- 删除 `derived/cfr30/` 数据目录，改为保存 probe 元数据、原生时间轴 clip 或按需抽取的帧。
- 视频模型如确实需要固定帧率，应在独立 export adapter 中完成，不得修改主数据集的时间语义。
- 所有涉及字幕时长、时序采样和质量验收的配置都应命名为 `duration_ms`、`start_pts`、`end_pts` 等，不要使用未说明时间基的裸 `frame_count`。

### 6.4 重新编码原则

- 尽量只做一次有损编码。
- `clean_image` 和 `rendered_image` 的共同背景必须来自同一次解码结果。
- 用于严格 inpainting 配对的数据不能把 clean/rendered 分别编码成 JPEG。
- Pilot 阶段优先使用 PNG 或无损 WebP；规模扩大后再评估存储成本。
- 如果需要字幕经过视频编码后的真实退化效果，作为 OCR 专用变体单独输出，不破坏严格 inpainting 配对。

## 7. 原生字幕与已有文字过滤

字幕、场景文字、台标和水印必须分别识别。建议使用两阶段过滤：

1. 视频级粗筛：对视频抽帧，检测下半区域中持续出现的文字框。
2. 样本级精筛：对最终选中的每一帧执行完整文字检测。

原生字幕判定可以综合以下特征：

- 文字框中心位置和宽高；
- 多个相邻帧中的位置稳定性；
- OCR 文本是否以句子形式发生切换；
- 是否具有统一基线和字幕式对齐；
- 是否位于画面下方；
- 是否长期完全不变，长期不变更可能是台标或水印。

不同训练任务应采用不同过滤规则：

- 全图 OCR 检测与识别：必须过滤所有未标注文字，或者补齐其标注。
- 仅对字幕 bbox 裁剪图做文字识别：可以保留框外场景文字。
- Inpainting：字幕目标区域内不能存在原生文字；其他位置的文字应有独立标记。

## 8. 去重、划分和来源均衡

### 8.1 去重层次

至少执行：

1. 文件 SHA-256 精确去重。
2. 关键帧感知哈希或视觉 embedding 近重复去重。
3. 可选音频指纹，用于识别跨平台转载和不同裁剪版本。

跨平台转载、加边框版本、不同码率版本和二次裁剪版本应尽可能归入同一个内容簇。

### 8.2 数据集划分

划分单位从小到大包括：

- 原视频；
- 作者或内容账号；
- 剧集或系列；
- 近重复内容簇。

默认至少以近重复内容簇为最小不可拆分单位。任何来自同一簇的裁剪、帧和字幕样式变体必须位于同一个 split。

### 8.3 均衡标准

均衡应在最终输出的字幕事件或样本层统计，而不是只统计下载视频数量。建议限制：

- 单个平台最大占比；
- 单作者最大占比；
- 单原视频最大事件数；
- 单近重复簇最大事件数；
- 各场景、宽高比、分辨率的最低覆盖量。

来源维度至少包括：平台、作者、内容簇和场景。场景标签可以包括室内、室外、对白、多人、单人、动画、游戏、新闻、体育、烹饪、城市、自然等，并根据实际目标集调整。

## 9. 场景切分与裁剪

处理顺序必须为：**场景切分和裁剪在前，字幕渲染在后**。

推荐宽高比桶可包括：

- 9:16
- 16:9
- 1:1
- 4:3

具体比例和权重应根据目标测试集重新统计。不要给每个原视频机械生成所有尺寸，否则会造成样本数量膨胀和高度相关。

裁剪策略：

- 使用人物框、显著性或目标跟踪辅助保留主要主体。
- 保留一定比例的普通随机裁剪，避免数据构图过于规则。
- 不做破坏原始几何比例的拉伸。
- 保存原图坐标中的 `crop_xywh`、缩放比例和输出尺寸。
- 裁剪变换必须参与 `sample_id` 和配置版本计算。

## 10. 字幕文本与样式采样

### 10.1 分布原则

所有参数完全均匀会产生大量不真实组合。推荐采用两层混合分布：

- 70%～80%：按照真实短剧测试集统计分布采样。
- 20%～30%：用于困难样本和长尾覆盖。

上述比例是初始建议，最终以真实评测结果调整。

### 10.2 需要控制的字幕维度

| 类别 | 参数示例 |
|---|---|
| 文本 | 字数、中文/数字/英文/标点、单双行、长尾字符 |
| 字体 | 黑体、宋体、圆体、手写体、字体粗细 |
| 几何 | 字号、字距、行距、对齐、左右位置 |
| 效果 | 填充色、描边、阴影、背景条、透明度 |
| 时间 | `duration_ms` 分布、淡入淡出状态、事件起止 PTS |
| 图像 | 分辨率、宽高比、亮度、模糊、压缩程度 |
| 来源 | 平台、作者、场景和内容簇 |

不要生成不合理的笛卡尔积组合。样式采样器需要支持条件分布，例如某些字体类别对应特定字号范围，双行字幕对应更严格的安全边距。

### 10.3 位置定义

字号、描边宽度、阴影偏移和位置优先使用相对于最终图像高度的比例。

字幕纵向位置按最终可见效果区域计算：

```text
visible_bbox_center_y = (effect_bbox_y0 + effect_bbox_y1) / 2
0.60 <= visible_bbox_center_y / image_height <= 0.90
```

这里的 bbox 必须包含填充、描边和阴影。不得使用字体 anchor、基线或未渲染前的逻辑布局框代替最终可见框。

采样流程应为：

1. 生成文本和样式。
2. 渲染透明字幕层。
3. 根据 alpha 计算真实可见尺寸。
4. 采样字幕中心位置。
5. 校验边界和纵向范围。
6. 不满足约束时拒绝并重新采样。

### 10.4 时长分布

不要直接在原生帧数 4～120 的每个整数上等概率采样。主采样单位应为 `duration_ms` 或秒，优先使用真实测试集的 PTS 直方图。原先 30fps 配置的分桶只能作为兼容参考，不能直接用于 24fps、60fps 或 VFR 视频。

在缺少更细测试集统计时，可以先使用以下物理时长分桶，再根据真实数据调整：

```text
约 0.13～0.27 秒
约 0.30～0.50 秒
约 0.53～1.00 秒
约 1.03～2.00 秒
约 2.03～3.00 秒
约 3.03～4.00 秒
```

对于图像训练，如果一个事件导出所有原生帧，长事件会严重主导样本数量。默认应为每个字幕事件固定或有上限地抽取若干代表帧。视频模型数据可以保留完整事件序列，并使用原生 PTS 驱动时序采样；不要假设相邻帧的时间间隔恒定。

### 10.5 字体与文本要求

- 字体文件必须有明确的训练和再分发许可。
- 保存字体文件 SHA-256 和许可证信息。
- 合成前检查所有字符的 glyph coverage。
- 发现缺字或 tofu 方框时丢弃或进行有记录的字体 fallback。
- 同时保存 `text_raw` 和 `text_normalized`，不得只保存不可逆的规范化文本。
- 规范化规则必须版本化，包括全半角、空白、Unicode 和标点处理。

## 11. 字幕渲染与标注生成

### 11.1 推荐渲染方案

建议提供两个可替换渲染后端：

- libass/ASS：生成接近常见视频字幕的视觉效果。
- Pango/Cairo、Skia 或支持复杂文字 shaping 的 Pillow 后端：用于精确控制字距、行距和 mask。

FFmpeg `drawtext` 可以用于简单实验，但不作为唯一核心渲染器，因为复杂换行、字体 fallback、精确 mask 和配置复现较难管理。

### 11.2 独立字幕层

字幕必须先渲染为透明 RGBA 图层，再与 clean image 合成。由 RGBA 图层生成：

- `layout_bbox`：排版逻辑区域；
- `ink_bbox`：字符填充区域；
- `effect_bbox`：包含描边和阴影的可见区域；
- `polygon`：有旋转或透视时使用；
- `alpha_mask`：像素级透明度；
- `inpaint_mask`：用于修复的二值或软 mask。

OCR 默认使用 `effect_bbox` 或逐行 bbox，inpainting 默认使用膨胀后的 `inpaint_mask`。

### 11.3 坐标约定

- 像素 bbox 使用 `[x0, y0, x1, y1)` 半开区间。
- 同时保存像素坐标和 `[0, 1]` 归一化坐标。
- 多行字幕保存整体 bbox 和逐行 bbox。
- 旋转字幕保存 polygon，不能只保存轴对齐 bbox。
- 所有坐标基于最终输出图像，而不是原视频坐标。

## 12. 样本数据契约

建议的最小样本结构如下：

```json
{
  "sample_id": "sha256...",
  "source": {
    "platform": "bilibili",
    "video_sha256": "...",
    "creator_hash": "...",
    "content_cluster_id": "...",
    "native_frame_index": 381,
    "pts": 38148,
    "timestamp_ms": 12716,
    "time_base": {
      "num": 1,
      "den": 3000
    },
    "frame_rate": {
      "avg_num": 30000,
      "avg_den": 1001,
      "r_num": 30000,
      "r_den": 1001,
      "is_vfr": false
    }
  },
  "image": {
    "width": 1080,
    "height": 1920,
    "clean_uri": "...",
    "rendered_uri": "..."
  },
  "subtitle": {
    "event_id": "...",
    "text_raw": "今天晚上一起吃饭",
    "text_normalized": "今天晚上一起吃饭",
    "start_native_frame": 360,
    "end_native_frame_exclusive": 405,
    "start_pts": 36000,
    "end_pts_exclusive": 40500,
    "start_time_ms": 12000,
    "end_time_ms": 13500,
    "duration_ms": 1500,
    "native_duration_frames": 45,
    "bbox_xyxy": [181, 1370, 902, 1456],
    "bbox_normalized": [0.168, 0.714, 0.835, 0.758],
    "line_bboxes_xyxy": [],
    "polygon": [],
    "alpha_mask_uri": "...",
    "inpaint_mask_uri": "...",
    "style": {
      "font_sha256": "...",
      "font_size_h_ratio": 0.041,
      "letter_spacing": 1.2,
      "line_spacing": 4.0,
      "stroke_width_h_ratio": 0.002,
      "opacity": 1.0,
      "style_seed": 123456
    }
  },
  "transform": {
    "crop_xywh": [0, 0, 1080, 1920],
    "target_size": [1080, 1920]
  },
  "build": {
    "dataset_version": "v1",
    "config_sha256": "...",
    "renderer_version": "...",
    "ffmpeg_version": "...",
    "seed": 123456
  },
  "split": "train"
}
```

`sample_id` 应由不会随存储位置变化的字段确定性生成，例如：

```text
hash(dataset_version, video_sha256, native_frame_index, frame_pts, crop_config, event_id, style_seed)
```

## 13. 存储和导出格式

代码仓库不存放原始视频和大规模派生数据。推荐对象存储布局：

```text
raw/videos/{platform}/{sha256}
derived/probe/{sha256}.json
derived/clips/{video_sha256}/{clip_id}
derived/frames/{video_sha256}/{native_frame_index}
manifests/{dataset_version}/videos.parquet
manifests/{dataset_version}/clips.parquet
manifests/{dataset_version}/events.parquet
manifests/{dataset_version}/samples.parquet
manifests/{dataset_version}/failures.parquet
shards/{dataset_version}/{split}/*.tar
reports/{dataset_version}/
```

推荐方案：

- 原始视频和大对象：S3/MinIO。
- 元数据和构建清单：Parquet。
- 临时查询和分布分析：DuckDB。
- 任务状态、授权信息：PostgreSQL。
- 训练数据：WebDataset shards，避免海量小文件。

一个 shard 中的样本可包含：

```text
{sample_id}.clean.png
{sample_id}.rendered.png
{sample_id}.alpha.png
{sample_id}.mask.png
{sample_id}.json
```

## 14. 推荐项目结构

```text
video-subtitle-dataset/
├── pyproject.toml
├── configs/
│   ├── sources/
│   ├── builds/
│   ├── styles/
│   ├── distributions/
│   └── splits/
├── src/subtitle_dataset/
│   ├── contracts/          # Pydantic/schema/manifest 定义
│   ├── ingest/
│   │   └── adapters/       # bilibili、douyin 等平台适配器
│   ├── media/
│   │   ├── probe.py        # 帧率、VFR/CFR、time base、色彩信息
│   │   ├── timeline.py     # PTS、时间换算和原生帧索引
│   │   ├── decode.py       # 原生时间轴解码与抽帧
│   │   ├── scene.py        # 场景切分
│   │   └── crop.py         # 裁剪与坐标变换
│   ├── filtering/          # 字幕、文字、质量和安全过滤
│   ├── dedup/              # 文件哈希和视频近重复聚类
│   ├── sampling/           # 文本、样式、位置、时长采样
│   ├── rendering/          # layout、RGBA、composite
│   ├── annotations/        # bbox、polygon、mask
│   ├── export/             # Parquet、WebDataset
│   ├── qa/                 # 自动质检与分布报告
│   ├── workflows/          # 可恢复的数据构建流程
│   └── cli.py
├── schemas/
├── assets/
│   └── fonts/
│       └── LICENSES/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── golden/             # 固定字体、配置和渲染输出
├── docs/
│   ├── data_card.md
│   └── source_registry.md
└── deploy/
```

## 15. 工作流与可复现性

MVP 阶段建议使用 Python CLI 加显式 manifest，不急于引入复杂分布式系统。规模扩大后再接入 Dagster 或 Prefect。

每个处理阶段必须：

- 输入和输出由 manifest 明确描述。
- 支持幂等重跑和失败恢复。
- 记录配置哈希、代码版本、依赖版本和随机种子。
- 使用确定性 seed；同一输入、配置和版本应生成同一字幕样本。
- 失败样本写入失败 manifest，不能静默丢弃。
- 支持按来源、日期、版本或内容簇回滚和重新构建。

## 16. 自动质量验收

每次构建至少检查以下规则：

### 16.1 视频和时间

- 原始帧率、VFR/CFR 状态和 time base 可解析并已写入 manifest。
- 选中帧的 PTS 单调递增，原始时间戳到 `native_frame_index` 的映射可追溯。
- 字幕事件使用 `duration_ms` 校验时间分布；在缺少新统计时，默认检查约 133～4000 ms 的兼容范围；不得把原生帧数当作跨视频统一时长单位。
- `end_native_frame_exclusive > start_native_frame`。
- `end_pts_exclusive > start_pts`，并且 PTS 换算出的时长与 `duration_ms` 一致。

### 16.2 渲染和标注

- `effect_bbox` 完整包含所有可见 alpha 像素。
- 字幕未被图像边界裁掉。
- 字幕可见 bbox 中心高度位于 60%～90%。
- `inpaint_mask` 覆盖填充、描边和阴影。
- bbox、polygon 和 mask 坐标一致。
- 所有字符存在对应 glyph，没有 tofu 方框。

### 16.3 严格配对

- `clean_image` 与 `rendered_image` 尺寸完全一致。
- mask 外像素逐像素相同；默认要求最大绝对差为 0。
- rendered 与 clean 的差异区域必须被 mask 包含。
- 不允许分别进行有损编码导致全图背景变化。

### 16.4 数据划分和分布

- 原视频、作者、系列和近重复簇不跨 split。
- 检测跨平台转载造成的数据泄漏。
- 单平台、作者、视频和内容簇没有超过配置上限。
- 字体、字号、位置、时长、场景、宽高比均达到覆盖目标。
- 输出分布报告并与目标分布比较。

### 16.5 人工抽检

自动检查通过后，按平台、场景、字幕样式、时长桶和困难程度分层抽样，检查：

- 字幕是否自然；
- bbox 和 mask 是否准确；
- 文本和图像是否一致；
- 是否残留原生字幕或水印；
- 是否存在明显版权、隐私或安全问题；
- 困难样本是否仍具有可辨识性。

## 17. 推荐实施顺序

### 阶段一：冻结数据契约

1. 实现 Pydantic/JSON Schema。
2. 明确坐标和时间区间约定。
3. 建立字体许可证和来源授权登记格式。

### 阶段二：实现严格配对渲染器

1. 输入一张 clean image 和字幕配置。
2. 输出 rendered image、alpha mask、inpaint mask 和 bbox。
3. 建立固定字体和固定 seed 的 golden tests。
4. 验证 mask 外像素完全一致。

### 阶段三：小规模视频处理 Pilot

1. 使用少量已授权视频。
2. 实现 ffprobe、原生时间轴解码、场景切分和裁剪。
3. 实现原生字幕检测和样本级文字精筛。
4. 生成第一版分布报告。

### 阶段四：端到端基线

1. 导出一个小型 WebDataset。
2. 分别训练 OCR 和 inpainting 基线。
3. 在真实短剧测试集上分析 synthetic-to-real gap。
4. 根据错误类型调整字体、压缩、位置和文本分布。

### 阶段五：扩大来源和并行度

在数据契约、渲染质量和基线结果稳定后，再扩大爬取规模、引入工作流系统和分布式处理。

## 18. 当前待确认事项

以下事项在正式编码前仍需结合业务目标确认：

1. OCR 是全图检测识别、字幕检测识别，还是 bbox 裁剪后的纯识别任务。
2. Inpainting 是单帧模型还是时序视频模型。
3. 目标分辨率和各宽高比的真实权重。
4. 短剧测试集的字体、字号、文本长度、时长和位置直方图。
5. 可合法用于训练及再分发的视频来源和字体清单。
6. 是否需要生成旋转、透视、滚动字幕或卡拉 OK 字幕。
7. 是否允许保留台标、人物姓名条和其他非字幕文字。
8. 最终数据是否需要对外分发；这会显著影响授权和存储策略。

## 19. 参考资料

- [FFmpeg Filters Documentation](https://ffmpeg.org/ffmpeg-filters.html)
- [PyAV Video API](https://pyav.org/docs/stable/api/video.html)
- [Scrapy Architecture](https://docs.scrapy.org/en/latest/topics/architecture.html)
- [Playwright Network Documentation](https://playwright.dev/python/docs/network)
- [yt-dlp Project README](https://github.com/yt-dlp/yt-dlp#readme)
