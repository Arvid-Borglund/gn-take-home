"""HTTP server for the ticket agent: the graph behind /api/chat. This is the program the
agent container runs.

    python server.py            starts the server on port 8000
    python server.py --direct   the same, with the agent's own tools (tools.py) instead
                                of the MCP server's

The tools come from the MCP server (mcp_server.py). It is started once, as a
subprocess, when this server starts, and it lives as long as this server does.

The web interface (web/) talks to this server. A message goes in with a POST, and the
answer comes back as a stream of server-sent events, one per thing that happens in the
graph: a tool call, a tool result, the agent's answer, or a question to the user.

    event: tool_call     the model asked for a tool
    event: tool_result   what the tool returned
    event: answer        the agent's text so far, and the tickets it is about
    event: confirm       the graph stopped before a delete and waits for a yes or no
    event: error         the turn failed
    event: done          the stream is over

A turn does not depend on that stream. It runs as a task of its own and puts its events
in a queue that the response reads from, so a turn runs to its end even if the browser
hangs up in the middle of it (see "Running the graph" in ChatServer).

The conversations are stored in PostgreSQL (conversations.py): the list of them in the
table "conversation", their messages by the graph's checkpointer. They are still there
after the server has been restarted, and each user only sees their own.
"""

import asyncio
import json
import sys
import traceback
from typing import Optional

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError
from langgraph.types import Command
from pydantic import BaseModel

from api_client import TicketApiClient, wait_for_api
from config import ConfigError, Settings, load_settings
from conversations import Conversations, build_checkpointer, open_database
from graph import MAX_GRAPH_STEPS, TicketAgent
from mcp_client import McpConnection
from model import build_llm
from scenarios import list_scenarios
from tools import build_tools
from transcript import Reply, build_chat_messages, reply_in_progress

PORT = 8000

# A conversation is named after its first message, cut to this length.
MAX_TITLE_LENGTH = 60

# Put in a turn's queue after its last event: it tells the reader that the turn is over.
END_OF_TURN = None

# The answer to a message or a confirmation that arrives while a turn is running.
STILL_WORKING = "The agent is still working on the previous message. Wait for it to finish."

# Whose the conversations are when there is no login in front of the server.
LOCAL_USER = "local"


# ----- Request bodies -----

class NewMessage(BaseModel):
    content: str


class Confirmation(BaseModel):
    confirmed: bool


# ----- Conversations -----

def user_of(x_user) -> str:
    """The user a request comes from.

    In front of this server stands nginx (web/), which does the login. It puts the
    login name in the header X-User on every request it passes on, and it sets the
    header itself, so a browser cannot choose its own. When the server is run without
    a login in front of it, there is no such header, and everything belongs to one
    user called "local"."""
    if isinstance(x_user, str) and x_user.strip() != "":
        return x_user.strip()
    return LOCAL_USER


def sse(event: str, data: dict) -> str:
    """One server-sent event: a name, a line of JSON, and an empty line to end it."""
    return "event: " + event + "\ndata: " + json.dumps(data) + "\n\n"


