# Survey 前后端联调自检清单（V1）

## 1. 环境准备
- 前端：`cd frontend && npm run dev`
- 后端：确认 `http://10.11.0.6:8001` 可访问
- 可选开关：`VITE_ENABLE_HTTP_LOG=true`（开发环境默认开启，设置为 `false` 可关闭）

## 2. 接口连通性自检
- 打开 `http://localhost:5173/cases`
- 在浏览器开发者工具确认请求成功：
  - `GET /api/cases`
  - 点击任一样本后 `GET /api/cases/{case_id}`
- 异常提示检查：
  - 断网/服务不可达时提示“网络连接失败”
  - 超时时提示“请求超时”
  - 409/404/500 时有对应业务提示

## 3. E2E 冒烟流程（核心 5 步）
1. 执行 `check-by-path`：输入 `sample_dir`，点击“仅检查文件”
2. 执行 `run-survey`：点击“执行 survey”
3. 列表刷新：确认新样本或更新样本在列表出现
4. 看板展示：点击样本，抽屉打开并展示详情，`raw/adjusted` 对比表可见
5. `rerun-survey`：在看板点击“重跑 survey”并确认成功

## 4. UI 行为检查
- 初始进入页面不显示详情看板
- 点击样本后才打开抽屉详情
- `final_level/status` 语义色正确
- 当前选中行高亮保持（翻页后保留筛选条件）
- `remark` 支持展开/收起

## 5. 联调记录模板
- 联调日期：
- 前端分支/提交：
- 后端分支/提交：
- 测试样本路径：
- 冒烟流程结果：
  - Step1 check-by-path：
  - Step2 run-survey：
  - Step3 列表刷新：
  - Step4 看板展示：
  - Step5 rerun-survey：
- 问题清单与结论：
