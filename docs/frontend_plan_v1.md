# Survey 前端开发计划与分工文档（Vue3 / V1）

## 1. 项目目标
- 构建 Survey 前端工作台，支持按路径触发 `kmer / nt / survey` 判定。
- 提供左侧样本列表 + 右侧详情看板的高效浏览与操作体验。
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
- 后端服务可访问（当前默认地址：`http://192.168.20.24:8001`）

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
默认后端地址已在代码中设置为：`http://192.168.20.24:8001`

如需覆盖，可在 `frontend/.env.local` 配置：
```bash
VITE_API_BASE_URL=http://192.168.20.24:8001
```

### 3.5 内网访问与 404 排障（2026-04-16）
现象：
- 本机 `npm run dev` 正常启动，日志显示 `Local: http://localhost:5173/`
- 内网访问 `https://192.168.20.24:5173/cases` 返回 404（或不可达）

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
- `http://192.168.20.24:5173/cases`

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
- `/cases` -> Survey 工作台（单页双栏）

### 4.2 工作台布局
1. 顶部说明区（标题 + 功能说明）
2. 路径执行区（RunPanel）
- 输入：`sample_dir`
- 可选输入：`sample_code`
- 按钮：`仅检查文件`、`执行 kmer`、`执行 nt`、`执行 survey`
- 反馈：展示 `file_check` 关键状态
3. 主体双栏区
- 左侧：已判定样本列表（CaseList）
- 右侧：详情看板（CaseBoard）

## 5. 代码结构（核心）
- `src/views/SurveyWorkbenchView.vue`：工作台容器
- `src/components/workbench/RunPanel.vue`：路径执行区
- `src/components/workbench/CaseList.vue`：列表区
- `src/components/workbench/CaseBoard.vue`：详情看板
- `src/stores/cases.ts`：核心状态与业务动作
- `src/api/http.ts`：axios 实例与统一异常处理
- `src/api/cases.ts`：cases 相关 API 封装
- `src/types/case.ts`：类型定义

### 5.1 `SurveyWorkbenchView.vue`（页面编排层）
- 职责：只做页面布局与组件装配，不承载业务逻辑。
- 组成：
  - 顶部说明区（标题、功能引导）
  - `RunPanel`（触发执行）
  - `CaseList`（列表筛选与选择）
  - `el-drawer + CaseBoard`（详情抽屉）
- 与 Store 关系：
  - 仅依赖 `boardDrawerVisible` 控制抽屉显隐。
  - 关闭抽屉时调用 `closeBoardDrawer()`，不直接修改业务数据。

### 5.2 `RunPanel.vue`（执行入口层）
- 职责：收集 `sample_dir / sample_code`，触发后端执行或文件检查。
- 输入：
  - `sample_dir`（必填）
  - `sample_code`（可选）
- 动作映射：
  - `仅检查文件` -> `store.checkFiles(sampleDir)`
  - `执行 kmer/nt/survey` -> `store.runByPath(type, sampleDir, sampleCode)`
- 交互规范：
  - 空路径先本地拦截，避免无效请求。
  - 按钮通过 `checkingFiles / runningType` 做防重入。
  - 展示 `file_check`（`kmer_complete / nt_complete / complete / missing`）供用户快速判断是否可执行。

### 5.3 `CaseList.vue`（列表与筛选层）
- 职责：展示样本摘要列表，提供筛选、分页、行选择。
- 关键状态来源：
  - 列表数据：`store.list`
  - 加载态：`store.loadingList`
  - 总数：`store.total`
  - 筛选参数：`store.filters`
- 关键行为：
  - 组件挂载时执行 `loadList()` 拉取第一页。
  - 点击行触发 `store.selectCase(row.id)`，并联动打开详情抽屉。
  - 查询时重置 `offset=0`；重置时恢复默认筛选。
- 视觉语义：
  - `final_level` 与 `status` 使用 Tag 颜色映射常量统一管理。
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
- 职责：统一管理列表、详情、执行、筛选、抽屉等前端业务状态。
- 核心动作：
  - `fetchList`：按筛选参数查询列表
  - `selectCase`：加载详情并打开抽屉
  - `runByPath`：执行后刷新列表并自动定位到新样本
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
  - `RunResponse`：执行接口返回
  - `FileCheckResponse`：文件检查返回
- 价值：
  - 在开发期尽早暴露字段缺失、类型不匹配和接口变更风险。

## 6. 状态与数据流

### 6.1 Store 状态
- 列表态：`list / total / loadingList`
- 详情态：`selectedCaseId / selectedCase / loadingDetail`
- 执行态：`runningType / checkingFiles`
- 筛选态：`filters(limit/offset/target_species/final_level/should_transfer/status)`
- 文件检查结果：`fileCheckResult`

### 6.2 关键动作
- `fetchList()`：查询列表
- `selectCase(caseId)`：查询详情
- `checkFiles(sampleDir)`：仅检查路径文件
- `runByPath(type, sampleDir, sampleCode)`：执行 `kmer / nt / survey`
- `rerunSelectedCase()`：重跑 survey（confirm=true）
- `removeSelectedCase()`：删除当前样本

## 7. 接口映射
- `GET /api/cases`
- `GET /api/cases/{case_id}`
- `POST /api/cases/check-by-path`
- `POST /api/cases/run-kmer`
- `POST /api/cases/run-nt`
- `POST /api/cases/run-survey`
- `POST /api/cases/rerun-survey`
- `DELETE /api/cases/{case_id}`

## 8. 已实现交互规范
- 所有执行按钮具备 loading 防重入
- `executed=false` 按业务提示处理，不当作请求异常
- HTTP `409/404/500` 全局错误提示
- 重跑 / 删除均使用二次确认弹窗

## 9. 后续开发计划（可直接分工）

### 9.1 A 组：列表体验增强
目标：提升筛选效率与风险识别速度
- 增加状态语义色（Tag）
- `final_level` 色彩规则：
  - `正常`：绿色
  - `轻度污染`：橙色
  - `重度污染`：红色
  - `fail`：灰红
- `status` 色彩规则：
  - `judged`：主色强调
  - 其他状态：中性色
- 列表支持当前选中行高亮保持
- 分页体验优化（切页后保留筛选条件）

交付物：
- 列表列渲染优化
- 颜色映射常量文件（避免魔法字符串）
- 简要 UI 验收截图

### 9.2 B 组：看板详情增强
目标：提升结果解释性，便于实验人员比对
- 在 `Result Metrics` 模块中新增 `raw / adjusted` 表格化展示
- 展示字段采用“键值双列表”或“同字段对比列”
- 对数值字段增加格式化（空值统一 `-`）
- `remark` 支持折叠/展开

交付物：
- `CaseBoard` 的 result_metrics 对比卡片
- 公共格式化函数（数字/空值/布尔）
- 对比展示样例截图

### 9.3 C 组：质量与联调保障
目标：提升接口稳定性与问题定位效率
- 增加请求日志开关（开发环境）
- 完善错误提示文案（区分网络错误与业务错误）
- 增加联调自检清单页面（或文档）
- 补充 E2E 冒烟流程：
  1. check-by-path
  2. run-survey
  3. 列表刷新
  4. 看板展示
  5. rerun-survey

交付物：
- 联调记录文档
- 关键流程测试记录

## 10. 验收清单
- 可按路径执行 `kmer / nt / survey`
- `survey` 成功后可在列表出现并在右侧看板展示详情
- 列表颜色语义与状态标识清晰
- `raw / adjusted` 对比表可读性满足使用需求
- `409/404/500` 提示准确
- 重跑与删除流程稳定可用