class ChatServer:
    def __init__(self, graph, client: TicketApiClient, settings: Settings, tools_from: str, conversations: Conversations):
        self._graph = graph
        self._client = client
        self._settings = settings
        self._tools_from = tools_from   # "mcp" or "direct", shown by /api/chat/health

        # The table "conversation" in the database: which conversations there are and
        # whose they are. A row is a dictionary with the table's column names. The
        # messages of a conversation are in the graph's checkpointer.
        self._conversations = conversations

        # The only thing that lives in this process: the task that runs a conversation's
        # current turn (_run_turn), by conversation id. Keeping it here does two things:
        # it tells whether a turn is running, and it keeps the task from being thrown
        # away while it runs.
        self._turn_tasks = {}

    def build_app(self) -> FastAPI:
        app = FastAPI(title="Ticket agent")

        app.add_api_route("/api/chat/health", self.health, methods=["GET"])
        app.add_api_route("/api/chat/scenarios", self.scenarios, methods=["GET"])
        app.add_api_route("/api/chat/conversations", self.list_conversations, methods=["GET"])
        app.add_api_route("/api/chat/conversations", self.create_conversation, methods=["POST"], status_code=201)
        app.add_api_route("/api/chat/conversations/{conversation_id}", self.get_conversation, methods=["GET"])
        app.add_api_route("/api/chat/conversations/{conversation_id}", self.delete_conversation, methods=["DELETE"], status_code=204)
        app.add_api_route("/api/chat/conversations/{conversation_id}/messages", self.post_message, methods=["POST"])
        app.add_api_route("/api/chat/conversations/{conversation_id}/confirmation", self.post_confirmation, methods=["POST"])

        return app

    # ----- Handlers -----
    # The first two are plain functions, not async: they call the ticket API with the
    # blocking client, and FastAPI runs plain functions in a thread of their own.

    def health(self) -> dict:
        result = self._client.list_tickets(None)
        ticket_api_up = result.status_code != 0

        status = "degraded"
        if ticket_api_up:
            status = "ok"

        return {
            "status": status,
            "ticket_api": ticket_api_up,
            "model": self._settings.azure_deployment,
            "tools": self._tools_from,
        }

    def scenarios(self) -> list:
        """The example requests the web interface offers (scenarios.py)."""
        return list_scenarios(self._client)

    # The rest take x_user: FastAPI fills it in from the request header X-User.
    # A user only ever gets their own conversations (_find, and list_for).

    async def list_conversations(self, x_user: Optional[str] = Header(None)) -> list:
        rows = await self._conversations.list_for(user_of(x_user))

        conversations = []
        for row in rows:
            conversations.append(self._describe(row))
        return conversations

    async def create_conversation(self, x_user: Optional[str] = Header(None)) -> dict:
        row = await self._conversations.create(user_of(x_user))
        return self._describe(row)

    async def get_conversation(self, conversation_id: int, x_user: Optional[str] = Header(None)) -> dict:
        # Asked before anything is read from the database. If the turn ends while the
        # reading goes on, the answer says "still running" and the browser asks again;
        # it never says "ended" together with a state that is not the final one.
        running = self._turn_is_running(conversation_id)

        row = await self._find(conversation_id, x_user)
        state = await self._graph.aget_state(self._config(conversation_id))

        result = self._describe(row)
        result["running"] = running
        result["messages"] = build_chat_messages(state.values.get("messages", []))
        result["pending_confirmation"] = pending_question(state)
        return result

    async def delete_conversation(self, conversation_id: int, x_user: Optional[str] = Header(None)) -> Response:
        await self._find(conversation_id, x_user)
        if self._turn_is_running(conversation_id):
            raise HTTPException(status_code=409, detail="The agent is still working in this conversation. Delete it when it has finished.")

        # The messages first, then the row in the list.
        await self._graph.checkpointer.adelete_thread(self._thread_id(conversation_id))
        await self._conversations.delete(conversation_id)
        return Response(status_code=204)

    async def post_message(self, conversation_id: int, body: NewMessage, x_user: Optional[str] = Header(None)) -> StreamingResponse:
        row = await self._find(conversation_id, x_user)
        content = body.content.strip()

        if content == "":
            raise HTTPException(status_code=422, detail="The message is empty.")
        if row["failed"]:
            raise HTTPException(status_code=409, detail="This conversation stopped on an error. Start a new one.")

        state = await self._graph.aget_state(self._config(conversation_id))

        # From here to _start_turn there is no "await", so no other request can get in
        # between the checks and the start: a conversation runs one turn at a time.
        if self._turn_is_running(conversation_id):
            raise HTTPException(status_code=409, detail=STILL_WORKING)
        if pending_question(state) is not None:
            raise HTTPException(status_code=409, detail="The agent is waiting for a yes or no to a deletion.")

        graph_input = {"messages": [HumanMessage(content=content)]}
        response = self._start_turn(conversation_id, graph_input, Reply())

        # The turn is running now. A conversation is named after its first message.
        if row["title"] == "":
            await self._conversations.set_title(conversation_id, content[:MAX_TITLE_LENGTH])

        return response

    async def post_confirmation(self, conversation_id: int, body: Confirmation, x_user: Optional[str] = Header(None)) -> StreamingResponse:
        await self._find(conversation_id, x_user)

        state = await self._graph.aget_state(self._config(conversation_id))

        # No "await" from here to _start_turn, as in post_message.
        if self._turn_is_running(conversation_id):
            raise HTTPException(status_code=409, detail=STILL_WORKING)
        if pending_question(state) is None:
            raise HTTPException(status_code=409, detail="The agent is not waiting for a confirmation.")

        # The turn continues where it stopped, so the reply starts from the steps that
        # were already taken, not from nothing.
        reply = reply_in_progress(state.values.get("messages", []))

        # Command(resume=...) continues the graph from the interrupt() that stopped it.
        graph_input = Command(resume=body.confirmed)
        return self._start_turn(conversation_id, graph_input, reply)

    # ----- Running the graph -----
    #
    # A turn is split in two, with a queue between them:
    #
    #   _run_turn     the producer. It runs the graph and puts every event in the queue.
    #                 It is a task of its own, started by _start_turn, and it does not
    #                 know whether anyone reads the queue.
    #   _read_events  the consumer. It takes the events out of the queue and hands them
    #                 to the browser. It is the body of the HTTP response.
    #
    # The reason is what happens when the browser hangs up in the middle of a turn (a
    # closed tab, a reload). The HTTP response is then stopped, wherever it is. If the
    # response itself ran the graph, the graph would stop too, possibly after the model
    # has asked for a tool and before the tool has answered. The conversation would be
    # left with a question without an answer, and the model refuses to continue from
    # that. With the split, only the reader stops. The turn runs to its end (or to the
    # question before a delete), so what is saved is always a finished exchange, and the
    # browser gets it when it asks for the conversation again.

    def _start_turn(self, conversation_id: int, graph_input, reply: Reply) -> StreamingResponse:
        # The queue has no size limit, so the producer never has to wait for a reader.
        events = asyncio.Queue()
        self._turn_tasks[conversation_id] = asyncio.create_task(self._run_turn(conversation_id, graph_input, reply, events))

        headers = {
            "Cache-Control": "no-cache",
            # Tells nginx to pass every event on at once instead of collecting them.
            "X-Accel-Buffering": "no",
        }
        return StreamingResponse(self._read_events(events), media_type="text/event-stream", headers=headers)

    async def _run_turn(self, conversation_id: int, graph_input, reply: Reply, events: asyncio.Queue) -> None:
        """Runs the graph for one turn and puts what happens in the queue, as
        server-sent events."""
        try:
            await self._run_graph(conversation_id, graph_input, reply, events)
            await self._conversations.mark_used(conversation_id)
        finally:
            # Whatever happened above, also if the database could not be reached:
            # a reader must never be left waiting for an end that does not come.
            events.put_nowait(sse("done", {}))
            events.put_nowait(END_OF_TURN)

    async def _run_graph(self, conversation_id: int, graph_input, reply: Reply, events: asyncio.Queue) -> None:
        try:
            # stream_mode="updates" gives one item per finished node, holding what that
            # node added to the state. A stop at interrupt() arrives under "__interrupt__".
            async for update in self._graph.astream(graph_input, self._config(conversation_id), stream_mode="updates"):
                for node_name in update:
                    if node_name == "__interrupt__":
                        question = update[node_name][0].value
                        events.put_nowait(sse("confirm", question))
                        continue

                    node_update = update[node_name]
                    if node_update is None:
                        continue

                    for message in node_update.get("messages", []):
                        for event in reply.add(message):
                            events.put_nowait(sse(event["event"], event["data"]))

        except GraphRecursionError:
            message = f"I stopped after {MAX_GRAPH_STEPS} steps without finishing. Try a more specific request."
            # Perhaps nobody reads the queue any more. The log always gets the error.
            print(f"Conversation {conversation_id}: {message}", file=sys.stderr)
            events.put_nowait(sse("error", {"message": message}))
            await self._conversations.mark_failed(conversation_id)
        except Exception as error:
            message = f"The language model call failed ({type(error).__name__}): {error}"
            print(f"Conversation {conversation_id}: the turn failed.", file=sys.stderr)
            traceback.print_exc()
            events.put_nowait(sse("error", {"message": message}))
            # The history may now end in a half-finished exchange, so the conversation
            # takes no more messages. The user starts a new one.
            await self._conversations.mark_failed(conversation_id)

    async def _read_events(self, events: asyncio.Queue):
        """Hands the events of a turn to the browser, one at a time as they arrive.

        If the browser hangs up, this function is stopped where it waits and nothing
        else happens: the turn goes on in its own task."""
        while True:
            event = await events.get()
            if event is END_OF_TURN:
                return
            yield event

    # ----- Helpers -----

    async def _find(self, conversation_id: int, x_user) -> dict:
        """The user's conversation as a row of the table. Someone else's conversation
        is answered like one that does not exist."""
        row = await self._conversations.find(conversation_id, user_of(x_user))
        if row is None:
            raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} does not exist.")
        return row

    def _turn_is_running(self, conversation_id: int) -> bool:
        task = self._turn_tasks.get(conversation_id)
        return task is not None and not task.done()

    def _describe(self, row: dict) -> dict:
        """A row of the table as the web interface gets it."""
        return {
            "id": row["conversation_id"],
            "title": row["title"],
            "created_at": row["created_at"].isoformat(timespec="seconds"),
            "updated_at": row["updated_at"].isoformat(timespec="seconds"),
            "failed": row["failed"],
            "running": self._turn_is_running(row["conversation_id"]),
        }

    def _thread_id(self, conversation_id: int) -> str:
        return f"web-{conversation_id}"

    def _config(self, conversation_id: int) -> dict:
        # thread_id names the conversation in the checkpointer: same id, same history.
        return {
            "configurable": {"thread_id": self._thread_id(conversation_id)},
            "recursion_limit": MAX_GRAPH_STEPS,
        }


