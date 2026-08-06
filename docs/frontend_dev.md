# Survey 前端开发计划与分工文档（Vue3 / V1）

## 1. 项目目标
- 构建 Survey 前端工作台，提供样本统计概览、列表浏览、模糊检索与人工审核入口。
- 提供样本列表 + 详情看板（抽屉形式）的高效浏览与操作体验。
- V1 重点保证功能完整、稳定联调、可快速迭代，不追求复杂视觉效果。

## 2. 技术基线
- 工程目录：`frontend/`
- 技术栈：`Vue3 + TypeScript + Vite`
- 状态管理：`Pinia`
- 请求层：`Axios`（统一处理 409/404/500）
- UI：`Element Plus`

## 3. 启动与运行说明

### 3.1 前置环境
- Node.js >= 20
- 后端服务可访问（当前默认地址：`http://10.11.0.6:8001`）

### 3.2 安装与启动
```bash
cd frontend
npm install
npm run dev
```

### 3.3 构建与预览
```bash
npm run build
npm run preview
```

### 3.4 环境变量
默认后端地址已在代码中设置为：`http://10.11.0.6:8001`

如需覆盖，可在 `frontend/.env.local` 配置：
```bash
VITE_API_BASE_URL=http://10.11.0.6:8001
```

### 3.5 内网访问与 404 排障（2026-04-16）
现象：
- 本机 `npm run dev` 正常启动，日志显示 `Local: http://localhost:5173/`
- 内网访问 `https://10.11.0.6:5173/cases` 返回 404（或不可达）

排查结论：
- 当前 `Vite` 默认仅监听本机回环地址（如 `[::1]:5173`），不会对内网网卡开放。
- 当前 dev server 协议是 `HTTP`，不是 `HTTPS`；直接用 `https://` 访问会协议不匹配。
- 该问题优先是“监听地址 + 协议”配置问题，不是前端路由 `createWebHistory()` 本身问题。
- 防火墙问题通常表现为超时/拒绝连接，不是典型 404。

标准启动方式（内网调试）：
```bash
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

后台运行方式（内网调试，关闭 VSCode 仍保持运行）：
```bash
mkdir -p logs
setsid bash -lc 'cd /data/work/zhurui/survey_rec/frontend && exec npm run dev -- --host 0.0.0.0 --port 5173' \
  > /data/work/zhurui/survey_rec/logs/frontend_dev.log 2>&1 < /dev/null &
echo $! > /data/work/zhurui/survey_rec/logs/frontend_dev.pid
```

停止后台服务：
```bash
kill "$(cat logs/frontend_dev.pid)"
```

检查是否已脱离终端（`TTY` 应为 `?`）：
```bash
ps -fp "$(cat logs/frontend_dev.pid)"
```

正确访问地址：
- `http://10.11.0.6:5173/cases`

推荐固化到 `vite.config.ts`（避免每次手工加参数）：
```ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
  },
})
```

如必须使用 `HTTPS`：
- 方案 1：在 Vite `server.https` 配置证书；
- 方案 2：通过 Nginx/Caddy 反向代理并做 TLS 终止。

## 4. 当前页面原型结构（已落地）

### 4.1 路由
- `/` -> 重定向到 `/cases`
- `/cases` -> Survey 工作台（统计概览 + 列表 + 详情抽屉）
- `/review-prototype` -> 人工审核页

### 4.2 工作台布局
1. 顶部说明区（标题 + 功能说明 + 「进入人工审核」入口）
2. 统计概览区（CaseStatsBar）
- 卡片：样本总数 / 正常 / 重度污染 / 待人工复核 / 已审核占比
- 数据来源：`GET /api/cases/stats`
3. 样本列表区（CaseList）
- 筛选：`stage_code`（模糊）、`target_species`（模糊）、`final_level`、审核状态、审核结论
- 筛选项变更即自动触发检索（无独立查询/重置按钮）
- 点击行以抽屉形式打开详情看板（CaseBoard）

## 5. 代码结构（核心）
- `src/views/SurveyWorkbenchView.vue`：工作台容器
- `src/components/workbench/CaseStatsBar.vue`：统计概览区
- `src/components/workbench/CaseList.vue`：列表区
- `src/components/workbench/CaseBoard.vue`：详情看板
- `src/stores/cases.ts`：核心状态与业务动作
- `src/api/http.ts`：axios 实例与统一异常处理
- `src/api/cases.ts`：cases 相关 API 封装
- `src/types/case.ts`：类型定义

### 5.1 `SurveyWorkbenchView.vue`（页面编排层）
- 职责：只做页面布局与组件装配，不承载业务逻辑。
- 组成：
  - 顶部说明区（标题、功能引导、「进入人工审核」入口）
  - `CaseStatsBar`（统计概览）
  - `CaseList`（列表筛选与选择）
  - `el-drawer + CaseBoard`（详情抽屉）
- 与 Store 关系：
  - 仅依赖 `boardDrawerVisible` 控制抽屉显隐。
  - 关闭抽屉时调用 `closeBoardDrawer()`，不直接修改业务数据。

### 5.2 `CaseStatsBar.vue`（统计概览层）
- 职责：展示全库样本统计概览卡片。
- 数据来源：`store.stats`（由 `store.fetchStats()` 拉取，随 `fetchList` 自动刷新）。
- 展示卡片：
  - 样本总数（`total`）
  - 正常 / 重度污染 / 待人工复核（`by_final_level`）
  - 已审核 / 总数（`reviewed / total`）
