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
