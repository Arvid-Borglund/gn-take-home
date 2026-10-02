"""The language model the agent talks to: a deployment at Azure OpenAI."""

from langchain_openai import AzureChatOpenAI

from config import Settings


def build_llm(settings: Settings) -> AzureChatOpenAI:
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
