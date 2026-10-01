"""Command-line interface for the ticket agent.

    python main.py            chat: type a request, or the number of an example scenario
    python main.py --demo     runs every example scenario once, without any input
    python main.py --direct   the same, but the agent calls the API with its own tools
                              (tools.py) instead of going through the MCP server;
                              can be combined with --demo

The tools come from the MCP server (mcp_server.py), which the agent starts as a
subprocess. --direct is the same agent without that step.

The CLI prints each tool call and each tool result as they happen, so it is visible
what the agent did and what the API answered, not only what the agent says afterwards.
"""

import asyncio
import sys
import time
import traceback
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import AzureChatOpenAI
from langgraph.errors import GraphRecursionError
from langgraph.types import Command

from api_client import TicketApiClient
from config import ConfigError, Settings, load_settings
from graph import TicketAgent
from mcp_client import connect_to_mcp_server, load_mcp_tools
from tools import build_tools

# One step is one node run. A normal request takes three (agent, tools, agent). This is
# the ceiling for a model that keeps calling tools without getting anywhere.
MAX_GRAPH_STEPS = 20

# How much of a tool result is shown on screen. The model always gets the whole result.
MAX_SHOWN_RESULT_LENGTH = 300

# The six requests from the assignment, plus a delete to show the confirmation step.
# {valid_id} and {missing_id} are filled in from the tickets that exist when it runs.
SCENARIOS = [
    "Create a new ticket about a keyboard not working.",
    "Retrieve all open tickets.",
    "Get details for ticket {valid_id}.",
    "Update ticket {valid_id} to have the status 'PROGRESS'.",
    "Update ticket {valid_id} to be RESOLVED, adding 'Replaced faulty cable' as the resolution.",
    "Update ticket {missing_id} to 'CLOSED'.",
    "Delete ticket {valid_id}.",
]


def build_llm(settings: Settings) -> AzureChatOpenAI:
    # reasoning_effort="none": this model rejects tool calls on the chat completions
    # endpoint while reasoning is on (HTTP 400), and the API version we were given is
    # older than the Responses API, which is the other way to get tools.
    # No temperature: the model only accepts its default.
    return AzureChatOpenAI(
        azure_endpoint=settings.azure_endpoint,
        api_key=settings.azure_api_key,
        azure_deployment=settings.azure_deployment,
        api_version=settings.azure_api_version,
        reasoning_effort="none",
        timeout=60,
        max_retries=2,
    )


def wait_for_api(client: TicketApiClient) -> bool:
    """True when the ticket API answers. Tries for about 15 seconds, because the API
    container may still be starting when the agent container does."""
    attempts = 0
    while attempts < 15:
        result = client.list_tickets(None)
        if result.status_code != 0:
            return True
        attempts += 1
        time.sleep(1)
    return False


def fill_in_ids(text: str, client: TicketApiClient) -> Optional[str]:
    """Replaces {valid_id} with the newest ticket's id and {missing_id} with an id that
    does not exist. Returns None when a valid id is needed but there are no tickets."""
    needs_valid_id = "{valid_id}" in text
    needs_missing_id = "{missing_id}" in text

    if not needs_valid_id and not needs_missing_id:
        return text

    highest_id = 0
    result = client.list_tickets(None)
    if result.ok:
        for ticket in result.data:
            if ticket["ticketId"] > highest_id:
                highest_id = ticket["ticketId"]

    if needs_valid_id and highest_id == 0:
        return None

    text = text.replace("{valid_id}", str(highest_id))
    text = text.replace("{missing_id}", str(highest_id + 1000))
    return text


def make_config(conversation_number: int) -> dict:
    # thread_id names the conversation in the checkpointer: same id, same history.
    return {
        "configurable": {"thread_id": f"conversation-{conversation_number}"},
        "recursion_limit": MAX_GRAPH_STEPS,
    }


# ----- Printing -----

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


def print_message(message) -> None:
    if isinstance(message, AIMessage):
        for call in message.tool_calls:
            print(f"  [tool call]   {format_call(call)}")
        text = text_of(message).strip()
        if text != "":
            print(f"agent> {text}")
    elif isinstance(message, ToolMessage):
        print(f"  [tool result] {shorten(text_of(message))}")


def print_menu() -> None:
    print("Ticket agent. Type a request, or a number to run one of these:")
    number = 0
    for scenario in SCENARIOS:
        number += 1
        text = scenario.replace("{valid_id}", "<newest ticket>")
        text = text.replace("{missing_id}", "<an id that does not exist>")
        print(f"  {number}. {text}")
    print("Commands: 'new' starts a new conversation, 'menu' shows this list, 'quit' exits.")


# ----- Running the graph -----

def ask_for_confirmation(question: dict, auto_confirm: bool) -> bool:
    ids = []
    for ticket_id in question["ticket_ids"]:
        ids.append(str(ticket_id))
    prompt = "  [confirm]     Delete ticket " + ", ".join(ids) + " permanently? [y/N] "

    if auto_confirm:
        print(prompt + "y   (answered automatically in demo mode)")
        return True

    answer = input(prompt).strip().lower()
    return answer == "y" or answer == "yes"


