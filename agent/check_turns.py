"""Checks how the web server (server.py) runs a turn and stores its conversations,
without a language model and without the ticket API.

    python check_turns.py

The real graph, the real ChatServer and a real PostgreSQL are used (the address is in
DATABASE_URL, as for the server). Two things are replaced:

- the language model, by ScriptedModel, which answers from a list written in this file;
- the tools, by two that touch nothing: a lookup that takes a moment, and a delete.

The handlers of ChatServer are called directly, the way FastAPI would call them. What
a handler returns is the response whose body is the stream of events. Reading that
body one event at a time is what the browser does, and closing it early is what
happens when the browser hangs up.

What is checked:

1. A turn that is read to its end gives its events in order, with "done" last.
2. A turn whose reader hangs up after the first event still runs to its end: the
   conversation has the tool result and the answer, it has not failed, and the next
   message in the same conversation works.
3. A message that arrives while a turn is running is refused (409).
4. A turn that stops at the question before a delete, with nobody reading: the
   question is still there afterwards, and answering it carries out the delete.
5. A turn that fails with nobody reading marks the conversation as failed.
6. A conversation belongs to its user: another user does not get it in their list, and
   gets a 404 for everything they try with it.
7. A conversation is still there after a restart: a new server on the same database
   has its messages and the question it was stopped at, and can answer the question.

The conversations are created for two users that exist only here, and they are deleted
again at the end. The exit code is 0 only when every check passes. CI runs it.
"""

import asyncio
import os
import sys

from fastapi import HTTPException
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

from conversations import Conversations, build_checkpointer, open_database
from graph import TicketAgent
from server import ChatServer, Confirmation, NewMessage
from tools import DELETE_TOOL_NAME

# How long the lookup tool takes. Long enough for a reader to hang up while it runs.
TOOL_SECONDS = 0.3

# The two users of the checks. Neither is a login that exists anywhere.
USER = "check-turns"
OTHER_USER = "check-turns-other"


# ----- What stands in for the model and the tools -----

class ScriptedModel:
    """Stands in for the language model. It gives the answers it was created with, one
    per call, in order. An answer that is an exception is raised instead."""

    def __init__(self, answers: list):
        self._answers = answers
        self._next = 0

    def bind_tools(self, tools: list):
        # The real model object returns a copy of itself that knows the tools.
        return self

    async def ainvoke(self, messages: list):
        answer = self._answers[self._next]
        self._next += 1
        if isinstance(answer, Exception):
            raise answer
        return answer


async def get_ticket(ticket_id: int) -> str:
    await asyncio.sleep(TOOL_SECONDS)
    return '{"ticket": {"ticketId": ' + str(ticket_id) + ', "title": "Printer out of toner", "status": "OPEN"}, "comments": []}'


async def delete_ticket(ticket_id: int) -> str:
    return f"Ticket {ticket_id} was deleted."


async def build_server(pool, answers: list) -> ChatServer:
    """A ChatServer around the real graph, with the scripted model and the two tools,
    built the way serve() in server.py builds the real one."""
    tools = [
        StructuredTool.from_function(coroutine=get_ticket, name="get_ticket", description="Get one ticket by id."),
        StructuredTool.from_function(coroutine=delete_ticket, name=DELETE_TOOL_NAME, description="Delete a ticket."),
    ]
    checkpointer = await build_checkpointer(pool)
    graph = TicketAgent(ScriptedModel(answers), tools).build(checkpointer)

    # No ticket API client and no settings: only /health and /scenarios use them.
    return ChatServer(graph, None, None, "direct", Conversations(pool))


def asks_for(tool_name: str, ticket_id: int) -> AIMessage:
    """What the model answers when it wants a tool to be called."""
    call = {"name": tool_name, "args": {"ticket_id": ticket_id}, "id": f"call-{tool_name}-{ticket_id}"}
    return AIMessage(content="", tool_calls=[call])


def says(text: str) -> AIMessage:
    return AIMessage(content=text)


# ----- What stands in for the browser -----

def event_name(event: str) -> str:
    """The name in the first line of a server-sent event: "event: tool_call"."""
    first_line = event.split("\n")[0]
    return first_line.replace("event: ", "")


async def read_all(response) -> list:
    """Reads a response to its end, as a browser that stays. Returns the event names."""
    names = []
    async for event in response.body_iterator:
        names.append(event_name(event))
    return names


async def read_one_and_hang_up(response) -> str:
    """Reads the first event and closes the stream, as a browser that goes away."""
    body = response.body_iterator
    first = await body.__anext__()
    await body.aclose()
    return event_name(first)


