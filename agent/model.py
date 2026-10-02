"""The language model the agent talks to.

Normally a deployment at Azure OpenAI, the one the assignment gives a key for. When
OLLAMA_BASE_URL is set, a local model served by Ollama is used instead. The graph does
not know which one it has: both take messages and tools and answer with tool calls.
"""

from langchain_ollama import ChatOllama
from langchain_openai import AzureChatOpenAI

from config import Settings


def build_llm(settings: Settings):
    if settings.ollama_base_url != "":
        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            # Qwen thinks before it answers unless it is told not to. With tool calls
            # that makes every round slow, and this agent does not need it.
            reasoning=False,
            # Ollama's own default context is small. The system prompt, the seven tool
            # descriptions, the conversation and the tool results all have to fit.
            num_ctx=32768,
            # How long Ollama keeps the model in memory after a request.
            keep_alive="30m",
        )

    # reasoning_effort="none": this model rejects tool calls on the chat completions
    # endpoint while reasoning is on (HTTP 400), and the API version we were given is
    # older than the Responses API, which is the other way to get tools.
    # No temperature: the model only accepts its default.
    return AzureChatOpenAI(
        azure_endpoint=settings.azure_endpoint,
        api_key=settings.azure_api_key,
        azure_deployment=settings.azure_deployment,
        api_version=settings.azure_api_version,
        reasoning_effort="none",
        timeout=60,
        max_retries=2,
    )
