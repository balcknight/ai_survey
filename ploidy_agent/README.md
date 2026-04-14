# 倍性纠错 Agent（LangChain + 结构化输出）

## 目标
- 输入：`物种名` + `main_dual` 输出字典（可选附带脚本文本）。
- 输出：结构化 JSON（最终倍性、是否纠正、置信度、判断依据、来源链接等）。

## 目录结构
- `prompts/system_prompt.txt`：系统提示词
- `tools/web_tools.py`：联网工具
- `schemas.py`：Pydantic 结构化输出 schema
- `agent.py`：`create_agent + ToolStrategy` 核心逻辑
- `pipeline.py`：对接 `main_dual` 的便捷封装

## 命令行调用
```bash
conda run -n zhurui_agent python run_ploidy_agent.py \
  --species 锤头双髻鲨 \
  --kmer-json data/tmp_kmer_result.json
```

## 代码调用
```python
from ploidy_agent.pipeline import correct_from_main_dual_result

res = correct_from_main_dual_result(
    species_name="锤头双髻鲨",
    main_dual_result=kmer_res,  # 来自 kmer_judge.main_dual
    script_text=raw_log_text,   # 可选
)
print(res["final_ploidy"], res["confidence"])
```