async def wait_until_idle(server: ChatServer, conversation_id: int) -> dict:
    """Asks for the conversation until no turn is running in it, at most five seconds.
    Returns the conversation as the last answer described it."""
    waited = 0.0
    while True:
        conversation = await server.get_conversation(conversation_id, USER)
        if not conversation["running"] or waited >= 5.0:
            return conversation
        await asyncio.sleep(0.05)
        waited += 0.05


async def status_of(call) -> int:
    """Awaits a handler call and returns the HTTP status it was refused with, or 0
    when it was not refused."""
    try:
        await call
    except HTTPException as error:
        return error.status_code
    return 0


def step_kinds(chat_message: dict) -> list:
    kinds = []
    for step in chat_message["steps"]:
        kinds.append(step["kind"])
    return kinds


def report(problems: list, name: str, ok: bool, detail) -> None:
    if ok:
        print(f"ok      {name}")
    else:
        print(f"FAILED  {name}: {detail}")
        problems.append(name)


# ----- The checks -----

async def check_a_turn_that_is_read(problems: list, pool) -> None:
    server = await build_server(pool, [asks_for("get_ticket", 7), says("Ticket 7 is open.")])
    conversation = await server.create_conversation(USER)

    response = await server.post_message(conversation["id"], NewMessage(content="Get ticket 7."), USER)
    names = await read_all(response)

    expected = ["tool_call", "tool_result", "answer", "done"]
    report(problems, "a turn that is read gives its events in order, done last", names == expected, names)


async def check_a_turn_nobody_reads(problems: list, pool) -> None:
    server = await build_server(pool, [
        asks_for("get_ticket", 7), says("Ticket 7 is open."),
        asks_for("get_ticket", 8), says("Ticket 8 is open too."),
    ])
    conversation = await server.create_conversation(USER)
    conversation_id = conversation["id"]

    response = await server.post_message(conversation_id, NewMessage(content="Get ticket 7."), USER)
    first = await read_one_and_hang_up(response)
    report(problems, "the reader got the first event and hung up", first == "tool_call", first)

    during = await server.get_conversation(conversation_id, USER)
    report(problems, "the turn is still running after the hang-up", during["running"] is True, during["running"])

    after = await wait_until_idle(server, conversation_id)
    reply = after["messages"][-1]
    report(problems, "the turn ran to its end", after["running"] is False, after["running"])
    report(problems, "the reply has the tool call and its result", step_kinds(reply) == ["call", "result"], step_kinds(reply))
    report(problems, "the reply has the answer", reply["content"] == "Ticket 7 is open.", reply["content"])
    report(problems, "the conversation has not failed", after["failed"] is False, after["failed"])

    response = await server.post_message(conversation_id, NewMessage(content="And ticket 8?"), USER)
    names = await read_all(response)
    report(problems, "the next message in the same conversation works", names == ["tool_call", "tool_result", "answer", "done"], names)


async def check_a_message_during_a_turn(problems: list, pool) -> None:
    server = await build_server(pool, [asks_for("get_ticket", 7), says("Ticket 7 is open.")])
    conversation = await server.create_conversation(USER)
    conversation_id = conversation["id"]

    response = await server.post_message(conversation_id, NewMessage(content="Get ticket 7."), USER)

    status = await status_of(server.post_message(conversation_id, NewMessage(content="Hello?"), USER))
    report(problems, "a message during a running turn is refused with 409", status == 409, status)

    status = await status_of(server.delete_conversation(conversation_id, USER))
    report(problems, "deleting the conversation during a running turn is refused with 409", status == 409, status)

    names = await read_all(response)
    report(problems, "the running turn was not disturbed", names[-1] == "done" and "answer" in names, names)


async def check_a_delete_question_nobody_reads(problems: list, pool) -> None:
    server = await build_server(pool, [
        asks_for("get_ticket", 7),
        asks_for(DELETE_TOOL_NAME, 7),
        says("Ticket 7 was deleted."),
    ])
    conversation = await server.create_conversation(USER)
    conversation_id = conversation["id"]

    response = await server.post_message(conversation_id, NewMessage(content="Look at ticket 7, then delete it."), USER)
    await read_one_and_hang_up(response)

    after = await wait_until_idle(server, conversation_id)
    question = after["pending_confirmation"]
    expected = {"action": DELETE_TOOL_NAME, "ticket_ids": [7]}
    report(problems, "the question before the delete is waiting", question == expected, question)
    report(problems, "the conversation has not failed", after["failed"] is False, after["failed"])

    response = await server.post_confirmation(conversation_id, Confirmation(confirmed=True), USER)
    names = await read_all(response)
    report(problems, "answering the question carries out the delete", names == ["tool_result", "answer", "done"], names)

    final = await server.get_conversation(conversation_id, USER)
    report(problems, "no question is waiting afterwards", final["pending_confirmation"] is None, final["pending_confirmation"])


