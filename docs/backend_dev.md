# Survey 后端设计（V1）

## 目标
- 基于 `SQLite + FastAPI` 实现可用后端，替代 JSON 文件存储。
- 支撑前端第一版核心页面：列表、详情、路径触发判定。
- `survey_dev.md` 继续只维护判定规则，本文件维护后端实现方案。

## 数据模型

说明：除特别标注外，各表均含自增 `id` 主键与 `created_at` / `updated_at`；子表通过 `case_id` 关联 `survey_cases.id`。

### 1. survey_cases（主表）
- `sample_code` 样本编号（可选；未传时默认取 `sample_dir` 最后一级目录名）
- `target_species` 目标物种
- `source_path` 来源路径
- `stage_code` 分期编号（外部接口传入）
- `bioinfo_emails_json` 生信邮箱列表（JSON，元素结构：`{"name":"...","email":"..."}`）
- `operation_emails_json` 运营邮箱列表（JSON，元素结构同上）
- `group_emails_json` 群组邮箱列表（JSON 字符串数组）
- `contact_name` / `contact_email` / `cc_emails_json` 历史联系人字段（兼容旧数据，新流程以 `bioinfo/operation/group_emails_json` 为准）
- `archive_path` 原始上传压缩包本地路径
- `status`（`created|kmer_done|nt_done|judged|failed`）
- `final_level`（冗余，便于筛选）
- `should_transfer`（冗余，便于筛选，取值 `是|否|转人工`）
- `remark`

### 2. kmer_results（1:1）
- `spe_depths_json` / `spe_freqs_json`
- `num_depths_json` / `num_freqs_json`
- `pattern` / `is_normal` / `detail`
- `warnings_json`
- `analysis_ploidy_json`
- `spe_plot_path` / `num_plot_path`（自动绘制的 kmer 峰图路径）
- `raw_json`

### 3. nt_results（1:1）
- `nt_level`（NT 判定等级：`正常|重度污染|fail`）
- `is_heavy_contamination`（是否重度污染）
- `nt_rule_version`（NT 判定规则版本）
- `target_species` / `target_category`（目标物种及其分类类别）
- `source_nt_count` / `valid_nt_count`（原始/有效 NT 条数）
- `dominant_category` / `dominant_ratio_percent`（占比最高的类别及百分比）
- `metazoa_ratio_percent` / `plantae_ratio_percent` / `bacteria_ratio_percent` / `fungi_ratio_percent` / `viruses_ratio_percent`（各界占比百分比）
- `reasonable_contamination_ratio_percent`（合理污染占比百分比）
- `pollution_ratio_percent` / `pollution_threshold_percent`（污染占比与判定阈值百分比）
- `ntcls_detail` / `ntspe_detail`
- `class_filtered_path` / `class_filtered_paths_json`（按类别过滤后的文件路径）
- `small_judged_paths_json`（样本量过小、按约定直接判定的文件路径）
- `nt_results_json`（各输入文件的 NT 判定明细数组）
- `raw_json`

### 4. gc_results（1:1）
- `executed`（是否执行了 GC 判定；GC 现随每次 survey 无条件执行）
- `status`（GC 判定状态）
- `reason`（未执行/异常原因）
- `pos_path`（`*.pos` 文件路径）
- `heavy_contamination`（GC 维度是否判定重度污染）
- `participated`（本次 GC 结果是否参与最终裁决；仅 kmer 无警告且 kmer/NT 不一致时为 true，老库补列后为 NULL）
- `gc_raw_json` / `raw_json`

### 5. survey_results（1:1）
- `final_level` / `should_transfer`（`是|否|转人工`） / `remark`
- `rule_version`
- `raw_json`

### 6. result_metrics（1:1）
- `result_path`
- `ploidy_pattern` / `ploidy_multiplier`
- `raw_json`（原始 `*.Result.xls` 首行）
- `adjusted_json`（按倍型修正后的结果）
- `remark`

### 7. manual_reviews（1:N）
- `case_id` 关联 `survey_cases.id`
- `reviewer_id`（审核人 user id，可空，关联 `users.id`；历史记录为 NULL）
  - 新库由 `create_all` 建出带外键的列；老库通过 `ALTER TABLE` 补列，SQLite 的 `ALTER ADD COLUMN` 不支持附带外键约束，故老库中该列为普通可空 INTEGER（业务层不依赖数据库级外键）。
- `reviewer_name`（审核人显示名快照；提交审核时写入当时用户的 `display_name`，保证改名/停用后历史可读；历史记录为 `system`）
- `kmer_review`（`correct|incorrect|uncertain`）
- `nt_review`（`correct|incorrect|uncertain`）
- `gc_review`（`correct|incorrect|uncertain`）
- `final_decision`（存储归一化后的 `transfer|no_transfer`）
- `note`（审核备注；作为审核邮件正文发送）
- `kmer_incorrect_reason`（Kmer 判定不正确原因，可空）
  - 仅当 `kmer_review=incorrect` 时记录人工填写的原因，用于后续校对/改进算法。
  - **不作为邮件正文发送**（区别于 `note`）；`kmer_review` 非 `incorrect` 时落库为 NULL。
  - 老库通过 `ALTER TABLE manual_reviews ADD COLUMN kmer_incorrect_reason TEXT` 补列（见「启动迁移」）。

