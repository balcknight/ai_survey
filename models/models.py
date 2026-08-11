from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI, ChatOpenAI
from openai import OpenAI
from langchain.chat_models import init_chat_model

def get_qwen_plus_llm():
    llm = ChatOpenAI(
        temperature=0,
        model="qwen3-vl-plus",
        openai_api_key="sk-b200ea2f10dc484ba7e979809b8e0c37",
        openai_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    return llm

def get_qwen35_plus_llm():
    llm = ChatOpenAI(
        temperature=0,
        model="qwen3.5-plus",
        openai_api_key="sk-b200ea2f10dc484ba7e979809b8e0c37",
        openai_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        extra_body={"enable_thinking": False}
    )
    return llm

def get_qwen35_plus_client():
    """获取支持思考内容展示的Qwen3.5-Plus客户端"""
    client = OpenAI(
        api_key="sk-b200ea2f10dc484ba7e979809b8e0c37",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    return client

def stream_with_thinking(client, model, question):
    """流式输出，展示思考过程和回答"""
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": question}],
        stream=True,
        extra_body={"enable_thinking": True}
    )
    thinking_started = False
    answer_started = False
    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if not delta:
            continue
        # 检查是否有思考内容
        reasoning = getattr(delta, 'reasoning_content', None)
        if reasoning:
            if not thinking_started:
                print("\n[思考过程]")
                thinking_started = True
            print(reasoning, end="", flush=True)
        elif delta.content:
            if not answer_started:
                print("\n[回答]")
                answer_started = True
            print(delta.content, end="", flush=True)
    print()

if __name__ == '__main__':
    # 测试问题
    test_question = "你好呀"
    print("Qwen-3.5-Plus-LLM的回答：")
    llm = get_qwen35_plus_llm()
    print(llm.invoke(test_question))