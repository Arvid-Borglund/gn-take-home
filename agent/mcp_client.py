"""The agent's side of MCP: starts the MCP server and makes its tools usable in the graph.

The agent does not call the ticket API itself. It starts mcp_server.py as a subprocess
and reaches the API through it (the CLI in main.py and the web server in server.py both
do; --direct turns it off):

    agent  --MCP over stdio-->  mcp_server.py  --HTTP-->  ticket API

What happens, in order:

1. connect_to_mcp_server() describes how the server is started. Opening the client it
   returns (async with) starts the subprocess and does the MCP handshake. Closing it
   stops the subprocess.
2. load_mcp_tools() asks the server which tools it has (tools/list) and wraps each one
   as a LangChain tool, with the name, the description and the argument schema that
   the server gave. Nothing about the tools is written down in the agent: it learns
   them from the server.
3. When the model calls a tool, the wrapper sends the call to the server (tools/call)
   and returns the text of the result.

The graph does not know where its tools come from. It gets a list of tools with the
same names as the direct ones in tools.py, so the confirmation before delete_ticket
works the same way with both.
"""

import inspect
import os
import sys

from langchain_core.tools import StructuredTool
from mcp import Client, StdioServerParameters

MCP_SERVER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")


def connect_to_mcp_server(ticket_api_url: str) -> Client:
    """Returns a client that starts the MCP server when it is opened with "async with".

    The server is started with the same Python as the agent. A subprocess started this
    way does not inherit the agent's environment variables, only the ones listed in
    env. So the address of the API is passed on, and the model key is not: the server
    has no use for it."""
    server = StdioServerParameters(
        command=sys.executable,
        args=[MCP_SERVER_FILE],
        env={"TICKET_API_URL": ticket_api_url},
    )
    return Client(server)


def text_of_result(result) -> str:
    """The text of an MCP tool result. A result is a list of content blocks; the
    ticket server only ever sends text blocks."""
    parts = []
    for block in result.content:
        if block.type == "text":
            parts.append(block.text)
    return "\n".join(parts)


class McpToolCaller:
    """Sends the calls of one tool to the MCP server."""

    def __init__(self, mcp_client: Client, tool_name: str):
        self._mcp_client = mcp_client
        self._tool_name = tool_name

    async def call(self, **arguments) -> str:
        result = await self._mcp_client.call_tool(self._tool_name, arguments)

        # A failed call (result.is_error) is not an exception here either. The text
        # already says what went wrong ("API ERROR 422: ..."), and the model gets it
        # as the tool result, exactly as with the direct tools.
        return text_of_result(result)


async def load_mcp_tools(mcp_client: Client) -> list:
    """Asks the server for its tools and returns them as LangChain tools."""
    listing = await mcp_client.list_tools()

    tools = []
    for mcp_tool in listing.tools:
        caller = McpToolCaller(mcp_client, mcp_tool.name)

        tool = StructuredTool(
            name=mcp_tool.name,
            # The server sends the docstring as it is written, indentation included.
            description=inspect.cleandoc(mcp_tool.description),
            # The argument schema (JSON Schema) goes to the model as it came.
            args_schema=mcp_tool.input_schema,
            # The tool is asynchronous: the graph calls it with ainvoke.
            coroutine=caller.call,
        )
        tools.append(tool)

    return tools