### 8. users（用户表）
- `username`（登录名，唯一）
- `display_name`（显示名，用于审核人展示）
- `password_hash`（PBKDF2-SHA256 哈希，格式 `pbkdf2_sha256$迭代数$salt_hex$hash_hex`）
- `is_active`（是否启用；停用后无法登录，且其未过期会话逐请求被拒）
- `created_at` / `updated_at`

### 9. user_sessions（登录会话表）
- `user_id` 关联 `users.id`
- `token_hash`（会话 token 的 sha256，唯一索引；库中不存明文 token）
- `expires_at`（过期时间，默认登录后 7 天，可配）
- `created_at`

### 启动迁移（老库兼容）
服务启动时 `init_db` 幂等执行（`--reload` 下可能多次）：
- `Base.metadata.create_all` 建出全部表（新库一次到位，含外键/索引）。
- 对老库做 `ALTER TABLE ... ADD COLUMN` 补列（SQLite 的 `ADD COLUMN` 不支持附带 `FOREIGN KEY`/`UNIQUE` 约束，故老库中这些列为普通可空列，业务层不依赖 DB 级约束）：
  - `survey_cases`：`stage_code/contact_name/contact_email/cc_emails_json/bioinfo_emails_json/operation_emails_json/group_emails_json/archive_path`
  - `manual_reviews`：`reviewer_id`（并建索引）、`kmer_incorrect_reason`
  - `gc_results`：`participated`（并建索引；老记录为 NULL，前端按 `executed` 回退展示）
- `users` 表为空时自动创建默认管理员（见「鉴权设计」）。

## V1 已实现接口

鉴权说明：标注 🔒 的接口需登录后调用（携带 `Authorization: Bearer <token>`）；外部机器对机器接口（`run-*`/`check-by-path`）保持开放。详见「鉴权设计」章。

- `GET /health`
- `POST /api/auth/login` 登录，返回 token
- `POST /api/auth/logout` 登出（幂等）
- `GET /api/auth/me` 当前登录用户
- 🔒 `GET /api/cases` 列表查询（`limit/offset/target_species/final_level/should_transfer/status/stage_code/bioinfo_email/review_status`）
- 🔒 `GET /api/cases/stats` 样本统计（`total/by_final_level/reviewed/unreviewed`）
- 🔒 `GET /api/cases/{case_id}` 样本详情
- 🔒 `GET /api/cases/{case_id}/kmer-plot?spectrum=spe|num` 获取 kmer 峰图（PNG）
- 🔒 `GET /api/cases/{case_id}/gc-plot` 获取 GC 图（PNG，始终尝试生成并展示）
- 🔒 `GET /api/cases/{case_id}/judge-report` 获取判定报告（结构化+文本总结）
- 🔒 `GET /api/cases/{case_id}/report-html` 获取样本目录内 html 报告（用于前端看板展示）
- 🔒 `GET /api/cases/{case_id}/archive` 下载 run-by-archive 保存的原始压缩包
- 🔒 `GET /api/cases/{case_id}/manual-review` 获取人工审核记录（倒序，含审核人）
- 🔒 `POST /api/cases/{case_id}/manual-review` 提交人工审核记录（审核人由登录态自动确定）
  - `final_decision` 入参兼容：`transfer|no_transfer|confirm|rerun|manual_transfer`
  - 后端会归一化存储为：`transfer|no_transfer`
  - 当 `kmer_review=incorrect` 时 `kmer_incorrect_reason` 必填（强制填写 Kmer 判定不正确原因），否则返回 `400`
- 🔒 `DELETE /api/cases/{case_id}` 删除样本（删除后可重新发起同路径判定）
- 🔒 `POST /api/cases/rerun-survey` 显式确认后重跑并覆盖该路径的已有记录
- `POST /api/cases/check-by-path` 只检查样本目录文件是否齐全（不执行判定）
- `POST /api/cases/run-kmer` 输入样本目录，执行 kmer 判定并入库
- `POST /api/cases/run-nt` 输入样本目录，执行 NT 判定并入库
- `POST /api/cases/run-survey` 输入样本目录，执行 `survey_judge_single.py` 同款完整判定（kmer+nt+survey+result）并入库
- `POST /api/cases/run-by-path` 输入样本目录，自动检查 5 个必需文件；若齐全则执行完整 survey 判定并入库
- `POST /api/cases/run-by-archive` 外部上传 `.zip` 压缩包，服务端落盘并解压后执行完整 survey 判定并入库

## 鉴权设计

### 目标与范围
- 用户规模 3-10 人（内部工具），无注册系统；用户由 `scripts/manage_users.py` 命令行维护。
- 核心目标：提交人工审核时自动绑定审核人（`manual_reviews.reviewer_id` + `reviewer_name` 快照）。
- **受保护接口**（前端使用）：列表、统计、详情、峰图/GC 图、判定报告、HTML 报告、压缩包下载、人工审核读写、重跑、删除。
- **开放接口**（外部机器对机器）：`run-by-path/run-by-archive/run-kmer/run-nt/run-survey/check-by-path`，以及 `/health`、`/api/auth/login`。

