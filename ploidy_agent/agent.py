import json
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy

from models.models import get_qwen_plus_llm
from ploidy_agent.schemas import PloidyCorrectionResult
from ploidy_agent.tools import web_search, web_search_summary


PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "system_prompt.txt"


def _load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_ploidy_agent():
    llm = get_qwen_plus_llm()
    return create_agent(
        model=llm,
        tools=[web_search_summary, web_search],
        system_prompt=_load_system_prompt(),
        response_format=ToolStrategy(PloidyCorrectionResult),
    )


def _build_user_payload(species_name: str, kmer_result: dict[str, Any], script_text: str | None) -> str:
    payload = {
        "species_name": species_name,
        "script_result_dict": kmer_result,
        "script_text": script_text or "",
        "task": "请基于脚本结果和联网证据输出最终倍性纠错结论。",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def run_ploidy_correction(
    species_name: str,
    kmer_result: dict[str, Any],
    script_text: str | None = None,
) -> PloidyCorrectionResult:
    agent = build_ploidy_agent()
    user_content = _build_user_payload(species_name, kmer_result, script_text)
    result = agent.invoke({"messages": [{"role": "user", "content": user_content}]})
    return result["structured_response"]