async def check_a_failure_nobody_reads(problems: list, pool) -> None:
    server = await build_server(pool, [asks_for("get_ticket", 7), RuntimeError("the model is down (this error is part of the check)")])
    conversation = await server.create_conversation(USER)
    conversation_id = conversation["id"]

    response = await server.post_message(conversation_id, NewMessage(content="Get ticket 7."), USER)
    await read_one_and_hang_up(response)

    print("        (a traceback is expected below: the turn fails on purpose, and the server logs it)")
    after = await wait_until_idle(server, conversation_id)
    report(problems, "a turn that fails with nobody reading marks the conversation as failed", after["failed"] is True, after["failed"])

    status = await status_of(server.post_message(conversation_id, NewMessage(content="Again?"), USER))
    report(problems, "a failed conversation takes no more messages (409)", status == 409, status)


async def check_whose_a_conversation_is(problems: list, pool) -> None:
    server = await build_server(pool, [says("Hello.")])
    conversation = await server.create_conversation(USER)
    conversation_id = conversation["id"]

    response = await server.post_message(conversation_id, NewMessage(content="Hi."), USER)
    await read_all(response)

    own_ids = []
    for listed in await server.list_conversations(USER):
        own_ids.append(listed["id"])
    report(problems, "a conversation is in its own user's list", conversation_id in own_ids, own_ids)

    other_ids = []
    for listed in await server.list_conversations(OTHER_USER):
        other_ids.append(listed["id"])
    report(problems, "it is not in another user's list", conversation_id not in other_ids, other_ids)

    status = await status_of(server.get_conversation(conversation_id, OTHER_USER))
    report(problems, "another user gets 404 when asking for it", status == 404, status)

    status = await status_of(server.post_message(conversation_id, NewMessage(content="Hi."), OTHER_USER))
    report(problems, "another user gets 404 when writing in it", status == 404, status)

    status = await status_of(server.delete_conversation(conversation_id, OTHER_USER))
    report(problems, "another user gets 404 when deleting it", status == 404, status)

    still_there = await server.get_conversation(conversation_id, USER)
    report(problems, "and it is still there for its own user", len(still_there["messages"]) == 2, still_there["messages"])


async def check_a_restart(problems: list, pool) -> None:
    before = await build_server(pool, [asks_for(DELETE_TOOL_NAME, 7)])
    conversation = await before.create_conversation(USER)
    conversation_id = conversation["id"]

    response = await before.post_message(conversation_id, NewMessage(content="Delete ticket 7."), USER)
    names = await read_all(response)
    report(problems, "a turn stops at the question before a delete", names == ["tool_call", "confirm", "done"], names)

    # A new graph, a new checkpointer and a new ChatServer on the same database: what
    # a restarted server has. Nothing is carried over in memory.
    after = await build_server(pool, [says("Ticket 7 was deleted.")])

    listed_ids = []
    for listed in await after.list_conversations(USER):
        listed_ids.append(listed["id"])
    report(problems, "after a restart the conversation is still in the list", conversation_id in listed_ids, listed_ids)

    restored = await after.get_conversation(conversation_id, USER)
    report(problems, "it has its title", restored["title"] == "Delete ticket 7.", restored["title"])
    report(problems, "it has its messages", len(restored["messages"]) == 2, restored["messages"])
    expected = {"action": DELETE_TOOL_NAME, "ticket_ids": [7]}
    report(problems, "the question before the delete is still waiting", restored["pending_confirmation"] == expected, restored["pending_confirmation"])

    response = await after.post_confirmation(conversation_id, Confirmation(confirmed=True), USER)
    names = await read_all(response)
    report(problems, "the restarted server can answer the question", names == ["tool_result", "answer", "done"], names)


async def delete_the_conversations_of(pool, username: str) -> None:
    """Removes what the checks created, the messages as well as the rows."""
    server = await build_server(pool, [])
    for listed in await server.list_conversations(username):
        await server.delete_conversation(listed["id"], username)


async def check() -> int:
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url == "":
        print("Missing setting: DATABASE_URL. The checks store their conversations in PostgreSQL, as the server does.")
        return 1

    problems = []

    pool = await open_database(database_url)
    try:
        await check_a_turn_that_is_read(problems, pool)
        await check_a_turn_nobody_reads(problems, pool)
        await check_a_message_during_a_turn(problems, pool)
        await check_a_delete_question_nobody_reads(problems, pool)
        await check_a_failure_nobody_reads(problems, pool)
        await check_whose_a_conversation_is(problems, pool)
        await check_a_restart(problems, pool)

        await delete_the_conversations_of(pool, USER)
        await delete_the_conversations_of(pool, OTHER_USER)
    finally:
        await pool.close()

    print()
    if len(problems) > 0:
        print(f"{len(problems)} checks failed.")
        return 1

    print("A turn runs to its end whether or not anyone reads it, and a conversation is kept for its user.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(check()))