### 凭证与存储
- 密码哈希：stdlib `hashlib.pbkdf2_hmac`（SHA256，60 万迭代，16 字节随机盐），零第三方依赖；存储格式 `pbkdf2_sha256$迭代数$salt_hex$hash_hex`，带方案前缀便于未来升级 bcrypt/argon2。
- 会话 token：`secrets.token_urlsafe(32)`；`user_sessions` 表只存 `sha256(token)`，支持服务端撤销（登出/停用即失效）。
- token 有效期默认 7 天（`AUTH_TOKEN_TTL_HOURS` 可配），过期会话惰性清理。

### 凭证传递
- JSON 接口一律走请求头 `Authorization: Bearer <token>`。
- `<img>/<iframe>/<a>` 直连的资源端点（kmer-plot/gc-plot/report-html/archive）无法携带请求头，额外支持 `?token=` 查询参数兜底；这些端点响应带 `Cache-Control: no-store` 与 `Referrer-Policy: no-referrer`，降低 token 出现在 URL 后的缓存/Referer 泄露风险。

### 审核人绑定
- 审核人只能由后端从登录态解析注入，**不接受客户端传入**（`ManualReviewIn` 无审核人字段），防止伪造他人身份。
- 写入规则：`reviewer_id`=当前用户 id；`reviewer_name`=用户 `display_name` 快照（为空则 `username`）。
- 历史审核记录 `reviewer_id` 为 NULL、`reviewer_name` 为 `system`。

### 首次启动默认管理员
- `init_db` 时若 `users` 表为空，自动创建默认管理员：用户名/显示名/密码分别取 `ADMIN_USERNAME`（默认 admin）/`ADMIN_DISPLAY_NAME`（默认 管理员）/`ADMIN_PASSWORD`。
- `ADMIN_PASSWORD` 留空时随机生成密码并打印到启动日志（请尽快用 `scripts/manage_users.py` 修改）。

## 通用测试前缀
```bash
BASE_URL="http://127.0.0.1:8001"
SAMPLE_DIR="/data/work/zhurui/survey_rec/data/to_zhurui_surey_jinxianlan/FDSW260016098-2r_DaYuanYe叶-1"

SAMPLE_DIR1="data/shenshaoqi_data_v2/1"
```

## 接口说明

### 1) 列表查询（GET /api/cases）
#### 请求参数
- `limit`：返回条数，默认 `20`，范围 `1~200`
- `offset`：偏移量，默认 `0`
- `target_species`：按目标物种模糊匹配（`contains`）
- `final_level`：按最终等级精确匹配
- `should_transfer`：按是否转移精确匹配（如 `是/否`）
- `status`：按状态精确匹配（`created|kmer_done|nt_done|judged|failed`）
- `stage_code`：按分期编号模糊匹配（`contains`）
- `bioinfo_email`：按生信邮箱模糊匹配（匹配 `bioinfo_emails_json`）
- `review_status`：人工审核状态（`reviewed|unreviewed`）

### 2) 样本详情（GET /api/cases/{case_id}）
#### 说明
- 返回单个样本完整详情，包含 `kmer_result/nt_result/gc_result/survey_result/result_metrics/manual_reviews` 等关联数据。

### 3) 获取 kmer 峰图（GET /api/cases/{case_id}/kmer-plot）
#### 请求参数
- `spectrum`：`spe` 或 `num`

### 4) 获取 GC 图（GET /api/cases/{case_id}/gc-plot）
#### 说明
- 返回已生成的 GC 图 PNG；可选查询参数 `step`（`ge=0`）用于获取**演进步骤快照**：
  - 不传 `step`：返回最终帧（`gc_raw.artifacts.png`），与历史行为完全一致；
  - 传 `step=N`：返回 `gc_raw.artifacts.png_steps` 中 `index==N` 的步骤图
    （`algo`/`llm_round`/`final` 各帧）；step 越界或老数据无步骤快照时返回 404。
- 所有返回路径均校验必须位于受管目录 `data/gc_plots/` 内，否则 403。
- 若未生成或路径非法，接口返回 404/403。

### 5) 获取判定报告（GET /api/cases/{case_id}/judge-report）
#### 说明
- 根据已入库的 `kmer_result/nt_result/result_metrics/survey_result` 自动填充判定报告。
- 该接口不触发重算，仅做结果组织与文本生成。

#### curl 示例
```bash
curl -X GET "http://10.11.0.6:8001/api/cases/12/judge-report"
```

### 6) 获取样本 HTML 报告（GET /api/cases/{case_id}/report-html）
#### 说明
- 在样本目录内查找 `.html` 报告并返回内容。

### 7) 获取原始压缩包（GET /api/cases/{case_id}/archive）
#### 说明
- 仅适用于 `run-by-archive` 入库的样本。

### 8) 获取人工审核记录（GET /api/cases/{case_id}/manual-review）
#### 说明
- 按创建时间倒序返回该样本的人工审核历史。
- 每条记录含 `reviewer_id`（审核人 user id，历史记录为 null）与 `reviewer_name`（审核人显示名快照，历史记录为 `system`）。
- 需登录（🔒）。

### 9) 提交人工审核记录（POST /api/cases/{case_id}/manual-review）
#### 请求参数
- `kmer_review`：`correct|incorrect|uncertain`
- `nt_review`：`correct|incorrect|uncertain`
- `gc_review`：`correct|incorrect|uncertain`
- `final_decision`：`transfer|no_transfer|confirm|rerun|manual_transfer`
- `note`：审核备注（作为邮件正文发送；即使 AI 判定有误，人工也会把备注改成正确结论，不影响收件人体验）
- `kmer_incorrect_reason`：Kmer 判定不正确原因（仅当 `kmer_review=incorrect` 时必填；仅记录用于算法校对，不发送邮件）

