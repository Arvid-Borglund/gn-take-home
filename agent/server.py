"""HTTP server for the ticket agent: the same graph as the CLI, behind /api/chat.

    python server.py        starts the server on port 8000

The web interface (web/) talks to this server. A message goes in with a POST, and the
answer comes back as a stream of server-sent events, one per thing that happens in the
graph: a tool call, a tool result, the agent's answer, or a question to the user.

    event: tool_call     the model asked for a tool
    event: tool_result   what the tool returned
    event: answer        the agent's text so far, and the tickets it is about
    event: confirm       the graph stopped before a delete and waits for a yes or no
    event: error         the turn failed
    event: done          the stream is over

The conversations live in this process: the list of them in ChatServer, their messages
in the graph's in-memory checkpointer. They are gone when the server restarts.
"""

import json
import sys
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError
from langgraph.types import Command
from pydantic import BaseModel

from api_client import TicketApiClient
from config import ConfigError, Settings, load_settings
from graph import TicketAgent
from main import MAX_GRAPH_STEPS, SCENARIOS, build_llm, fill_in_ids, wait_for_api
from tools import build_tools
from transcript import Reply, build_chat_messages, reply_in_progress

PORT = 8000

# A conversation is named after its first message, cut to this length.
MAX_TITLE_LENGTH = 60


# ----- Request bodies -----

class NewMessage(BaseModel):
    content: str


class Confirmation(BaseModel):
    confirmed: bool


# ----- Conversations -----

class Conversation:
    def __init__(self, conversation_id: int, created_at: str):
        self.id = conversation_id
        self.title = ""
        self.created_at = created_at
        self.updated_at = created_at
        # Set when a turn crashed. The history may then end in a half-finished exchange,
        # so the conversation takes no more messages. The CLI does the same thing: it
        # starts a new conversation after a failed turn.
        self.failed = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "failed": self.failed,
        }


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sse(event: str, data: dict) -> str:
    """One server-sent event: a name, a line of JSON, and an empty line to end it."""
    return "event: " + event + "\ndata: " + json.dumps(data) + "\n\n"