- 交互规范：
  - 加载中用 `loadingStats` 显示 loading。
  - 数据未就绪时展示占位符 `-`。

### 5.3 `CaseList.vue`（列表与筛选层）
- 职责：展示样本摘要列表，提供筛选、分页、行选择。
- 关键状态来源：
  - 列表数据：`store.list`
  - 加载态：`store.loadingList`
  - 总数：`store.total`
  - 筛选参数：`store.filters`
- 展示列：
  - `ID / stage_code / target_species / final_level / 最终决策 / 更新时间`（不再展示 `sample_code`）。
- 筛选项（变更即自动触发检索，无独立查询/重置按钮）：
  - `stage_code`（模糊）、`target_species`（模糊）文本框：失焦 / 回车 / 清空时触发。
  - `final_level`、审核状态、审核结论下拉：变更时触发。
- 关键行为：
  - 组件挂载时执行 `loadList()` 拉取第一页。
  - 点击行触发 `store.selectCase(row.id)`，并联动打开详情抽屉。
  - 触发检索时重置 `offset=0`。
- 视觉语义：
  - `final_level` 使用 Tag 颜色映射常量统一管理。
  - 当前选中行使用高亮类名 `case-list__row--active`。

### 5.4 `CaseBoard.vue`（详情展示与高风险操作层）
- 职责：展示完整样本详情，并承载“重跑/删除”高风险动作。
- 内容分区：
  - 摘要信息（主字段概览）
  - Kmer 结果
  - NT 结果
  - Survey + Result Metrics（含 `raw/adjusted` 对比表）
- 关键行为：
  - 监听 `selectedCaseId`，切换样本时重置 remark 展开态。
  - “重跑 survey”“删除”均要求确认弹窗（二次确认）。

### 5.5 `stores/cases.ts`（业务中枢）
- 职责：统一管理列表、统计、详情、筛选、抽屉等前端业务状态。
- 核心动作：
  - `fetchList`：按筛选参数查询列表，并顺带刷新统计（`fetchStats`）
  - `fetchStats`：拉取样本统计概览
  - `selectCase`：加载详情并打开抽屉
  - `rerunSelectedCase / removeSelectedCase`：高风险动作封装
- 设计原则：
  - 组件尽量“薄”，业务副作用集中在 Store，便于联调和排障。

### 5.6 `api/http.ts`（HTTP 基础设施层）
- 职责：封装 axios 实例、超时、开发日志、全局异常提示。
- 统一错误语义：
  - 网络错误：提示后端不可达
  - `409`：重复路径冲突
  - `404`：记录不存在
  - `500`：服务端异常

### 5.7 `api/cases.ts`（接口适配层）
- 职责：提供 cases 领域 API 函数，隔离后端响应细节。
- 约定：
  - 前端内部统一消费 `CaseListResponse`（`items/total/limit/offset`）。
  - `getCases` 已兼容两类后端返回：
    - 直接数组：`CaseSummary[]`
    - 分页对象：`{ items, total, limit, offset }`
  - 通过适配层归一化，避免组件层直接处理兼容逻辑。

### 5.8 `types/case.ts`（领域类型层）
- 职责：集中维护 Case 相关类型，作为组件、Store、API 的契约。
- 重点类型：
  - `CaseSummary`：列表字段集合
  - `CaseDetail`：详情字段集合
  - `CaseStats`：统计概览返回
  - `RunResponse`：重跑接口返回
- 价值：
  - 在开发期尽早暴露字段缺失、类型不匹配和接口变更风险。

## 6. 状态与数据流

### 6.1 Store 状态
- 列表态：`list / total / loadingList`
- 统计态：`stats / loadingStats`
- 详情态：`selectedCaseId / selectedCase / loadingDetail`
- 执行态：`runningType`（仅用于重跑 survey）
- 筛选态：`filters(limit/offset/stage_code/target_species/final_level/review_status/review_final_decision/...)`

### 6.2 关键动作
- `fetchList()`：查询列表（并刷新统计）
- `fetchStats()`：查询样本统计概览
- `selectCase(caseId)`：查询详情
- `rerunSelectedCase()`：重跑 survey（confirm=true）
- `removeSelectedCase()`：删除当前样本

## 7. 接口映射
- `GET /api/cases`（列表）
- `GET /api/cases/stats`（统计概览）
- `GET /api/cases/{case_id}`（详情）
- `GET /api/cases/{case_id}/judge-report`（判定报告）
- `GET /api/cases/{case_id}/report-html`（HTML 报告）
- `GET /api/cases/{case_id}/archive`（原始压缩包）
- `GET /api/cases/{case_id}/manual-review`（审核记录）
- `POST /api/cases/{case_id}/manual-review`（提交审核）
- `POST /api/cases/rerun-survey`（重跑）
- `DELETE /api/cases/{case_id}`（删除）

> 说明：`run-kmer / run-nt / run-survey / check-by-path / run-by-path / run-by-archive` 等执行类接口仍由后端提供，但当前前端工作台不再内置按路径执行入口（样本入库主要由外部 `run-by-archive` 上传触发）。

## 8. 已实现交互规范
- 列表筛选项变更（失焦 / 回车 / 清空 / 下拉变更）自动触发检索，无独立查询/重置按钮
- 重跑按钮具备 loading 防重入
- HTTP `409/404/500` 全局错误提示
- 重跑 / 删除均使用二次确认弹窗
