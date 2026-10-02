"""The LangGraph graph: the model and the tools take turns until the model answers.

    START -> agent -+- answer for the user ------------------------> END
                    +- tool calls ---------------------> tools -> agent
                    +- tool calls, one is a delete -> confirm -> tools -> agent

- agent calls the model with the tools bound. The model either writes an answer for the
  user or asks for one or more tool calls.
- confirm stops the graph with interrupt() and waits for the user's yes or no.
- tools runs the tool calls and adds one ToolMessage per call. A delete that was not
  confirmed is not run; the model is told so instead.

The graph is compiled with a checkpointer that keeps the state: in the database for the
web server, in memory for the evals. It does two jobs. It remembers the conversation
between turns: the same thread_id means the same conversation. And it is what makes
interrupt() possible: the state is saved when the graph stops, so the graph can continue
from the same place when the answer comes.
"""

from typing import Annotated, TypedDict

from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from prompts import SYSTEM_PROMPT

# The one tool the graph does not run on the model's word alone: the user is asked
# first (confirm_delete below). The name is the one the MCP server gives the tool.
DELETE_TOOL_NAME = "delete_ticket"

# One step is one node run. A normal request takes three (agent, tools, agent). This is
# the ceiling for a model that keeps calling tools without getting anywhere. Whoever
# runs the graph passes it as recursion_limit.
MAX_GRAPH_STEPS = 20


class AgentState(TypedDict):
    # The conversation so far: user messages, model messages and tool results.
    # add_messages tells LangGraph to append what a node returns to this list
    # instead of replacing the list.
    messages: Annotated[list, add_messages]

    # Written by the confirm node, read by the tools node.
    delete_confirmed: bool


class TicketAgent:
    def __init__(self, llm, tools: list):
        # bind_tools sends the tool descriptions along with every model call,
        # so the model can answer with "call this tool with these arguments".
        self._llm_with_tools = llm.bind_tools(tools)

        self._tools_by_name = {}
        for tool in tools:
            self._tools_by_name[tool.name] = tool

    # ----- Nodes: each one takes the state and returns the part of it that changed -----

    async def call_model(self, state: AgentState) -> dict:
        messages = [SystemMessage(content=SYSTEM_PROMPT)]
        for message in state["messages"]:
            messages.append(message)

        response = await self._llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    def confirm_delete(self, state: AgentState) -> dict:
        last_message = state["messages"][-1]

        ticket_ids = []
        for call in last_message.tool_calls:
            if call["name"] == DELETE_TOOL_NAME:
                ticket_ids.append(call["args"].get("ticket_id"))

        # interrupt() stops the graph here and hands the question to whoever is running
        # it (the web server, which passes it on to the browser). When the graph is
        # continued with an answer, this node runs again from the top, and this time
        # interrupt() returns that answer.
        question = {"action": DELETE_TOOL_NAME, "ticket_ids": ticket_ids}
        answer = interrupt(question)

        confirmed = False
        if answer is True:
            confirmed = True

        return {"delete_confirmed": confirmed}

    async def run_tools(self, state: AgentState) -> dict:
        last_message = state["messages"][-1]
        delete_confirmed = state.get("delete_confirmed", False)

        # The model must get exactly one ToolMessage back for every tool call it made.
        results = []
        for call in last_message.tool_calls:
            name = call["name"]

            if name == DELETE_TOOL_NAME and not delete_confirmed:
                content = "NOT EXECUTED: the user did not confirm the deletion. Nothing was deleted."
            elif name not in self._tools_by_name:
                content = f"ERROR: there is no tool named {name}."
            else:
                tool = self._tools_by_name[name]
                try:
                    content = await tool.ainvoke(call["args"])
                except Exception as error:
                    # Arguments of the wrong type from the model, or a bug in a tool.
                    # The model gets the error as a result and can correct itself.
                    content = f"ERROR: the tool call failed: {error}"

            results.append(ToolMessage(content=str(content), tool_call_id=call["id"], name=name))

        # A confirmation covers one round of tool calls. The next delete asks again.
        return {"messages": results, "delete_confirmed": False}

    # ----- Routing: which node comes after agent -----

    def route_after_model(self, state: AgentState) -> str:
        last_message = state["messages"][-1]

        if len(last_message.tool_calls) == 0:
            return END

        for call in last_message.tool_calls:
            if call["name"] == DELETE_TOOL_NAME:
                return "confirm"

        return "tools"

    # ----- Wiring -----

    def build(self, checkpointer=None):
        """Compiles the graph. Without a checkpointer the state is kept in memory,
        which is what the evals want. The web server passes one that keeps the state
        in the database (conversations.py)."""
        if checkpointer is None:
            checkpointer = InMemorySaver()

        graph = StateGraph(AgentState)

        graph.add_node("agent", self.call_model)
        graph.add_node("confirm", self.confirm_delete)
        graph.add_node("tools", self.run_tools)

        graph.add_edge(START, "agent")
        graph.add_conditional_edges(
            "agent",
            self.route_after_model,
            {"tools": "tools", "confirm": "confirm", END: END},
        )
        graph.add_edge("confirm", "tools")
        graph.add_edge("tools", "agent")

        return graph.compile(checkpointer=checkpointer)
