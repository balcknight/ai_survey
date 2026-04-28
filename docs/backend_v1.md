# Survey 后端设计（V1）

## 目标
- 基于 `SQLite + FastAPI` 实现可用后端，替代 JSON 文件存储。
- 支撑前端第一版核心页面：列表、详情、路径触发判定。
- `survey_dev.md` 继续只维护判定规则，本文件维护后端实现方案。

## 数据模型

### 1. survey_cases（主表）
- `id` 主键
- `sample_code` 样本编号（可选；未传时默认取 `sample_dir` 最后一级目录名）
- `target_species` 目标物种
- `source_path` 来源路径
- `stage_code` 分期编号（外部接口传入）
- `contact_name` / `contact_email` 联系人信息（外部接口传入）
- `cc_emails_json` 抄送邮箱列表（JSON）
- `archive_path` 原始上传压缩包本地路径
- `status`（`created|kmer_done|nt_done|judged|failed`）
- `final_level`（冗余，便于筛选）
- `should_transfer`（冗余，便于筛选）
- `remark`
- `created_at` / `updated_at`

### 2. kmer_results（1:1）
- `case_id`
- `spe_depths_json` / `spe_freqs_json`
- `num_depths_json` / `num_freqs_json`
- `pattern` / `is_normal` / `detail`
- `warnings_json`
- `analysis_ploidy_json`
- `spe_plot_path` / `num_plot_path`（自动绘制的 kmer 峰图路径）
- `raw_json`

### 3. nt_results（1:1）
- `case_id`
- `nt_score` / `nt_level`
- `ntcls_score` / `ntspe_score`
- `ntcls_detail` / `ntspe_detail`
- `ntcls_top1_pass` / `ntcls_contamination_pass` / `ntspe_contamination_pass`
- `raw_json`

### 4. survey_results（1:1）
- `case_id`
- `final_level` / `should_transfer` / `remark`
- `rule_version`
- `raw_json`

### 5. result_metrics（1:1）
- `case_id`
- `result_path`
- `ploidy_pattern` / `ploidy_multiplier`
- `raw_json`（原始 `*.Result.xls` 首行）
- `adjusted_json`（按倍型修正后的结果）
- `remark`

## V1 已实现接口
- `GET /health`
- `GET /api/cases` 列表查询（`limit/offset/target_species/final_level/should_transfer/status`）
- `GET /api/cases/{case_id}` 样本详情
- `GET /api/cases/{case_id}/kmer-plot?spectrum=spe|num` 获取 kmer 峰图（PNG）
- `DELETE /api/cases/{case_id}` 删除样本（删除后可重新发起同路径判定）
- `POST /api/cases/check-by-path` 只检查样本目录文件是否齐全（不执行判定）
- `POST /api/cases/run-kmer` 输入样本目录，执行 kmer 判定并入库
- `POST /api/cases/run-nt` 输入样本目录，执行 NT 判定并入库
- `POST /api/cases/run-survey` 输入样本目录，执行 `survey_judge_single.py` 同款完整判定（kmer+nt+survey+result）并入库
- `POST /api/cases/rerun-survey` 显式确认后重跑并覆盖该路径的已有记录
- `POST /api/cases/run-by-path` 输入样本目录，自动检查 5 个必需文件；若齐全则执行完整 survey 判定并入库
- `POST /api/cases/run-by-archive` 外部上传 `.zip` 压缩包，服务端落盘并解压后执行完整 survey 判定并入库

## 通用测试前缀
```bash
BASE_URL="http://127.0.0.1:8001"
SAMPLE_DIR="/data/work/zhurui/survey_rec/data/shenshaoqi_data/survey1/X101SC2507/X101SC25070200-Z01-J002/FDSW250019884-2a_百花山C-嫩茎_1管"

SAMPLE_DIR1="data/shenshaoqi_data_v2/1"
```

## 0) 列表查询（GET /api/cases）
### 请求参数
- `limit`：返回条数，默认 `20`，范围 `1~200`
- `offset`：偏移量，默认 `0`
- `target_species`：按目标物种模糊匹配（`contains`）
- `final_level`：按最终等级精确匹配
- `should_transfer`：按是否转移精确匹配（如 `是/否`）
- `status`：按状态精确匹配（`created|kmer_done|nt_done|judged|failed`）

### curl 示例（可直接执行）
```bash
# 基础分页（第一页）
curl -G "$BASE_URL/api/cases" \
  --data-urlencode "limit=20" \
  --data-urlencode "offset=0"

# 分页（第二页）
curl -G "$BASE_URL/api/cases" \
  --data-urlencode "limit=20" \
  --data-urlencode "offset=20"

# 按目标物种筛选（模糊匹配）
curl -G "$BASE_URL/api/cases" \
  --data-urlencode "target_species=手掌参"

# 按最终等级筛选
curl -G "$BASE_URL/api/cases" \
  --data-urlencode "final_level=重度污染"

# 按是否转移筛选
curl -G "$BASE_URL/api/cases" \
  --data-urlencode "should_transfer=否"

# 按状态筛选
curl -G "$BASE_URL/api/cases" \
  --data-urlencode "status=judged"

# 组合筛选（推荐）
curl -G "$BASE_URL/api/cases" \
  --data-urlencode "target_species=手掌参" \
  --data-urlencode "final_level=重度污染" \
  --data-urlencode "should_transfer=否" \
  --data-urlencode "status=judged" \
  --data-urlencode "limit=20" \
  --data-urlencode "offset=0"
```

