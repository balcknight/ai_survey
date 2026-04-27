from pathlib import Path
from typing import List
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openai import OpenAI
from pydantic import BaseModel, Field

from models.models import get_qwen35_plus_llm


class IntentRoute(BaseModel):
    """意图路由模型"""

    intent: str = Field(
        ...,
        description="用户意图：modify_section（修改部分）、generate_paper（生成文章）、chat（常规对话）、other（其他）",
    )
    target_section: List[str] = Field(
        default_factory=list,
        description=(
            "目标修改的章节列表：title, introduction, methods, results, "
            "discussion, abstract, references，如果不是修改部分则为空列表。"
            "如果用户要求同时修改多个章节，返回包含所有章节的列表"
        ),
    )
    reasoning: List[str] = Field(
        default_factory=list,
        description=(
            "判断理由列表，每个理由对应一个章节。"
            "如果只有一个章节，列表包含一个元素；如果有多个章节，列表包含对应数量的理由"
        ),
    )


TEST_QUERIES = [
    "请帮我润色一下摘要部分，让语言更学术一些。",
    "把引言和讨论都改一下，引言补充研究背景，讨论里增加结果意义分析。",
    "帮我直接生成一篇完整论文草稿。",
    "你好，什么是PCA分析？",
]


def test_langchain_structured_output():
    print("=== LangChain with_structured_output(function_calling) ===")
    llm = get_qwen35_plus_llm()
    structured_llm = llm.with_structured_output(IntentRoute, method="function_calling")

    for i, query in enumerate(TEST_QUERIES, 1):
        print(f"\n----- CASE {i} -----")
        print("QUERY:", query)
        try:
            result = structured_llm.invoke(query)
            print("RESULT:", result.model_dump())
        except Exception as exc:
            print("ERROR:", type(exc).__name__, str(exc))


def test_openai_tools():
    print("\n=== OpenAI compatible tools ===")
    llm = get_qwen35_plus_llm()
    client = OpenAI(api_key=llm.openai_api_key.get_secret_value(), base_url=llm.openai_api_base)

    tools = [
        {
            "type": "function",
            "function": {
                "name": "route_intent",
                "description": "将用户请求路由到结构化意图",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "intent": {"type": "string"},
                        "target_section": {"type": "array", "items": {"type": "string"}},
                        "reasoning": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["intent", "target_section", "reasoning"],
                },
            },
        }
    ]

    for i, query in enumerate(TEST_QUERIES, 1):
        print(f"\n----- CASE {i} -----")
        print("QUERY:", query)
        response = client.chat.completions.create(
            model="qwen3.5-plus",
            extra_body={"enable_thinking": False},
            messages=[
                {
                    "role": "system",
                    "content": "你是意图路由器。必须调用工具 route_intent 返回结构化结果，不要输出普通文本。",
                },
                {"role": "user", "content": query},
            ],
            tools=tools,
            tool_choice="auto",
        )
        message = response.choices[0].message
        if message.tool_calls:
            print("TOOL_ARGS:", message.tool_calls[0].function.arguments)
        else:
            print("CONTENT:", message.content)


if __name__ == "__main__":
    test_langchain_structured_output()
    test_openai_tools()