class ChatServer:
    def __init__(self, graph, client: TicketApiClient, settings: Settings):
        self._graph = graph
        self._client = client
        self._settings = settings
        self._conversations = {}   # conversation id -> Conversation
        self._next_id = 1

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
        }

    def scenarios(self) -> list:
        """The requests from the assignment, with real ticket ids filled in. A scenario
        that needs a ticket is left out while there are no tickets."""
        texts = []
        for scenario in SCENARIOS:
            text = fill_in_ids(scenario, self._client)
            if text is not None:
                texts.append(text)
        return texts

    async def list_conversations(self) -> list:
        conversations = []
        for conversation_id in self._conversations:
            conversations.append(self._conversations[conversation_id].to_dict())

        # ISO timestamps sort correctly as text. The latest one used comes first.
        conversations.sort(key=sort_key, reverse=True)
        return conversations

    async def create_conversation(self) -> dict:
        conversation = Conversation(self._next_id, now())
        self._next_id += 1
        self._conversations[conversation.id] = conversation
        return conversation.to_dict()

    async def get_conversation(self, conversation_id: int) -> dict:
        conversation = self._find(conversation_id)
        state = await self._graph.aget_state(self._config(conversation))

        result = conversation.to_dict()
        result["messages"] = build_chat_messages(state.values.get("messages", []))
        result["pending_confirmation"] = pending_question(state)
        return result

    async def delete_conversation(self, conversation_id: int) -> Response:
        conversation = self._find(conversation_id)
        await self._graph.checkpointer.adelete_thread(self._thread_id(conversation))
        del self._conversations[conversation_id]
        return Response(status_code=204)

    async def post_message(self, conversation_id: int, body: NewMessage) -> StreamingResponse:
        conversation = self._find(conversation_id)
        content = body.content.strip()

        if content == "":
            raise HTTPException(status_code=422, detail="The message is empty.")
        if conversation.failed:
            raise HTTPException(status_code=409, detail="This conversation stopped on an error. Start a new one.")

        state = await self._graph.aget_state(self._config(conversation))
        if pending_question(state) is not None:
            raise HTTPException(status_code=409, detail="The agent is waiting for a yes or no to a deletion.")

        if conversation.title == "":
            conversation.title = content[:MAX_TITLE_LENGTH]

        graph_input = {"messages": [HumanMessage(content=content)]}
        return self._stream(conversation, graph_input, Reply())

    async def post_confirmation(self, conversation_id: int, body: Confirmation) -> StreamingResponse:
        conversation = self._find(conversation_id)

        state = await self._graph.aget_state(self._config(conversation))
        if pending_question(state) is None:
            raise HTTPException(status_code=409, detail="The agent is not waiting for a confirmation.")

        # The turn continues where it stopped, so the reply starts from the steps that
        # were already taken, not from nothing.
        reply = reply_in_progress(state.values.get("messages", []))

        # Command(resume=...) continues the graph from the interrupt() that stopped it.
        graph_input = Command(resume=body.confirmed)
        return self._stream(conversation, graph_input, reply)

    # ----- Running the graph -----

    def _stream(self, conversation: Conversation, graph_input, reply: Reply) -> StreamingResponse:
        headers = {
            "Cache-Control": "no-cache",
            # Tells nginx to pass every event on at once instead of collecting them.
            "X-Accel-Buffering": "no",
        }
        events = self._run_turn(conversation, graph_input, reply)
        return StreamingResponse(events, media_type="text/event-stream", headers=headers)

    async def _run_turn(self, conversation: Conversation, graph_input, reply: Reply):
        """Runs the graph and yields what happens as server-sent events. This is the
        same loop as run_turn in main.py, with "send to the browser" where the CLI
        prints."""
        try:
            # stream_mode="updates" gives one item per finished node, holding what that
            # node added to the state. A stop at interrupt() arrives under "__interrupt__".
            async for update in self._graph.astream(graph_input, self._config(conversation), stream_mode="updates"):
                for node_name in update:
                    if node_name == "__interrupt__":
                        question = update[node_name][0].value
                        yield sse("confirm", question)
                        continue

                    node_update = update[node_name]
                    if node_update is None:
                        continue

                    for message in node_update.get("messages", []):
                        for event in reply.add(message):
                            yield sse(event["event"], event["data"])

        except GraphRecursionError:
            conversation.failed = True
            message = f"I stopped after {MAX_GRAPH_STEPS} steps without finishing. Try a more specific request."
            yield sse("error", {"message": message})
        except Exception as error:
            conversation.failed = True
            message = f"The language model call failed ({type(error).__name__}): {error}"
            yield sse("error", {"message": message})

        conversation.updated_at = now()
        yield sse("done", {})

    # ----- Helpers -----

    def _find(self, conversation_id: int) -> Conversation:
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} does not exist.")
        return conversation

    def _thread_id(self, conversation: Conversation) -> str:
        return f"web-{conversation.id}"

    def _config(self, conversation: Conversation) -> dict:
        # thread_id names the conversation in the checkpointer: same id, same history.
        return {
            "configurable": {"thread_id": self._thread_id(conversation)},
            "recursion_limit": MAX_GRAPH_STEPS,
        }


def sort_key(conversation: dict) -> str:
    return conversation["updated_at"]


def pending_question(state):
    """The question of an interrupt() the graph is stopped at, or None when the graph
    is not waiting for anything."""
    for task in state.tasks:
        for stop in task.interrupts:
            return stop.value
    return None


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as error:
        print(error)
        return 1

    client = TicketApiClient(settings.ticket_api_url)
    if not wait_for_api(client):
        # The server starts anyway. /api/chat/health reports it, and the tools return
        # "could not be reached" until the API is up.
        print(f"The ticket API does not answer at {settings.ticket_api_url} yet.")

    llm = build_llm(settings)
    tools = build_tools(client)
    graph = TicketAgent(llm, tools).build()

    app = ChatServer(graph, client, settings).build_app()
    uvicorn.run(app, host="0.0.0.0", port=PORT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
