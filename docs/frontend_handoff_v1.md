# Survey 前端设计交接文档（Vue3 / V1）

## 1. 目标与范围
- 本文档用于交付前端工程师完成 Survey 系统 V1 设计与实现。
- V1 页面范围：样本列表页、样本详情页、按路径执行判定（含检查文件）、重跑、删除。
- 后端基线：`FastAPI + SQLite`，接口以 `/api/cases` 为主。

## 2. 业务对象与关键概念
- `case`：一个样本判定记录，主键 `id`。
- `status`：流程状态，`created | kmer_done | nt_done | judged | failed`。
- `final_level`：综合结论，常见值 `正常 | 轻度污染 | 重度污染 | fail`。
- `should_transfer`：是否建议流转，`是 | 否`。
- `result_metrics`：由 `*.Result.xls` 提取并按倍型修正后的指标信息。

## 3. 页面与路由建议
- `/cases`
  - 样本列表页（默认入口）。
  - 顶部提供筛选、路径执行入口。
- `/cases/:id`
  - 样本详情页。
  - 展示 kmer / nt / survey / result_metrics 四块结果。

## 4. 视觉与交互设计建议
- 视觉方向：专业实验室工作台风格，浅底高对比，不做花哨渐变背景。
- 信息密度：列表偏高密度（便于批量查看），详情偏分块卡片（便于阅读结论）。
- 推荐状态色：
  - `正常`：绿色
  - `轻度污染`：橙色
  - `重度污染`：红色
  - `fail`：深红或灰红
  - `judged`：主色强调，其余流程态用中性色
- 动效：仅保留必要反馈（加载骨架、按钮 loading、请求成功/失败 toast）。

## 5. 列表页设计（/cases）
### 5.1 筛选区
- `target_species`（输入框）
- `final_level`（下拉）
- `should_transfer`（下拉）
- `status`（下拉）
- 分页参数：`limit`、`offset`

### 5.2 表格字段
- `id`
- `sample_code`
- `target_species`
- `status`
- `kmer_pattern` / `kmer_is_normal`
- `nt_score` / `nt_level`
- `final_level` / `should_transfer`
- `updated_at`
- 操作列：`查看详情`、`删除`

### 5.3 顶部主操作
- `按路径执行完整判定`（主按钮，调用 `POST /api/cases/run-survey`）
- `仅检查文件`（次按钮，调用 `POST /api/cases/check-by-path`）

## 6. 详情页设计（/cases/:id）
### 6.1 顶部摘要
- `id / sample_code / target_species`
- `status / final_level / should_transfer`
- `remark / source_path / created_at / updated_at`

### 6.2 内容分区
- `Kmer 结果`
  - `pattern / is_normal / detail / warnings`
  - `spe_peaks` 与 `num_peaks`（可做简单峰值表格；图表可放 V1.1）
- `NT 结果`
  - `nt_score / nt_level`
  - `ntcls_score / ntspe_score`
  - 三个 pass 布尔值与 detail 文本
- `综合结果`
  - `final_level / should_transfer / remark / rule_version`
- `Result 指标（result_metrics）`
  - `ploidy_pattern / ploidy_multiplier / remark`
  - `raw` 与 `adjusted` 对比展示（建议双列表格）

### 6.3 详情页操作
- `重跑`：`POST /api/cases/rerun-survey`，需二次确认并传 `confirm=true`
- `删除`：`DELETE /api/cases/{id}`

## 7. 接口契约（前端重点）
### 7.1 列表
- `GET /api/cases`
- Query：`limit offset target_species final_level should_transfer status`
- 返回：`CaseSummaryOut[]`

### 7.2 详情
- `GET /api/cases/{case_id}`
- 返回：`CaseDetailOut`（包含 `kmer_result/nt_result/survey_result/result_metrics`）

### 7.3 检查文件
- `POST /api/cases/check-by-path`
- Body:
```json
{
  "sample_dir": "string"
}
```
- 返回含 `file_check`：
  - `spe_path/num_path/ntcls_path/ntspe_path/result_path`
  - `missing[]`
  - `kmer_complete/nt_complete/complete`

### 7.4 执行完整判定（主流程）
- `POST /api/cases/run-survey`
- Body:
```json
{
  "sample_dir": "string",
  "sample_code": "string | null",
  "case_id": "number | null",
  "verbose": false
}
```
- 成功返回：`executed=true`，并附 `case_id + case_detail`
- 文件不全返回：`executed=false`（HTTP 200）
- 路径重复返回：HTTP `409`

### 7.5 重跑
- `POST /api/cases/rerun-survey`
- Body 需包含 `"confirm": true`
- 路径不存在历史记录返回：HTTP `404`

### 7.6 删除
- `DELETE /api/cases/{case_id}`

## 8. 前端 TypeScript 类型建议
```ts
export interface PeaksData {
  depths: number[];
  freqs: number[];
}

export interface CaseSummary {
  id: number;
  sample_code: string | null;
  target_species: string;
  status: "created" | "kmer_done" | "nt_done" | "judged" | "failed";
  kmer_pattern: string | null;
  kmer_is_normal: boolean | null;
  nt_score: number | null;
  nt_level: string | null;
  final_level: string | null;
  should_transfer: "是" | "否" | null;
  updated_at: string;
}

export interface CaseDetail extends Omit<CaseSummary, "kmer_pattern" | "kmer_is_normal" | "nt_score" | "nt_level"> {
  source_path: string | null;
  remark: string | null;
  created_at: string;
  kmer_result: {
    pattern: string | null;
    is_normal: boolean | null;
    detail: string | null;
    spe_peaks: PeaksData | null;
    num_peaks: PeaksData | null;
    warnings: string[];
    analysis_ploidy: Record<string, unknown> | null;
  } | null;
  nt_result: {
    nt_score: number | null;
    nt_level: string | null;
    ntcls_score: number | null;
    ntspe_score: number | null;
    ntcls_detail: string | null;
    ntspe_detail: string | null;
    ntcls_top1_pass: boolean | null;
    ntcls_contamination_pass: boolean | null;
    ntspe_contamination_pass: boolean | null;
  } | null;
  survey_result: {
    final_level: string | null;
    should_transfer: string | null;
    remark: string | null;
    rule_version: string | null;
  } | null;
  result_metrics: {
    result_path: string | null;
    ploidy_pattern: string | null;
    ploidy_multiplier: number | null;
    raw: Record<string, unknown> | null;
    adjusted: Record<string, unknown> | null;
    remark: string | null;
  } | null;
}
```

## 9. 交互状态与异常处理规范
- 所有执行按钮需具备 `loading`，防重复提交。
- 对 `executed=false` 的响应，按业务提示处理，不当作请求异常。
- 对 HTTP `409/404/400/500`，统一错误弹窗，展示后端 `detail`。
- 删除与重跑均需要二次确认弹窗。
- `rerun-survey` 文案需明确“覆盖原记录”。

## 10. 推荐实现栈（Vue3）
- `Vue3 + TypeScript + Vite`
- `Vue Router`
- `Pinia`（管理筛选条件、列表缓存、详情缓存）
- `Axios`（统一拦截器与错误处理）
- UI 组件库按团队习惯（Element Plus/Naive UI/Ant Design Vue 均可）

## 11. 联调验收清单
- 列表筛选、分页可用。
- `check-by-path` 能正确展示 5 文件检查结果（含 `*.Result.xls`）。
- `run-survey` 成功后能跳详情并看到 `result_metrics`。
- `rerun-survey(confirm=true)` 能覆盖原记录并刷新详情。
- 删除后列表即时移除。
- 409（路径重复）提示清晰。