def pending_question(state):
    """The question of an interrupt() the graph is stopped at, or None when the graph
    is not waiting for anything."""
    for task in state.tasks:
        for stop in task.interrupts:
            return stop.value
    return None


async def serve(llm, tools: list, client: TicketApiClient, settings: Settings, tools_from: str) -> None:
    """Builds the graph and answers HTTP requests until the server is stopped."""
    # The pool of database connections lives as long as the server. "finally" closes
    # it however the server ends.
    pool = await open_database(settings.database_url)
    try:
        # The graph keeps its state (the messages) in the database, so a conversation
        # is still there after this server has been restarted.
        checkpointer = await build_checkpointer(pool)
        graph = TicketAgent(llm, tools).build(checkpointer)
        app = ChatServer(graph, client, settings, tools_from, Conversations(pool)).build_app()

        config = uvicorn.Config(app, host="0.0.0.0", port=PORT)
        await uvicorn.Server(config).serve()
    finally:
        await pool.close()


async def run(settings: Settings, client: TicketApiClient, use_direct_tools: bool) -> None:
    """Gets the tools, from the MCP server or the direct ones, and runs the server.
    The graph is the same in both cases: it only sees a list of tools."""
    llm = build_llm(settings)

    if use_direct_tools:
        tools = build_tools(client)
        print("(direct tools: the agent calls the ticket API itself, without the MCP server)")
        await serve(llm, tools, client, settings, "direct")
        return

    # The MCP server is started here, and every conversation uses it. If it dies while
    # this server runs, the connection starts it again before the next tool call
    # (mcp_client.py), so this server does not have to be restarted. "finally" stops
    # the MCP server when the HTTP server stops.
    connection = McpConnection(settings.ticket_api_url)
    await connection.start()
    try:
        tools = await connection.load_tools()
        print(connection.describe(tools))
        await serve(llm, tools, client, settings, "mcp")
    finally:
        await connection.stop()


def main() -> int:
    use_direct_tools = "--direct" in sys.argv[1:]

    try:
        settings = load_settings()
    except ConfigError as error:
        print(error)
        return 1

    if settings.database_url == "":
        print("Missing setting: DATABASE_URL. The web server keeps its conversations in PostgreSQL.")
        return 1

    client = TicketApiClient(settings.ticket_api_url)
    if not wait_for_api(client):
        # The server starts anyway. /api/chat/health reports it, and the tools return
        # "could not be reached" until the API is up.
        print(f"The ticket API does not answer at {settings.ticket_api_url} yet.")

    try:
        asyncio.run(run(settings, client, use_direct_tools))
    except KeyboardInterrupt:
        # Ctrl+C: the HTTP server has already shut down in an orderly way.
        pass
    except Exception as error:
        if use_direct_tools:
            raise
        # Most likely the MCP server did not start, but it can be anything else too.
        # The whole traceback goes to the log first: there the cause must not get
        # lost. The exit code 1 tells whoever started the container that it failed.
        traceback.print_exc()
        # To stderr, like the traceback, so that the two stay in order in the log.
        print(
            f"The server stopped on an error ({type(error).__name__}, see above). "
            "If the MCP server is the cause: with --direct the agent calls the ticket API itself.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