#### 校验规则
- **Kmer 判定不正确强制填原因**：当 `kmer_review=incorrect` 时，`kmer_incorrect_reason` 必填且去除首尾空白后非空，否则返回 `400`，不写库、不触发邮件。
- 落库规则：仅当 `kmer_review=incorrect` 时记录 `kmer_incorrect_reason`（去首尾空白）；其余情况该字段落库为 `NULL`，保证数据干净。
- 其余字段取值校验沿用 `ManualReviewIn` 的正则约束（见 `schemas.py`）。

#### 设计说明
- 该原因与审核备注 `note` **解耦**：`note` 会作为邮件正文发送给收件人，而原因只用于内部记录、便于后续校对与改进算法，因此单独存入 `manual_reviews.kmer_incorrect_reason`，不占用 `note`、不进入邮件正文。
- 因新增列，老库由启动迁移自动 `ALTER TABLE manual_reviews ADD COLUMN kmer_incorrect_reason TEXT`（见「启动迁移」）。

#### 说明
- 需登录（🔒）。审核人由登录态自动确定并写入 `reviewer_id`/`reviewer_name`，**不接受审核人入参**。
- 入库成功后仍会按 `MAIL_ENABLED` 触发审核备注邮件（邮件正文取 `note`，行为不变，不含原因）。

### 10) 检查文件但不执行（POST /api/cases/check-by-path）
#### 请求参数
- `sample_dir`：样本目录绝对路径或相对路径

#### curl 示例
```bash
curl -X POST "$BASE_URL/api/cases/check-by-path" \
  -H "Content-Type: application/json" \
  -d "{
    \"sample_dir\": \"$SAMPLE_DIR1\"
  }"
```

#### 返回关键字段
- `file_check.kmer_complete`：是否具备 kmer 执行条件（SpeFreq+NumFreq）
- `file_check.nt_complete`：是否具备 NT 执行条件（ntcls+ntspe）
- `file_check.complete`：是否具备 survey 执行条件（五文件齐全，含 `*.Result.xls`）
- `file_check.missing`：缺失文件列表

#### 响应示例
```json
{
  "sample_dir": "/path/to/sample",
  "file_check": {
    "spe_path": "/path/to/sample/a.SpeFreq.cut",
    "num_path": "/path/to/sample/a.NumFreq.cut",
    "ntcls_path": "/path/to/sample/all.ntcls.xls",
    "ntspe_path": "/path/to/sample/all.ntspe.xls",
    "result_path": "/path/to/sample/a.Result.xls",
    "missing": [],
    "kmer_complete": true,
    "nt_complete": true,
    "complete": true
  },
  "message": "文件齐全，可执行完整 survey 判定"
}
```

### 11) run-kmer（POST /api/cases/run-kmer）
#### 请求参数
- `sample_dir`：样本目录
- `sample_code`：样本编号（可选；未传或传空字符串时，默认取 `sample_dir` 最后一级目录名）
- `case_id`：已有 case 时可传，传了就更新该 case（可选）
- `verbose`：是否打印详细日志（默认 `true`）

#### curl 示例
```bash
curl -X POST "$BASE_URL/api/cases/run-kmer" \
  -H "Content-Type: application/json" \
  -d "{
    \"sample_dir\": \"$SAMPLE_DIR\",
    \"sample_code\": \"FDSW250019884-2a\",
    \"verbose\": false
  }"
```

### 12) run-nt（POST /api/cases/run-nt）
#### 请求参数
- 同 `run-kmer`

#### curl 示例
```bash
curl -X POST "$BASE_URL/api/cases/run-nt" \
  -H "Content-Type: application/json" \
  -d "{
    \"sample_dir\": \"$SAMPLE_DIR\",
    \"sample_code\": \"FDSW250019884-2a\",
    \"verbose\": false
  }"
```

### 13) run-survey（POST /api/cases/run-survey，推荐前端主按钮）
#### 请求参数
- 同 `run-kmer`

#### curl 示例
```bash
curl -X POST "$BASE_URL/api/cases/run-survey" \
  -H "Content-Type: application/json" \
  -d "{
    \"sample_dir\": \"$SAMPLE_DIR\",
    \"sample_code\": \"FDSW250019884-2a\",
    \"verbose\": false
  }"
```

### 14) run-by-path（POST /api/cases/run-by-path，兼容接口）
#### 请求参数
- 同 `run-survey`

#### 返回新增字段
- `judge_report`：判定报告，字段示例
```json
{
  "nt_abnormal": false,
  "kmer_poisson": true,
  "ploidy_text": "推测二倍体",
  "transfer_suggestion": "建议流转",
  "summary_text": "采用kmer 17进行Survey分析，预估得到: ..."
}
```

#### curl 示例
```bash
curl -X POST "$BASE_URL/api/cases/run-by-path" \
  -H "Content-Type: application/json" \
  -d "{
    \"sample_dir\": \"$SAMPLE_DIR\",
    \"sample_code\": \"FDSW250019884-2a\",
    \"verbose\": false
  }"
```

