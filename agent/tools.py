"""The tools the model may call: one per endpoint of the ticket API.

A tool does three things: it takes the arguments the model chose, calls the API through
TicketApiClient, and returns a text for the model to read.

- On success the text is the JSON the API returned.
- On a 4xx the text starts with "API ERROR <status>:" followed by the API's own message.

Two rules follow from that. A tool never raises for a business-rule error: the error is
a result, and the model's job is to explain it to the user. And a tool never decides what
is valid. The status argument is a free string on purpose, and no description below lists
the valid statuses: the API owns the rules, and the agent learns them from its answers.
"""

import json
from typing import Optional

from langchain_core.tools import tool

from api_client import ApiResult, TicketApiClient

# graph.py stops and asks the user before a call to this tool is run.
DELETE_TOOL_NAME = "delete_ticket"


def describe_result(result: ApiResult, text_when_no_body: str) -> str:
    """Turns an ApiResult into the text the model reads."""
    if result.ok:
        if result.data is None:
            return text_when_no_body
        return json.dumps(result.data)

    if result.status_code == 0:
        return f"ERROR: {result.error}"

    return f"API ERROR {result.status_code}: {result.error}"


def build_tools(client: TicketApiClient) -> list:
    # The functions are defined inside build_tools so that they can use `client`.
    # @tool turns a function into a tool: the name, the arguments with their types and
    # the docstring become the description the model sees when it chooses what to call.

    @tool
    def create_ticket(title: str, description: str) -> str:
        """Create a new support ticket. A new ticket always starts as open.
        title is a short summary, description says what the problem is.
        Returns the created ticket, including its ticketId."""
        result = client.create_ticket(title, description)
        return describe_result(result, "The ticket was created.")

    @tool
    def list_tickets(status: Optional[str] = None) -> str:
        """List tickets. Without status: every ticket. With status: only the tickets
        that have that status. The API validates the status value."""
        result = client.list_tickets(status)
        return describe_result(result, "[]")

    @tool
    def get_ticket(ticket_id: int) -> str:
        """Get one ticket by id: all its fields plus its comments."""
        result = client.get_ticket(ticket_id)
        return describe_result(result, "")

    @tool
    def update_ticket(
        ticket_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        resolution: Optional[str] = None,
    ) -> str:
        """Update a ticket. Pass only the fields that should change; the others are
        left as they are. status sets a new status, resolution is the note on how the
        problem was solved. The API validates the values.
        Returns the updated ticket."""
        result = client.update_ticket(ticket_id, title, description, status, resolution)
        return describe_result(result, "The ticket was updated.")

    @tool
    def delete_ticket(ticket_id: int) -> str:
        """Delete a ticket permanently, together with its comments and history.
        The application asks the user to confirm before the deletion is carried out."""
        result = client.delete_ticket(ticket_id)
        return describe_result(result, f"Ticket {ticket_id} was deleted.")

    @tool
    def add_comment(ticket_id: int, body: str) -> str:
        """Add a comment to a ticket. Returns the created comment."""
        result = client.add_comment(ticket_id, body)
        return describe_result(result, "The comment was added.")

    @tool
    def get_ticket_history(ticket_id: int) -> str:
        """Get the history of a ticket: one snapshot per change, oldest first, each
        with its version number and the time of the change."""
        result = client.list_versions(ticket_id)
        return describe_result(result, "[]")

    return [
        create_ticket,
        list_tickets,
        get_ticket,
        update_ticket,
        delete_ticket,
        add_comment,
        get_ticket_history,
    ]