## 1) 检查文件但不执行
### 请求参数
- `sample_dir`：样本目录绝对路径或相对路径

### curl 示例
```bash
curl -X POST "$BASE_URL/api/cases/check-by-path" \
  -H "Content-Type: application/json" \
  -d "{
    \"sample_dir\": \"$SAMPLE_DIR1\"
  }"
```

### 返回关键字段
- `file_check.kmer_complete`：是否具备 kmer 执行条件（SpeFreq+NumFreq）
- `file_check.nt_complete`：是否具备 NT 执行条件（ntcls+ntspe）
- `file_check.complete`：是否具备 survey 执行条件（五文件齐全，含 `*.Result.xls`）
- `file_check.missing`：缺失文件列表

### 响应示例
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

## 2) run-kmer
### 请求参数
- `sample_dir`：样本目录
- `sample_code`：样本编号（可选；未传或传空字符串时，默认取 `sample_dir` 最后一级目录名）
- `case_id`：已有 case 时可传，传了就更新该 case（可选）
- `verbose`：是否打印详细日志（默认 `true`）

### curl 示例
```bash
curl -X POST "$BASE_URL/api/cases/run-kmer" \
  -H "Content-Type: application/json" \
  -d "{
    \"sample_dir\": \"$SAMPLE_DIR\",
    \"sample_code\": \"FDSW250019884-2a\",
    \"verbose\": false
  }"
```

## 3) run-nt
### 请求参数
- 同 `run-kmer`

### curl 示例
```bash
curl -X POST "$BASE_URL/api/cases/run-nt" \
  -H "Content-Type: application/json" \
  -d "{
    \"sample_dir\": \"$SAMPLE_DIR\",
    \"sample_code\": \"FDSW250019884-2a\",
    \"verbose\": false
  }"
```

## 4) run-survey（推荐前端主按钮）
### 请求参数
- 同 `run-kmer`

### curl 示例
```bash
curl -X POST "$BASE_URL/api/cases/run-survey" \
  -H "Content-Type: application/json" \
  -d "{
    \"sample_dir\": \"$SAMPLE_DIR\",
    \"sample_code\": \"FDSW250019884-2a\",
    \"verbose\": false
  }"
```

## 5) run-by-path（兼容接口）
### 请求参数
- 同 `run-survey`

### curl 示例
```bash
curl -X POST "$BASE_URL/api/cases/run-by-path" \
  -H "Content-Type: application/json" \
  -d "{
    \"sample_dir\": \"$SAMPLE_DIR\",
    \"sample_code\": \"FDSW250019884-2a\",
    \"verbose\": false
  }"
```

## 6) rerun-survey（显式确认覆盖）
### 请求参数
- `sample_dir`：样本目录（必须已存在历史记录）
- `sample_code`：样本编号（可选；未传或传空字符串时，默认取 `sample_dir` 最后一级目录名）
- `verbose`：是否打印详细日志（默认 `true`）
- `confirm`：必须为 `true`，否则拒绝执行

### curl 示例
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

## 7) run-by-archive（外部上传压缩包）
### 请求参数（`multipart/form-data`）
- `archive`：`.zip` 压缩包
- `stage_code`：分期编号
- `sample_name`：样本名称（核酸编号）
- `contact`：JSON 字符串，格式 `{"name":"...","email":"..."}`
- `cc_emails`：可选，JSON 数组字符串或逗号分隔邮箱串
- `verbose`：可选，默认 `true`

### curl 示例
```bash
ZIP_PATH="/tmp/survey_external_test.zip"
curl -X POST "$BASE_URL/api/cases/run-by-archive" \
  -F "archive=@${ZIP_PATH};type=application/zip" \
  -F "stage_code=P1" \
  -F "sample_name=FDSW260016086-2r" \
  -F 'contact={"name":"测试生信","email":"bio@example.com"}' \
  -F 'cc_emails=["ops@example.com","qa@example.com"]' \
  -F "verbose=false"
```

## 执行类接口返回说明（run-kmer/run-nt/run-survey/run-by-path/rerun-survey/run-by-archive）
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
- 峰图统一输出到固定目录 `data/kmer_plots/`（按 `sample_dir` 哈希分桶），不再写回样本目录。

## 7) 获取 kmer 峰图
### 请求参数
- `spectrum`：`spe` 或 `num`

### curl 示例
```bash
curl -L "$BASE_URL/api/cases/12/kmer-plot?spectrum=spe" --output spe_plot.png
```

## 删除接口
### curl 示例
```bash
curl -X DELETE "$BASE_URL/api/cases/12"
```

### 行为说明
- 删除样本记录时会同步删除该样本关联的峰图文件（仅清理 `data/kmer_plots/` 受管目录内文件）。

### run-survey 响应示例（精简）
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
      "nt_score": 2
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
    routers/
      cases.py
```

## 运行方式
```bash
conda run -n zhurui_agent python -m uvicorn backend.app.main:app --host 0.0.0.0 --reload --port 8001
```

后台运行方式：
```bash
mkdir -p logs
nohup python -m uvicorn backend.app.main:app --host 0.0.0.0 --reload --port 8001 > logs/backend_dev.log 2>&1 &
echo $! > logs/backend_dev.pid
```

停止后台服务：
```bash
kill "$(cat logs/backend_dev.pid)"
```
