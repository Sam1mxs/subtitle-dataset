# 配置目录

按设计文档 §14 划分，每个子目录存放 YAML/JSON 配置并纳入版本控制：

- `sources/`：平台来源登记与授权信息
- `builds/`：数据集构建配置（版本、seed、过滤阈值等）
- `styles/`：字幕样式配置（字体、字号、描边、阴影等）
- `distributions/`：文本、时长、位置、宽高比等分布配置
- `splits/`：train/val/test 划分与均衡阈值

所有配置在使用前必须计算 `config_sha256` 并写入样本的 `build` 字段。
