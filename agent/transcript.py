"""Turns the graph's messages into what the web interface shows.

The graph keeps a conversation as a flat list of messages: what the user wrote, what the
model answered, which tools the model asked for and what the tools returned. The web
interface shows the same conversation as turns: the user's message, then the agent's
reply together with the steps (tool calls and tool results) that led to it and the
tickets the reply is about.

The tickets of a reply are taken from the tool calls and their results, never from the
model's text. A ticket number in an answer becomes a link in the web interface only when
a tool call in the same turn was about that ticket and the API did not answer that it
is missing. A number the model made up never becomes a link.
"""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from graph import DELETE_TOOL_NAME

# How much of a tool result the web interface shows. The model always gets the whole
# result.
MAX_SHOWN_RESULT_LENGTH = 300


def text_of(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content

    # Some models return a list of content blocks instead of one string.
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)


def format_call(call: dict) -> str:
    """A tool call as it would look in code: update_ticket(ticket_id=3, status='CLOSED')"""
    arguments = []
    for key in call["args"]:
        value = call["args"][key]
        arguments.append(f"{key}={value!r}")
    return call["name"] + "(" + ", ".join(arguments) + ")"


def shorten(text: str) -> str:
    text = text.replace("\n", " ")
    if len(text) > MAX_SHOWN_RESULT_LENGTH:
        return text[:MAX_SHOWN_RESULT_LENGTH] + " ..."
    return text


def is_error_result(text: str) -> bool:
    """True when a tool result says that the call failed or was not carried out.
    The three prefixes are the ones mcp_server.py and graph.py write."""
    if text.startswith("API ERROR"):
        return True
    if text.startswith("ERROR"):
        return True
    if text.startswith("NOT EXECUTED"):
        return True
    return False


def was_rejected_for_its_values(text: str) -> bool:
    """True when the API refused a call for another reason than a missing ticket, such
    as an invalid status. The ticket the call was about is then still worth a link:
    a 404 says the ticket is not there, any other rejection is about the values."""
    return text.startswith("API ERROR") and not text.startswith("API ERROR 404")


def find_tickets(data, found: list) -> None:
    """Collects every object that has a ticketId, however deep it sits in the JSON.
    A list of tickets gives one per ticket; GET /tickets/{id} has it under "ticket"."""
    if isinstance(data, dict):
        if "ticketId" in data:
            found.append(data)
        for key in data:
            find_tickets(data[key], found)
    elif isinstance(data, list):
        for item in data:
            find_tickets(item, found)


class Reply:
    """The agent's side of one turn, built up one message at a time.

    The same class is used in two places. While a turn is running, server.py feeds it
    each new message and sends the events it returns to the browser. When an old
    conversation is opened, build_chat_messages() below feeds it the stored messages.
    That way a reply looks the same live and when it is read back.
    """

    def __init__(self):
        self.content = ""         # the agent's text so far
        self.steps = []           # tool calls and tool results, in the order they happened
        self._calls_by_id = {}    # tool call id -> the call, to find the arguments of a result
        self._tickets_by_id = {}  # ticket id -> {"ticket_id", "title", "status"}

    def add(self, message) -> list:
        """Takes the next message of the turn. Returns the events it gives rise to,
        each one as {"event": name, "data": {...}}."""
        events = []

        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                self._calls_by_id[call["id"]] = call
                step = {"kind": "call", "text": format_call(call), "error": False}
                self.steps.append(step)
                events.append({"event": "tool_call", "data": step})

            text = text_of(message).strip()
            if text != "":
                if self.content != "":
                    self.content += "\n\n"
                self.content += text
                events.append({"event": "answer", "data": self._answer()})

        elif isinstance(message, ToolMessage):
            text = text_of(message)
            failed = is_error_result(text)

            call = self._calls_by_id.get(message.tool_call_id)
            if call is not None:
                if not failed:
                    self._collect_tickets(call, text)
                elif was_rejected_for_its_values(text):
                    self._note_ticket_of(call)

            step = {"kind": "result", "text": shorten(text), "error": failed}
            self.steps.append(step)
            events.append({"event": "tool_result", "data": step})

        return events

    def is_empty(self) -> bool:
        return self.content == "" and len(self.steps) == 0

    def to_chat_message(self) -> dict:
        return {
            "role": "assistant",
            "content": self.content,
            "steps": self.steps,
            "tickets": self._ticket_list(),
        }

    def _answer(self) -> dict:
        return {"content": self.content, "tickets": self._ticket_list()}

    def _ticket_list(self) -> list:
        tickets = []
        for ticket_id in self._tickets_by_id:
            tickets.append(self._tickets_by_id[ticket_id])
        return tickets

    def _collect_tickets(self, call: dict, result_text: str) -> None:
        """Notes which tickets a successful tool call was about."""
        ticket_id = call["args"].get("ticket_id")

        # A deleted ticket cannot be opened any more, so it is not offered as a link.
        if call["name"] == DELETE_TOOL_NAME:
            if ticket_id in self._tickets_by_id:
                del self._tickets_by_id[ticket_id]
            return

        try:
            data = json.loads(result_text)
        except ValueError:
            data = None

        found = []
        find_tickets(data, found)
        for ticket in found:
            self._tickets_by_id[ticket["ticketId"]] = {
                "ticket_id": ticket["ticketId"],
                "title": ticket.get("title"),
                "status": ticket.get("status"),
            }

        # Comments and history come back without the ticket's own fields. The call was
        # still about that ticket, and it succeeded, so the ticket exists.
        self._note_ticket_of(call)

    def _note_ticket_of(self, call: dict) -> None:
        """Adds the ticket a call was about, by id alone, unless it is already there
        with its title and status."""
        ticket_id = call["args"].get("ticket_id")
        if isinstance(ticket_id, int) and ticket_id not in self._tickets_by_id:
            self._tickets_by_id[ticket_id] = {"ticket_id": ticket_id, "title": None, "status": None}


def build_chat_messages(messages: list) -> list:
    """The whole conversation as the web interface shows it: user messages and agent
    replies in order."""
    chat_messages = []
    reply = None

    for message in messages:
        if isinstance(message, HumanMessage):
            if reply is not None and not reply.is_empty():
                chat_messages.append(reply.to_chat_message())
            chat_messages.append({"role": "user", "content": text_of(message)})
            reply = Reply()
        elif reply is not None:
            reply.add(message)

    if reply is not None and not reply.is_empty():
        chat_messages.append(reply.to_chat_message())

    return chat_messages


def reply_in_progress(messages: list) -> Reply:
    """The reply of the latest turn, built from everything after the last user message.
    Used when a turn continues after the user has answered a confirmation: the steps
    from before the stop are already part of the reply."""
    reply = Reply()

    for message in messages:
        if isinstance(message, HumanMessage):
            reply = Reply()
        else:
            reply.add(message)

    return reply
