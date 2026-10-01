"""MCP server for the ticket API: every endpoint is offered as an MCP tool.

    python mcp_server.py

MCP (Model Context Protocol) is a standard way for a program with a language model in
it (the client) to find out which tools a server has and to call them. The client does
not have to know this API: it asks the server for its tools (tools/list), gets a name,
a description and an argument schema for each, and calls one with tools/call.

    MCP client (the agent)  --MCP over stdio-->  this server  --HTTP-->  ticket API

The transport is stdio: the client starts this file as a subprocess and the two talk
over the subprocess's stdin and stdout. Nothing listens on a port. That is also why
nothing in this file may print to stdout: stdout carries the protocol.

A tool here does the same three things as a tool in tools.py: it takes the arguments
the model chose, calls the API through TicketApiClient, and returns a text for the
model to read (tool_results.py). The same two rules hold:

- A business-rule error is a result, not a crash. A 4xx from the API comes back as a
  tool result with the API's own message as text, and with the result marked as an
  error (is_error), which is how MCP says "the call was made and it failed".
- The server never decides what is valid. status is a free string and no description
  lists the valid statuses: the API owns the rules.
"""

import os
from typing import Optional

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from api_client import ApiResult, TicketApiClient
from tool_results import describe_result

# Where the ticket API is. The agent passes the address on when it starts the server.
TICKET_API_URL = os.environ.get("TICKET_API_URL", "http://localhost:8080")

client = TicketApiClient(TICKET_API_URL)

# log_level: the server writes its log to stderr, which ends up in the agent's
# terminal. Only warnings and errors are worth showing there.
mcp = MCPServer(
    "ticketing",
    instructions="Tools for a support ticketing system: create, list, read, update, comment on and delete tickets.",
    log_level="WARNING",
)


def to_tool_result(result: ApiResult, text_when_no_body: str) -> CallToolResult:
    """Turns an ApiResult into an MCP tool result: the text, and whether it is an error."""
    text = describe_result(result, text_when_no_body)
    is_error = not result.ok
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=is_error)


# @mcp.tool() registers a function as a tool: the function name, the arguments with
# their types and the docstring become what the client gets from tools/list.
#
# The annotations are hints for the client about what a tool does to the data:
# read_only_hint says it changes nothing, destructive_hint says it can remove something.
# A client can use them to decide when to ask the user first.

@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False))
def create_ticket(title: str, description: str) -> CallToolResult:
    """Create a new support ticket. A new ticket always starts as open.
    title is a short summary, description says what the problem is.
    Returns the created ticket, including its ticketId."""
    result = client.create_ticket(title, description)
    return to_tool_result(result, "The ticket was created.")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_tickets(status: Optional[str] = None) -> CallToolResult:
    """List tickets. Without status: every ticket. With status: only the tickets
    that have that status. The API validates the status value."""
    result = client.list_tickets(status)
    return to_tool_result(result, "[]")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_ticket(ticket_id: int) -> CallToolResult:
    """Get one ticket by id: all its fields plus its comments."""
    result = client.get_ticket(ticket_id)
    return to_tool_result(result, "")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False))
def update_ticket(
    ticket_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    resolution: Optional[str] = None,
) -> CallToolResult:
    """Update a ticket. Pass only the fields that should change; the others are
    left as they are. status sets a new status, resolution is the note on how the
    problem was solved. The API validates the values.
    Returns the updated ticket."""
    result = client.update_ticket(ticket_id, title, description, status, resolution)
    return to_tool_result(result, "The ticket was updated.")


# The server carries out a delete when it is asked to. Asking the user first is the
# client's job (the agent does it in graph.py); destructive_hint tells any other
# client that this is the tool to be careful with.
@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True))
def delete_ticket(ticket_id: int) -> CallToolResult:
    """Delete a ticket permanently, together with its comments and history.
    The application asks the user to confirm before the deletion is carried out."""
    result = client.delete_ticket(ticket_id)
    return to_tool_result(result, f"Ticket {ticket_id} was deleted.")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False))
def add_comment(ticket_id: int, body: str) -> CallToolResult:
    """Add a comment to a ticket. Returns the created comment."""
    result = client.add_comment(ticket_id, body)
    return to_tool_result(result, "The comment was added.")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_ticket_history(ticket_id: int) -> CallToolResult:
    """Get the history of a ticket: one snapshot per change, oldest first, each
    with its version number and the time of the change."""
    result = client.list_versions(ticket_id)
    return to_tool_result(result, "[]")


if __name__ == "__main__":
    mcp.run(transport="stdio")
