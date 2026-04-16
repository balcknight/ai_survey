# AGENTS.md

## 项目规则

- 总是以中文进行回复.
- 项目环境是 `zhurui_agent`。
- 前端代码路径：`frontend/`（主要源码在 `frontend/src/`）。
- 后端代码路径：`backend/`（FastAPI 入口：`backend/app/main.py`）。
- 执行 Python 命令优先使用：`conda run -n zhurui_agent python ...`。
- 若需要进入交互式环境再执行：先 `source /data/home/zhurui/.bashrc`，再 `conda activate zhurui_agent`。
- `survey_judge_single.py` 的单样本运行约定：只设置 `sample_dir`，脚本会自动定位 4 个输入文件（`*.SpeFreq.cut`、`*.NumFreq.cut`、`all.ntcls.xls`、`all.ntspe.xls`）。
- 自动定位规则：仅在提供的 `sample_dir` 内查找（含子目录），不向父目录或兄弟目录扩展，避免误匹配到其他样本。
- 提醒：kmer 和 nt 都需要物种名参与 LLM 处理；默认从 `all.ntcls.xls` 第一行 `Sample name` 读取，并同时传给 kmer 与 nt 流程。
