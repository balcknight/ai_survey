# Survey 后端迭代路线

## V1.1（优先）
- 对齐 `survey_judge_single.py` 输出结构（已完成，2026-04-16）
  - 新增 `result_metrics` 入库与详情返回
  - `check-by-path/run-survey/run-by-path/rerun-survey` 改为检查 5 文件（含 `*.Result.xls`）
- 增加 `POST /api/cases/{id}/run-all`
- 支持“基于已有 case_id 的单步/全流程执行”，减少重复建 case

## V1.2
- 增加 `GET /api/stats/overview`
- 增加批量导入样本路径接口
- 增加错误审计字段（失败原因、trace 简要）

## V1.3
- 引入 Alembic 管理迁移
- 增加鉴权（内网 token）
- 增加异步任务队列（批量判定场景）
