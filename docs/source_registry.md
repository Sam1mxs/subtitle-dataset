# 来源登记表（设计文档 §4）

登记表文件：`configs/sources/registry.json`。任何视频进入下载或训练管线前，
必须先在登记表中注册并通过授权检查；未通过检查的数据不得进入下载队列。

## 字段说明

| 字段 | 含义 |
|---|---|
| `source_id` | 来源唯一 ID（小写字母/数字/`-`/`_`） |
| `platform` | 平台名（如 bilibili、douyin），会写入样本 `source.platform` |
| `source_url_or_hash` | 来源 URL 或内容哈希 |
| `creator_id_or_hash` | 作者 ID 或哈希，会写入样本 `source.creator_hash` |
| `license_status` | `authorized` / `pending` / `unknown` / `rejected` |
| `allowed_to_download` | 是否允许下载 |
| `allowed_for_derivative_work` | 是否允许生成衍生数据 |
| `allowed_for_ml_training` | 是否允许用于 ML 训练 |
| `allowed_to_redistribute` | 是否允许再分发 |
| `authorization_reference` | 授权依据（合同编号、许可页链接等） |
| `authorization_start_at` / `authorization_expire_at` | 授权时间窗（可空=无窗口约束） |
| `crawled_at` | 登记/抓取时间 |

## 硬性校验（`source-registry validate`）

- `source_id` 不得重复；
- `allowed_for_ml_training=True` 时 `license_status` 必须是 `authorized`；
- 授权到期日不得早于生效日。

## 授权检查（`source-registry check`）

`allowed_to_download`、`allowed_for_derivative_work`、`allowed_for_ml_training`
全部为 True，`license_status=authorized`，且 `at` 在授权时间窗内，才算通过。
`generate --source-id` 会先执行该检查，未通过直接拒绝生成。

## 合规约定（落实 §4 约束）

- 优先使用平台开放接口、已授权账号、版权合作方或自有视频；
- 遵守服务条款、robots 规则、访问频率限制和个人信息保护要求；
- 不实现绕过登录、验证码、签名、DRM 或其他访问控制的能力；
- 下载任务必须支持来源级限速、退避、暂停和删除请求；
- 原始 URL、Cookie、账号信息等敏感数据不得进入训练 manifest；
- 对人脸、用户名、联系方式、未成年人和其他隐私内容制定保留及删除策略。

当前 `registry.json` 中的 `bilibili-demo` 是占位示例（全部权限为 False），
不代表任何真实授权；真实来源需按上述流程登记。