async def run_turn(graph, config: dict, user_text: str, auto_confirm: bool) -> None:
    """Sends one user message through the graph and prints what happens."""
    graph_input = {"messages": [HumanMessage(content=user_text)]}

    while True:
        question = None

        # stream_mode="updates" gives one item per finished node, holding what that
        # node added to the state. A stop at interrupt() arrives under "__interrupt__".
        async for update in graph.astream(graph_input, config, stream_mode="updates"):
            for node_name in update:
                if node_name == "__interrupt__":
                    question = update[node_name][0].value
                    continue

                node_update = update[node_name]
                if node_update is None:
                    continue
                for message in node_update.get("messages", []):
                    print_message(message)

        if question is None:
            return

        confirmed = ask_for_confirmation(question, auto_confirm)

        # Command(resume=...) continues the graph from the interrupt() that stopped it.
        graph_input = Command(resume=confirmed)


async def run_turn_safely(graph, config: dict, user_text: str, auto_confirm: bool) -> bool:
    """Like run_turn, but a failure becomes a message instead of a crash.
    Returns False when the turn failed."""
    try:
        await run_turn(graph, config, user_text, auto_confirm)
        return True
    except GraphRecursionError:
        print(f"agent> I stopped after {MAX_GRAPH_STEPS} steps without finishing. Try a more specific request.")
        return False
    except Exception as error:
        print(f"agent> The language model call failed ({type(error).__name__}): {error}")
        return False


async def chat(graph, client: TicketApiClient) -> None:
    print_menu()
    conversation_number = 1

    while True:
        try:
            line = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if line == "":
            continue
        if line == "quit" or line == "exit":
            return
        if line == "menu":
            print_menu()
            continue
        if line == "new":
            conversation_number += 1
            print("(new conversation)")
            continue

        user_text = line
        if line.isdigit():
            number = int(line)
            if number < 1 or number > len(SCENARIOS):
                print(f"There is no scenario {number}.")
                continue
            user_text = fill_in_ids(SCENARIOS[number - 1], client)
            if user_text is None:
                print("There are no tickets yet. Run scenario 1 first.")
                continue
            print(f"you> {user_text}")

        succeeded = await run_turn_safely(graph, make_config(conversation_number), user_text, False)
        if not succeeded:
            # The failed turn may have left a half-finished exchange in the history.
            conversation_number += 1
            print("(new conversation)")


async def demo(graph, client: TicketApiClient) -> None:
    number = 0
    for scenario in SCENARIOS:
        number += 1
        user_text = fill_in_ids(scenario, client)
        print()
        print(f"--- Scenario {number} ---")
        if user_text is None:
            print("Skipped: there is no ticket to use.")
            continue
        print(f"you> {user_text}")
        # A new conversation per scenario: each request has to work on its own.
        await run_turn_safely(graph, make_config(number), user_text, True)


async def run_cli(llm, tools: list, client: TicketApiClient, demo_mode: bool) -> None:
    graph = TicketAgent(llm, tools).build()

    if demo_mode:
        await demo(graph, client)
    else:
        await chat(graph, client)


def describe_mcp_tools(mcp_client, tools: list) -> str:
    """One line that says where the tools come from. Printed when the agent starts."""
    names = []
    for tool in tools:
        names.append(tool.name)
    return f"(MCP server '{mcp_client.server_info.name}' offers {len(tools)} tools: " + ", ".join(names) + ")"


async def run(settings: Settings, client: TicketApiClient, demo_mode: bool, use_direct_tools: bool) -> None:
    """Gets the tools, from the MCP server or the direct ones, and runs the CLI.
    The graph is the same in both cases: it only sees a list of tools."""
    llm = build_llm(settings)

    if use_direct_tools:
        tools = build_tools(client)
        print("(direct tools: the agent calls the ticket API itself, without the MCP server)")
        await run_cli(llm, tools, client, demo_mode)
        return

    # "async with" starts the MCP server as a subprocess and stops it again when the
    # block is left, so the server lives exactly as long as the CLI runs.
    async with connect_to_mcp_server(settings.ticket_api_url) as mcp_client:
        tools = await load_mcp_tools(mcp_client)
        print(describe_mcp_tools(mcp_client, tools))
        await run_cli(llm, tools, client, demo_mode)


def main() -> int:
    demo_mode = "--demo" in sys.argv[1:]
    use_direct_tools = "--direct" in sys.argv[1:]

    try:
        settings = load_settings()
    except ConfigError as error:
        print(error)
        return 1

    client = TicketApiClient(settings.ticket_api_url)
    if not wait_for_api(client):
        print(f"The ticket API does not answer at {settings.ticket_api_url}. Start it with: docker compose up -d")
        return 1

    try:
        asyncio.run(run(settings, client, demo_mode, use_direct_tools))
    except Exception as error:
        if use_direct_tools:
            raise
        # A failed turn is handled inside the chat. What ends up here is most likely
        # the MCP server not starting, but it can be anything else too, so the whole
        # traceback is printed first: the cause must not get lost.
        traceback.print_exc()
        # To stderr, like the traceback, so that the two stay in order.
        print(
            f"The agent stopped on an error ({type(error).__name__}, see above). "
            "If the MCP server is the cause: with --direct the agent calls the ticket API itself.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