### 15) rerun-survey（POST /api/cases/rerun-survey，显式确认覆盖）
#### 请求参数
- `sample_dir`：样本目录（必须已存在历史记录）
- `sample_code`：样本编号（可选；未传或传空字符串时，默认取 `sample_dir` 最后一级目录名）
- `verbose`：是否打印详细日志（默认 `true`）
- `confirm`：必须为 `true`，否则拒绝执行

#### curl 示例
```bash
curl -X POST "$BASE_URL/api/cases/rerun-survey" \
  -H "Content-Type: application/json" \
  -d "{
    \"sample_dir\": \"$SAMPLE_DIR\",
    \"sample_code\": \"FDSW250019884-2a\",
    \"verbose\": false,
    \"confirm\": true
  }"
```

### 16) run-by-archive（POST /api/cases/run-by-archive，外部上传压缩包）
#### 请求参数（`multipart/form-data`）
- `archive`：样本文件压缩包（仅支持 `.zip`）
- `stage_code`：分期编号
- `sample_name`：样本名称（核酸编号，唯一标识符）
- `bioinfo_emails`：生信邮箱列表 JSON 字符串（元素结构同旧 `contact`）
```json
[{"name":"测试生信","email":"bio@example.com"}]
```
- `operation_emails`：运营邮箱列表 JSON 字符串（格式同 `bioinfo_emails`）
- `group_emails`：群组邮箱，支持 JSON 数组字符串或逗号分隔字符串（可选）
- `verbose`：是否输出详细日志（可选，默认 `true`）

#### 压缩包内文件要求
- 必需：`*.SpeFreq.cut`
- 必需：`*.NumFreq.cut`
- 必需：`all.ntcls.xls`（备选匹配：`*.ntcls.xls`）
- 必需：至少一个 `*.species.xls`（备选：`*.species.test.xls`）
- 必需：`*.Result.xls`
- 可选：`*.pos`
- 可选：`.html` 报告文件

#### 处理逻辑
- 服务端先保存压缩包到本地：`data/external_uploads/YYYYMMDD/<sample_name>_<task_id>/upload.zip`
- 解压到：`.../extracted/`
- 自动识别样本目录（若解压后仅有一层目录则进入该目录）
- 后续与现有 `run-by-path` 一致：检查文件完整性 -> 执行 survey 判定 -> 入库
- 额外参数会写入 `survey_cases`：`stage_code/bioinfo_emails_json/operation_emails_json/group_emails_json/archive_path`
- 返回中包含 `judge_report`（同 `run-by-path`）

#### curl 示例
```bash
BASE_URL="http://10.11.0.6:8001"
ZIP_PATH="/data/work/zhurui/survey_rec/data/to_zhurui_surey_jinxianlan/FDSW260016086-2r_CaiXia叶-1/survey_external_test.zip"

curl -X POST "$BASE_URL/api/cases/run-by-archive" \
  -F "archive=@${ZIP_PATH};type=application/zip" \
  -F "stage_code=P1" \
  -F "sample_name=FDSW260016086-2r" \
  -F 'bioinfo_emails=[{"name":"测试生信","email":"bio@example.com"}]' \
  -F 'operation_emails=[{"name":"测试运营","email":"ops_person@example.com"}]' \
  -F 'group_emails=["ops@example.com","qa@example.com"]' \
  -F "verbose=false"
```

#### 响应示例（成功）
```json
{
  "sample_dir": "/data/work/zhurui/survey_rec/data/external_uploads/20260428/FDSW260016086-2r_c3763b3d24fe/extracted/FDSW260016086-2r_CaiXia叶-1",
  "archive_path": "/data/work/zhurui/survey_rec/data/external_uploads/20260428/FDSW260016086-2r_c3763b3d24fe/upload.zip",
  "stage_code": "P1",
  "sample_name": "FDSW260016086-2r",
  "bioinfo_emails": [{"name": "测试生信", "email": "bio@example.com"}],
  "operation_emails": [{"name": "测试运营", "email": "ops_person@example.com"}],
  "group_emails": ["ops@example.com", "qa@example.com"],
  "file_check": {"complete": true, "missing": []},
  "executed": true,
  "message": "压缩包文件齐全，已完成survey判定并入库",
  "case_id": 9
}
```

#### 响应示例（文件不全）
```json
{
  "executed": false,
  "message": "输入文件不完整，缺失: *.Result.xls",
  "file_check": {
    "complete": false,
    "missing": ["*.Result.xls"]
  }
}
```

### 17) 删除样本（DELETE /api/cases/{case_id}）
#### curl 示例
```bash
curl -X DELETE "$BASE_URL/api/cases/12"
```

#### 行为说明
- 删除样本记录时会同步清理该样本关联的受管产物：
  - kmer 峰图（仅 `data/kmer_plots/` 内）；
  - GC 全部产物：终帧 `*.gc_line.png`、`*.gc_line.json`、演进步骤 `*.gc_line.step{N}.png`（含同 stem glob 兜底孤儿文件）、LLM 日志 `*.gc_line.llm_log.json`（仅 `data/gc_plots/` 内，非受管路径忽略并计入响应提示）。

### 18) 样本统计（GET /api/cases/stats）
#### 说明
- 返回全库样本的统计概览，供前端工作台统计卡片展示。
- 统计为全量口径，不随列表筛选条件变化。

#### 返回字段
- `total`：样本总数
- `by_final_level`：按 `final_level` 分组的计数（键如 `正常 / 重度污染 / 待人工复核 / 未判定`）
- `reviewed`：已审核样本数（存在人工审核记录）
- `unreviewed`：未审核样本数

