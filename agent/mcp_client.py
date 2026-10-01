"""The agent's side of MCP: starts the MCP server and makes its tools usable in the graph.

The agent does not call the ticket API itself. It starts mcp_server.py as a subprocess
and reaches the API through it (the CLI in main.py and the web server in server.py both
do; --direct turns it off):

    agent  --MCP over stdio-->  mcp_server.py  --HTTP-->  ticket API

McpConnection owns that subprocess. What happens, in order:

1. start() starts the server and does the MCP handshake.
2. load_tools() asks the server which tools it has (tools/list) and wraps each one as a
   LangChain tool, with the name, the description and the argument schema that the
   server gave. Nothing about the tools is written down in the agent: it learns them
   from the server.
3. When the model calls a tool, the wrapper sends the call to the server (tools/call)
   through call_tool() and returns the text of the result. Before every call,
   call_tool() checks that the server still answers. If it has died, it is started
   again first, so the web server heals without being restarted itself.
4. stop() stops the server.

The graph does not know where its tools come from. It gets a list of tools with the
same names as the direct ones in tools.py, so the confirmation before delete_ticket
works the same way with both.
"""

import asyncio
import inspect
import os
import sys

from langchain_core.tools import StructuredTool
from mcp import Client, StdioServerParameters

MCP_SERVER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")

# How long the server gets to answer the "are you there" question before a tool call.
ALIVE_TIMEOUT_SECONDS = 5


class McpServerError(Exception):
    pass


def text_of_result(result) -> str:
    """The text of an MCP tool result. A result is a list of content blocks; the
    ticket server only ever sends text blocks."""
    parts = []
    for block in result.content:
        if block.type == "text":
            parts.append(block.text)
    return "\n".join(parts)


class McpConnection:
    """Owns the MCP server process: starts it, stops it, sends tool calls to it, and
    starts it again when it has died."""

    def __init__(self, ticket_api_url: str):
        self._ticket_api_url = ticket_api_url

        self._client = None            # the open SDK client; None while no server runs
        self._task = None              # the task that keeps the client open (_keep_open)
        self._opened = None            # set when that task has opened the client, or failed to
        self._close_requested = None   # set by stop(): tells that task to close the client
        self._open_error = None        # why the client could not be opened

        # Only one tool call at a time may check the server and restart it.
        self._restart_lock = asyncio.Lock()

        self.server_name = ""          # the name the server gave in the handshake
        self.restarts = 0              # how many times a dead server was started again

    # ----- Starting and stopping -----

    def _new_client(self) -> Client:
        """A client that starts the MCP server when it is opened with "async with".

        The server is started with the same Python as the agent. A subprocess started
        this way does not inherit the agent's environment variables, only the ones
        listed in env. So the address of the API is passed on, and the model key is
        not: the server has no use for it."""
        server = StdioServerParameters(
            command=sys.executable,
            args=[MCP_SERVER_FILE],
            env={"TICKET_API_URL": self._ticket_api_url},
        )
        return Client(server)

    async def _keep_open(self) -> None:
        """Opens the client, keeps it open until stop() asks, and closes it.

        This runs as a task of its own. The SDK requires that a client is closed by
        the same task that opened it, and a restart is discovered by whichever request
        happens to make the next tool call. That request's task ends long before the
        server is stopped, so it cannot be the one that holds the client open."""
        try:
            async with self._new_client() as client:
                self._client = client
                self.server_name = client.server_info.name
                self._opened.set()
                await self._close_requested.wait()
        except Exception as error:
            # Either the server could not be started, or closing a server that was
            # already dead complained. start() only looks at this in the first case.
            self._open_error = error
        finally:
            self._client = None
            self._opened.set()

    async def start(self) -> None:
        """Starts the server and returns when the handshake is done. Raises the error
        if the server could not be started."""
        self._opened = asyncio.Event()
        self._close_requested = asyncio.Event()
        self._open_error = None
        self._task = asyncio.create_task(self._keep_open())

        await self._opened.wait()

        if self._client is None:
            error = self._open_error
            if error is None:
                error = McpServerError("The MCP server did not start.")
            raise error

    async def stop(self) -> None:
        """Stops the server. Does nothing if it is not running."""
        if self._task is None:
            return

        self._close_requested.set()
        await self._task
        self._task = None

    # ----- Using the server -----

    async def load_tools(self) -> list:
        """Asks the server for its tools and returns them as LangChain tools."""
        listing = await self._client.list_tools()

        tools = []
        for mcp_tool in listing.tools:
            caller = McpToolCaller(self, mcp_tool.name)

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

    async def call_tool(self, tool_name: str, arguments: dict):
        """Sends one tool call to the server and returns the MCP result."""
        # One call at a time through this part. Two calls that both find the server
        # dead must not start two new servers: the second one waits, and then finds
        # the server the first one started.
        async with self._restart_lock:
            alive = await self._is_alive()
            if not alive:
                await self._restart()
            client = self._client

        # The call itself is made once and is never repeated. If the server dies in the
        # middle of it, nobody knows whether the ticket API was already called, and a
        # second create_ticket would make a second ticket. The error then goes back as
        # the tool result, and the next call finds the server dead and restarts it.
        return await client.call_tool(tool_name, arguments)

    async def _is_alive(self) -> bool:
        """True when the server answers a request.

        MCP used to have a ping request for this, but it was removed from the protocol
        (revision 2026-07-28), so the question asked is tools/list: every server
        answers it, and it changes nothing. cache_mode="bypass" makes the SDK send
        the request to the server instead of answering from its own cache. A living
        server answers in a millisecond or two; a dead one gives an error at once."""
        if self._client is None:
            return False

        try:
            await asyncio.wait_for(self._client.list_tools(cache_mode="bypass"), ALIVE_TIMEOUT_SECONDS)
        except Exception:
            return False

        return True

    async def _restart(self) -> None:
        await self.stop()

        try:
            await self.start()
        except Exception as error:
            # This becomes the tool result ("ERROR: the tool call failed: ..."), so it
            # is written for the model and the user. The next call tries again.
            raise McpServerError("The MCP server has stopped and could not be started again.") from error

        self.restarts += 1
        # To stderr: it belongs in the server log, not in a conversation.
        print(f"(the MCP server had stopped and was started again, restart {self.restarts})", file=sys.stderr)


class McpToolCaller:
    """Sends the calls of one tool to the MCP server."""

    def __init__(self, connection: McpConnection, tool_name: str):
        self._connection = connection
        self._tool_name = tool_name

    async def call(self, **arguments) -> str:
        result = await self._connection.call_tool(self._tool_name, arguments)

        # A failed call (result.is_error) is not an exception here either. The text
        # already says what went wrong ("API ERROR 422: ..."), and the model gets it
        # as the tool result, exactly as with the direct tools.
        return text_of_result(result)
