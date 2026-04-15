# Survey 后端迭代路线

## V1.1（优先）
- 增加 `POST /api/cases/{id}/run-kmer`
- 增加 `POST /api/cases/{id}/run-nt`
- 增加 `POST /api/cases/{id}/run-survey`
- 增加 `POST /api/cases/{id}/run-all`
- 将现有 `kmer_judge.py / nt_judge.py / survey_judge_single.py` 服务化接入

## V1.2
- 增加 `GET /api/stats/overview`
- 增加批量导入样本路径接口
- 增加错误审计字段（失败原因、trace 简要）

## V1.3
- 引入 Alembic 管理迁移
- 增加鉴权（内网 token）
- 增加异步任务队列（批量判定场景）