#### curl 示例
```bash
curl -X GET "$BASE_URL/api/cases/stats"
```

#### 响应示例
```json
{
  "total": 289,
  "by_final_level": {"正常": 180, "重度污染": 13, "待人工复核": 96},
  "reviewed": 150,
  "unreviewed": 139
}
```

### 19) 登录（POST /api/auth/login）
#### 请求参数
- `username`：登录名
- `password`：密码
#### 说明
- 用户不存在/已停用/密码错误统一返回 401「用户名或密码错误」（避免用户名枚举）。
- 成功后创建会话并返回明文 token（仅此一次）。

#### curl 示例
```bash
curl -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<密码>"}'
```

#### 响应示例
```json
{
  "access_token": "vN8UDJ481M2vvWZElEc2T1zOgzJraaVGwLZxdjVF-wo",
  "token_type": "bearer",
  "expires_at": "2026-08-13T07:26:46",
  "user": {"id": 1, "username": "admin", "display_name": "管理员", "is_active": true}
}
```

### 20) 登出（POST /api/auth/logout）
#### 说明
- 幂等：token 已失效时调用也不报错。删除对应会话行，token 立即失效。

#### curl 示例
```bash
curl -X POST "$BASE_URL/api/auth/logout" -H "Authorization: Bearer $TOKEN"
```

### 21) 当前登录用户（GET /api/auth/me）
#### 说明
- 需登录（🔒）。返回当前 token 对应的用户信息，供前端校验登录态与展示。

#### curl 示例
```bash
curl -X GET "$BASE_URL/api/auth/me" -H "Authorization: Bearer $TOKEN"
```

#### 受保护接口调用示例（携带 token）
```bash
# 登录取 token
TOKEN=$(curl -s -X POST "$BASE_URL/api/auth/login" -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<密码>"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
# 列表
curl -X GET "$BASE_URL/api/cases?limit=20" -H "Authorization: Bearer $TOKEN"
# 资源端点也可用 ?token=（浏览器原生加载场景）
curl -X GET "$BASE_URL/api/cases/12/kmer-plot?spectrum=spe&token=$TOKEN"
```

## 执行类接口返回说明
（`run-kmer/run-nt/run-survey/run-by-path/rerun-survey/run-by-archive`）
- `run-kmer` 依赖 `file_check.kmer_complete=true`。
- `run-nt` 依赖 `file_check.nt_complete=true`。
- `run-survey/run-by-path` 依赖 `file_check.complete=true`（即同时具备 `*.SpeFreq.cut/*.NumFreq.cut/all.ntcls.xls/all.ntspe.xls/*.Result.xls`）。
- `run-by-archive` 会将压缩包保存到 `data/external_uploads/`，解压后再执行与 `run-by-path` 一致的完整判定逻辑。
- 条件不满足时：`executed=false`，仅返回缺失项。
- `run-kmer/run-nt/run-survey/run-by-path` 都会先检查 `sample_dir` 是否已存在历史记录；若已存在，返回 `409`。
- `rerun-survey` 用于显式覆盖重跑：`confirm=true` 且路径已存在时才执行。
- 执行类接口若未传 `sample_code`（或传空字符串），会自动使用 `sample_dir` 的最后一级目录名作为样本编号。
- `executed=true`：该接口对应步骤执行成功并已入库。
- `case_id`：数据库中的样本主键，可用于后续 `GET /api/cases/{case_id}` 查询。
- `run-survey/rerun-survey/run-by-path` 的判定入口统一与 `survey_judge_single.py` 对齐：目标物种由 `all.ntcls.xls` 首行 `Sample name` 推导，并同时用于 kmer 与 nt。
- `run-kmer/run-survey/rerun-survey/run-by-path` 会自动绘制 Spe/Num 峰图，并写入 `kmer_result.spe_plot_path/num_plot_path`。
- `run-survey/run-by-path/run-by-archive/rerun-survey` 中 GC 复核随 survey **无条件执行**（产出 GC 图与判定数据用于展示/追溯）；是否参与最终裁决由 `gc_result.participated` 标识——仅 kmer 无警告且 kmer/NT 判定不一致时为 true，其余情况 GC 仅展示、不改变判定逻辑。`run-by-path/run-by-archive` 入库前另由 `_ensure_gc_plot_artifacts` 兜底补图（GC 首次执行未产出 PNG 时重试一次，失败仅加 warning）。
- GC 产物落盘于受管目录 `data/gc_plots/<样本名>_<sha1前16位>/`：终帧 `*.gc_line.png`、JSON `*.gc_line.json`、演进步骤 `*.gc_line.step{N}.png`、LLM 日志 `*.gc_line.llm_log.json`；`DELETE /api/cases/{id}` 会按 `gc_raw.artifacts.png_steps` 与 `llm_adjustment.log_path` 收集全部路径清理（并对同 stem `*.step*.png` 做 glob 兜底），非受管路径忽略。
- 峰图统一输出到固定目录 `data/kmer_plots/`（按 `sample_dir` 哈希分桶），不再写回样本目录。

