from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI, ChatOpenAI


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

if __name__ == '__main__':
    # 测试问题
    test_question = "二代测序进行sRNA测序，建议进行PCA分析吗"
    llm = get_qwen35_plus_llm()
    response = llm.invoke(test_question)
    print("Qwen-3.5-Plus-LLM的回答：")  
    print(response)
    # Qwen-3.5-Plus-LLM的回答：
    # content='是的，**强烈建议在sRN...