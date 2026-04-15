# Survey 后端设计（V1）

## 目标
- 基于 `SQLite + FastAPI` 实现可用后端，替代 JSON 文件存储。
- 支撑前端第一版核心页面：列表、详情、手动创建、JSON 导入。
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

## V1 已实现接口
- `GET /health`
- `POST /api/cases` 创建样本（可携带 kmer/nt/survey）
- `POST /api/cases/import-survey-json` 导入完整 JSON 结果
- `GET /api/cases` 列表查询（`limit/offset/target_species/final_level/should_transfer/status`）
- `GET /api/cases/{case_id}` 样本详情

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
conda run -n zhurui_agent python -m uvicorn backend.app.main:app --reload --port 8000
```