## run-survey 响应示例（精简）
```json
{
  "sample_dir": "/path/to/sample",
  "executed": true,
  "message": "survey判定完成并已入库",
  "file_check": {
    "complete": true
  },
  "case_id": 12,
  "case_detail": {
    "id": 12,
    "target_species": "手掌参",
    "kmer_result": {
      "pattern": "二倍体",
      "is_normal": true,
      "spe_main_peak_depth": 68.0,
      "num_main_peak_depth": 70.0
    },
    "nt_result": {
      "nt_level": "fail",
      "is_heavy_contamination": false
    },
    "survey_result": {
      "final_level": "重度污染",
      "should_transfer": "否"
    },
    "result_metrics": {
      "ploidy_pattern": "三倍体",
      "ploidy_multiplier": 3,
      "remark": "三倍体，按约定将 Genome_size(M)/Revised_Genome_size(M) 乘 3 以换算到该倍体总基因组大小"
    }
  }
}
```

## 常用数据库查询速查（SQLite）
数据库文件：
```bash
data/survey_backend.sqlite3
```

### Shell 一行命令版（可直接复制）
```bash
# 变量版（推荐）
DB="data/survey_backend.sqlite3"

# 1) 最近 20 条样本（含判定结果）
sqlite3 "$DB" "SELECT c.id,c.sample_code,c.stage_code,c.status,sr.final_level,sr.should_transfer,c.updated_at FROM survey_cases c LEFT JOIN survey_results sr ON sr.case_id=c.id ORDER BY c.updated_at DESC,c.id DESC LIMIT 20;"

# 2) 查询包含运营邮箱的 survey 结果（替换邮箱关键字）
sqlite3 "$DB" "SELECT c.id,c.sample_code,c.stage_code,c.operation_emails_json,sr.final_level,sr.should_transfer,c.updated_at FROM survey_cases c LEFT JOIN survey_results sr ON sr.case_id=c.id WHERE c.operation_emails_json LIKE '%ops_person@example.com%' ORDER BY c.updated_at DESC;"

# 3) 查询包含群组邮箱的样本（替换邮箱关键字）
sqlite3 "$DB" "SELECT id,sample_code,stage_code,group_emails_json,status,updated_at FROM survey_cases WHERE group_emails_json LIKE '%ops@example.com%' ORDER BY updated_at DESC;"

# 4) 查询某阶段重度污染（替换阶段）
sqlite3 "$DB" "SELECT c.id,c.sample_code,c.stage_code,sr.final_level,sr.remark,c.updated_at FROM survey_cases c JOIN survey_results sr ON sr.case_id=c.id WHERE c.stage_code='P1' AND sr.final_level='重度污染' ORDER BY c.updated_at DESC;"

# 5) 判定级别统计
sqlite3 "$DB" "SELECT COALESCE(sr.final_level,'未判定') AS final_level,COUNT(*) AS cnt FROM survey_cases c LEFT JOIN survey_results sr ON sr.case_id=c.id GROUP BY COALESCE(sr.final_level,'未判定') ORDER BY cnt DESC;"

# 6) 单样本全链路联查（替换 sample_code）
sqlite3 "$DB" "SELECT c.id,c.sample_code,c.target_species,c.status,kr.pattern AS kmer_pattern,nr.nt_level,gr.status AS gc_status,sr.final_level,sr.should_transfer,c.updated_at FROM survey_cases c LEFT JOIN kmer_results kr ON kr.case_id=c.id LEFT JOIN nt_results nr ON nr.case_id=c.id LEFT JOIN gc_results gr ON gr.case_id=c.id LEFT JOIN survey_results sr ON sr.case_id=c.id WHERE c.sample_code='FDSW260016086-2r';"

# 7) 排查未完成判定（没有 survey_results）
sqlite3 "$DB" "SELECT c.id,c.sample_code,c.stage_code,c.status,c.updated_at FROM survey_cases c LEFT JOIN survey_results sr ON sr.case_id=c.id WHERE sr.case_id IS NULL ORDER BY c.updated_at DESC;"

# 8) AI 最终结论与人工审核不一致（仅比较 AI 给出明确结论 是/否 的样本，转人工不计入；每个样本取最新一条审核记录）
sqlite3 "$DB" "WITH latest_review AS (SELECT m.* FROM manual_reviews m JOIN (SELECT case_id, MAX(id) AS max_id FROM manual_reviews GROUP BY case_id) t ON m.id=t.max_id) SELECT c.id,c.sample_code,c.stage_code,sr.final_level,sr.should_transfer,lr.final_decision,lr.note FROM survey_cases c JOIN survey_results sr ON sr.case_id=c.id JOIN latest_review lr ON lr.case_id=c.id WHERE sr.should_transfer IN ('是','否') AND CASE sr.should_transfer WHEN '是' THEN 'transfer' ELSE 'no_transfer' END <> lr.final_decision ORDER BY c.updated_at DESC;"

# 9) kmer/nt 与人工判定不一致（最新审核记录中 kmer_review/nt_review 为 incorrect，含 Kmer 不正确原因）
sqlite3 "$DB" "WITH latest_review AS (SELECT m.* FROM manual_reviews m JOIN (SELECT case_id, MAX(id) AS max_id FROM manual_reviews GROUP BY case_id) t ON m.id=t.max_id) SELECT c.id,c.sample_code,kr.pattern,lr.kmer_review,lr.kmer_incorrect_reason,nr.nt_level,nr.is_heavy_contamination,lr.nt_review,lr.note FROM survey_cases c JOIN latest_review lr ON lr.case_id=c.id LEFT JOIN kmer_results kr ON kr.case_id=c.id LEFT JOIN nt_results nr ON nr.case_id=c.id WHERE lr.kmer_review='incorrect' OR lr.nt_review='incorrect' ORDER BY c.updated_at DESC;"

# 10) 按审核人统计审核量
sqlite3 "$DB" "SELECT reviewer_name,COUNT(*) AS cnt FROM manual_reviews GROUP BY reviewer_name ORDER BY cnt DESC;"

# 11) 最近审核记录（含审核人用户名与显示名）
sqlite3 "$DB" "SELECT mr.id,mr.case_id,u.username,u.display_name,mr.reviewer_name,mr.final_decision,mr.created_at FROM manual_reviews mr LEFT JOIN users u ON u.id=mr.reviewer_id ORDER BY mr.id DESC LIMIT 10;"

# 12) Kmer 判定不正确原因汇总（用于校对/改进算法；按原因聚合计数）
sqlite3 "$DB" "SELECT kmer_incorrect_reason,COUNT(*) AS cnt FROM manual_reviews WHERE kmer_incorrect_reason IS NOT NULL AND kmer_incorrect_reason<>'' GROUP BY kmer_incorrect_reason ORDER BY cnt DESC;"
```

