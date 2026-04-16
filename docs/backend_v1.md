# Survey 后端设计（V1）

## 目标
- 基于 `SQLite + FastAPI` 实现可用后端，替代 JSON 文件存储。
- 支撑前端第一版核心页面：列表、详情、路径触发判定。
- `survey_dev.md` 继续只维护判定规则，本文件维护后端实现方案。

## 数据模型

### 1. survey_cases（主表）
- `id` 主键
- `sample_code` 样本编号
- `target_species` 目标物种
- `source_path` 来源路径
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
- `DELETE /api/cases/{case_id}` 删除样本（删除后可重新发起同路径判定）
- `POST /api/cases/check-by-path` 只检查样本目录文件是否齐全（不执行判定）
- `POST /api/cases/run-kmer` 输入样本目录，执行 kmer 判定并入库
- `POST /api/cases/run-nt` 输入样本目录，执行 NT 判定并入库
- `POST /api/cases/run-survey` 输入样本目录，执行 `survey_judge_single.py` 同款完整判定（kmer+nt+survey+result）并入库
- `POST /api/cases/rerun-survey` 显式确认后重跑并覆盖该路径的已有记录
- `POST /api/cases/run-by-path` 输入样本目录，自动检查 5 个必需文件；若齐全则执行完整 survey 判定并入库

## 通用测试前缀
```bash
BASE_URL="http://127.0.0.1:8001"
SAMPLE_DIR="/data/work/zhurui/survey_rec/data/shenshaoqi_data/survey1/X101SC2507/X101SC25070200-Z01-J002/FDSW250019884-2a_百花山C-嫩茎_1管"

SAMPLE_DIR1="data/shenshaoqi_data_v2/1"


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
- `sample_code`：样本编号（可选）
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
- `sample_code`：样本编号（可选）
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

## 执行类接口返回说明（run-kmer/run-nt/run-survey/run-by-path/rerun-survey）
- `run-kmer` 依赖 `file_check.kmer_complete=true`。
- `run-nt` 依赖 `file_check.nt_complete=true`。
- `run-survey/run-by-path` 依赖 `file_check.complete=true`（即同时具备 `*.SpeFreq.cut/*.NumFreq.cut/all.ntcls.xls/all.ntspe.xls/*.Result.xls`）。
- 条件不满足时：`executed=false`，仅返回缺失项。
- `run-kmer/run-nt/run-survey/run-by-path` 都会先检查 `sample_dir` 是否已存在历史记录；若已存在，返回 `409`。
- `rerun-survey` 用于显式覆盖重跑：`confirm=true` 且路径已存在时才执行。
- `executed=true`：该接口对应步骤执行成功并已入库。
- `case_id`：数据库中的样本主键，可用于后续 `GET /api/cases/{case_id}` 查询。
- `run-survey/rerun-survey/run-by-path` 的判定入口统一与 `survey_judge_single.py` 对齐：目标物种由 `all.ntcls.xls` 首行 `Sample name` 推导，并同时用于 kmer 与 nt。

## 删除接口
### curl 示例
```bash
curl -X DELETE "$BASE_URL/api/cases/12"
```

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
      "is_normal": true
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
conda run -n zhurui_agent python -m uvicorn backend.app.main:app --reload --port 8001
```
