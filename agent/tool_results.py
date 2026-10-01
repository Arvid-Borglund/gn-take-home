"""The text a tool hands back to the model, built from the API's answer.

Used by both sets of tools: the ones the agent calls directly (tools.py) and the ones
the MCP server offers (mcp_server.py). The model reads the same text either way.

- On success the text is the JSON the API returned.
- On a 4xx the text starts with "API ERROR <status>:" followed by the API's own message.
- When the API could not be reached at all the text starts with "ERROR:".
"""

import json

from api_client import ApiResult


def describe_result(result: ApiResult, text_when_no_body: str) -> str:
    """Turns an ApiResult into the text the model reads."""
    if result.ok:
        if result.data is None:
            return text_when_no_body
        return json.dumps(result.data)

    if result.status_code == 0:
        return f"ERROR: {result.error}"

    return f"API ERROR {result.status_code}: {result.error}"