## 目录结构
```text
backend/
  app/
    main.py
    db.py
    models.py
    schemas.py
    crud.py
    json_utils.py
    security.py        # 密码哈希 / 会话 token 纯工具
    deps.py            # 鉴权依赖 get_current_user
    routers/
      cases.py         # 受保护 router + 外部开放 public_router
      auth.py          # login / logout / me
scripts/
  manage_users.py      # 用户管理 CLI（create/reset-password/set-active/list）
```

## 运行方式
先准备配置文件（推荐）：
```bash
cp .env.example .env
```

后端会在启动时自动按顺序加载：
- 项目根目录 `.env`
- `backend/.env`

说明：
- 自动加载时不会覆盖你当前 shell 已有的同名环境变量。
- 因此可用“`.env` 提供默认值 + shell 临时覆盖”的方式调试。

可配置项示例（邮件相关，默认关闭）：
```bash
export MAIL_ENABLED=false
export MAIL_FROM="1623893955@qq.com"
export MAIL_TO="zhurui8901@novogene.com"
export MAIL_SMTP_HOST="smtp.qq.com"
export MAIL_SMTP_PORT=465
export MAIL_SMTP_USE_SSL=true
export MAIL_SMTP_USERNAME="1623893955@qq.com"
export MAIL_SMTP_PASSWORD="<QQ邮箱SMTP授权码>"
export MAIL_SUBJECT_PREFIX="[Survey提醒]"
export MAIL_CASE_LIST_URL="http://10.11.0.6:5173/cases"
```

可配置项示例（登录鉴权相关）：
```bash
export AUTH_TOKEN_TTL_HOURS=168      # token 有效期（小时），默认 168（7 天）
export ADMIN_USERNAME=admin          # 首次启动自动创建的默认管理员用户名
export ADMIN_DISPLAY_NAME=管理员      # 默认管理员显示名
export ADMIN_PASSWORD=               # 留空则首次启动随机生成并打印到启动日志
```

说明：
- `MAIL_ENABLED=false` 时不发送邮件，仅执行判定与入库。
- `MAIL_ENABLED=true` 时，在 `run-survey`、`rerun-survey`、`run-by-path`、`run-by-archive` 成功后异步发送提醒邮件；`manual-review` 入库成功后会把备注内容作为邮件正文发送（失败不影响主流程）。
- `MAIL_TO` 当前先固定 `zhurui8901@novogene.com`，后续可改为动态收件策略。

## 用户管理（scripts/manage_users.py）

无注册系统，用户由命令行脚本维护。**必须从项目根目录运行**（数据库路径相对 cwd）。

```bash
# 列出用户（含活跃会话数）
conda run -n zhurui_agent python scripts/manage_users.py list

# 创建用户（密码缺省时交互输入，两次确认，长度 >= 10）
conda run -n zhurui_agent python scripts/manage_users.py create --username zhurui --display-name 朱锐

# 重置密码
conda run -n zhurui_agent python scripts/manage_users.py reset-password --username zhurui

# 停用/启用（停用时同时注销该用户全部在线会话）
conda run -n zhurui_agent python scripts/manage_users.py set-active --username zhurui --active false
conda run -n zhurui_agent python scripts/manage_users.py set-active --username zhurui --active true
```

说明：
- 用户名规则：2-64 位，仅允许字母/数字/下划线/点/短横线。
- 密码可用 `--password` 直接传入（会留在 shell history，仅自动化场景用），缺省走交互式输入。
- 首次启动后端时若 `users` 表为空会自动创建默认管理员（见「鉴权设计」章）。

启动后端：
```bash
conda run -n zhurui_agent python -m uvicorn backend.app.main:app --host 0.0.0.0 --reload --port 8001
```

后台运行方式：
```bash
mkdir -p logs
conda activate zhurui_agent
nohup python -m uvicorn backend.app.main:app --host 0.0.0.0 --reload --port 8001 > logs/backend_dev.log 2>&1 &
echo $! > logs/backend_dev.pid
```

停止后台服务：
```bash
kill "$(cat logs/backend_dev.pid)"
```
