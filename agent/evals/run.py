"""Evals for the agent: fixed questions, run against the real graph, the real model and
the real API, with fixed expectations on what the agent does.

    docker compose run --rm agent python evals/run.py
    docker compose run --rm agent python evals/run.py -k delete   only cases with "delete" in the id
    docker compose run --rm agent python evals/run.py -v          show every check and every answer
    docker compose run --rm agent python evals/run.py --direct    without the MCP server: the agent's own tools

The checks are about things that can be decided without judging prose: which tools were
called, with which arguments, and which state the tickets are in afterwards. The wording
of the answer is only checked where something specific must be in it, such as the valid
statuses after a rejected update.

The exit code is 0 only when every case passes, so the command can gate a pipeline.
"""

import argparse
import asyncio
import os
import sys
import time

import yaml

# The agent's modules live one directory up from this file.
AGENT_DIRECTORY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AGENT_DIRECTORY)

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from langgraph.types import Command  # noqa: E402

from api_client import TicketApiClient, wait_for_api  # noqa: E402
from config import ConfigError, load_settings  # noqa: E402
from graph import MAX_GRAPH_STEPS, TicketAgent  # noqa: E402
from mcp_client import McpConnection  # noqa: E402
from model import build_llm  # noqa: E402
from tools import build_tools  # noqa: E402
from transcript import text_of  # noqa: E402

CASES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases.yaml")

# The tickets every case starts from. "key" is the placeholder name in cases.yaml.
SEED_TICKETS = [
    {
        "key": "printer",
        "title": "Printer out of toner",
        "description": "The printer on the second floor prints blank pages.",
        "status": "OPEN",
        "resolution": None,
    },
    {
        "key": "monitor",
        "title": "Monitor flickers",
        "description": "The external monitor flickers every few minutes.",
        "status": "OPEN",
        "resolution": None,
    },
    {
        "key": "vpn",
        "title": "VPN disconnects",
        "description": "The VPN drops the connection about once an hour.",
        "status": "RESOLVED",
        "resolution": "Updated the VPN client",
    },
    {
        "key": "laptop",
        "title": "Laptop battery swollen",
        "description": "The battery pushes the trackpad up. The laptop was replaced.",
        "status": "CLOSED",
        "resolution": None,
    },
]


class CaseRun:
    """What happened when one question went through the agent."""

    def __init__(self):
        self.answer = ""    # the agent's final text
        self.calls = []     # the tool calls it made, in order: {"name": ..., "args": {...}}
        self.error = ""     # set when the run crashed
        self.seconds = 0.0


class Check:
    def __init__(self, name: str, ok: bool, detail: str):
        self.name = name
        self.ok = ok
        self.detail = detail


# ----- Tickets before and after a case -----

def highest_ticket_id(client: TicketApiClient) -> int:
    highest = 0
    result = client.list_tickets(None)
    if result.ok:
        for ticket in result.data:
            if ticket["ticketId"] > highest:
                highest = ticket["ticketId"]
    return highest


def seed_tickets(client: TicketApiClient) -> dict:
    """Creates the seed tickets. Returns placeholder name -> ticket id."""
    ids = {}

    for seed in SEED_TICKETS:
        created = client.create_ticket(seed["title"], seed["description"])
        if not created.ok:
            raise RuntimeError(f"Could not create the seed ticket '{seed['title']}': {created.error}")
        ticket_id = created.data["ticketId"]
        ids[seed["key"]] = ticket_id

        if seed["status"] != "OPEN":
            updated = client.update_ticket(ticket_id, None, None, seed["status"], seed["resolution"])
            if not updated.ok:
                raise RuntimeError(f"Could not set up the seed ticket '{seed['title']}': {updated.error}")

    ids["missing"] = highest_ticket_id(client) + 100000
    return ids


def remove_tickets_above(client: TicketApiClient, highest_before: int) -> None:
    """Removes every ticket created since the case started: the seeds, and whatever
    the agent created itself."""
    result = client.list_tickets(None)
    if not result.ok:
        return
    for ticket in result.data:
        if ticket["ticketId"] > highest_before:
            client.delete_ticket(ticket["ticketId"])


def fill_in(value, ids: dict):
    """Replaces {printer}, {monitor} and so on with the real ids, in a text or in any
    texts inside a list or a dictionary."""
    if isinstance(value, str):
        for key in ids:
            value = value.replace("{" + key + "}", str(ids[key]))
        return value

    if isinstance(value, list):
        filled = []
        for item in value:
            filled.append(fill_in(item, ids))
        return filled

    if isinstance(value, dict):
        filled = {}
        for key in value:
            filled[key] = fill_in(value[key], ids)
        return filled

    return value


# ----- Running one question -----

async def run_question(graph, thread_id: str, question: str, confirm: bool) -> CaseRun:
    run = CaseRun()
    started = time.time()
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": MAX_GRAPH_STEPS}
    graph_input = {"messages": [HumanMessage(content=question)]}

    try:
        while True:
            interrupted = False

            async for update in graph.astream(graph_input, config, stream_mode="updates"):
                for node_name in update:
                    if node_name == "__interrupt__":
                        interrupted = True
                        continue

                    node_update = update[node_name]
                    if node_update is None:
                        continue

                    for message in node_update.get("messages", []):
                        if isinstance(message, AIMessage):
                            for call in message.tool_calls:
                                run.calls.append({"name": call["name"], "args": call["args"]})
                            text = text_of(message).strip()
                            if text != "":
                                run.answer = text

            if not interrupted:
                break

            # The agent asked before a delete. Answer what the case says.
            graph_input = Command(resume=confirm)
    except Exception as error:
        run.error = f"{type(error).__name__}: {error}"

    run.seconds = time.time() - started
    return run


# ----- Checking the result -----

def value_matches(expected, actual) -> bool:
    """A text matches when the expected text is found in the actual one, ignoring case.
    Anything else (numbers) is compared as written."""
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.lower() in actual.lower()
    return str(expected) == str(actual)


def a_call_matches(calls: list, tool: str, wanted_args: dict) -> bool:
    for call in calls:
        if call["name"] != tool:
            continue

        all_match = True
        for key in wanted_args:
            if key not in call["args"] or not value_matches(wanted_args[key], call["args"][key]):
                all_match = False

        if all_match:
            return True
    return False


def check_ticket(client: TicketApiClient, wanted: dict) -> Check:
    ticket_id = int(wanted["id"])
    name = f"ticket {ticket_id}"
    result = client.get_ticket(ticket_id)

    if "exists" in wanted:
        if wanted["exists"]:
            return Check(name + " exists", result.ok, f"API answered {result.status_code}")
        return Check(name + " is gone", result.status_code == 404, f"API answered {result.status_code}")

    if not result.ok:
        return Check(name, False, f"API answered {result.status_code}: {result.error}")

    ticket = result.data["ticket"]
    problems = []

    if "status" in wanted and ticket["status"] != wanted["status"]:
        problems.append(f"status is {ticket['status']}, expected {wanted['status']}")

    if "resolution" in wanted and ticket["resolution"] != wanted["resolution"]:
        problems.append(f"resolution is {ticket['resolution']!r}, expected {wanted['resolution']!r}")

    if "comment" in wanted:
        found = False
        for comment in result.data["comments"]:
            if wanted["comment"].lower() in comment["body"].lower():
                found = True
        if not found:
            problems.append(f"no comment contains {wanted['comment']!r}")

    if len(problems) > 0:
        return Check(name, False, "; ".join(problems))
    return Check(name, True, "as expected")


def check_case(expect: dict, run: CaseRun, client: TicketApiClient) -> list:
    checks = []

    tool_names = []
    for call in run.calls:
        tool_names.append(call["name"])
    answer = run.answer.lower()

    checks.append(Check("no error", run.error == "", run.error))

    if "tools" in expect:
        checks.append(Check("tools", tool_names == expect["tools"], f"called {tool_names}"))

    if "tools_include" in expect:
        missing = []
        for tool in expect["tools_include"]:
            if tool not in tool_names:
                missing.append(tool)
        checks.append(Check("tools_include", len(missing) == 0, f"called {tool_names}"))

    if "tools_not" in expect:
        unwanted = []
        for tool in tool_names:
            if tool in expect["tools_not"]:
                unwanted.append(tool)
        checks.append(Check("tools_not", len(unwanted) == 0, f"called {tool_names}"))

    if "max_tool_calls" in expect:
        checks.append(Check("max_tool_calls", len(tool_names) <= expect["max_tool_calls"], f"{len(tool_names)} calls"))

    if "calls" in expect:
        for wanted in expect["calls"]:
            ok = a_call_matches(run.calls, wanted["tool"], wanted["args"])
            checks.append(Check(f"call {wanted['tool']}", ok, f"wanted {wanted['args']}, got {run.calls}"))

    if "answer_has" in expect:
        missing = []
        for text in expect["answer_has"]:
            if text.lower() not in answer:
                missing.append(text)
        checks.append(Check("answer_has", len(missing) == 0, f"missing {missing}"))

    if "answer_has_any" in expect:
        found = False
        for text in expect["answer_has_any"]:
            if text.lower() in answer:
                found = True
        checks.append(Check("answer_has_any", found, f"none of {expect['answer_has_any']}"))

    if "answer_lacks" in expect:
        unwanted = []
        for text in expect["answer_lacks"]:
            if text.lower() in answer:
                unwanted.append(text)
        checks.append(Check("answer_lacks", len(unwanted) == 0, f"found {unwanted}"))

    if "tickets" in expect:
        for wanted in expect["tickets"]:
            checks.append(check_ticket(client, wanted))

    return checks


# ----- The whole suite -----

async def run_suite(arguments) -> int:
    try:
        settings = load_settings()
    except ConfigError as error:
        print(error)
        return 1

    client = TicketApiClient(settings.ticket_api_url)
    if not wait_for_api(client):
        print(f"The ticket API does not answer at {settings.ticket_api_url}.")
        return 1

    with open(CASES_FILE, encoding="utf-8") as file:
        cases = yaml.safe_load(file)["cases"]

    if arguments.keyword:
        selected = []
        for case in cases:
            if arguments.keyword in case["id"]:
                selected.append(case)
        cases = selected

    llm = build_llm(settings)

    if arguments.direct:
        tools = build_tools(client)
        return await run_cases(cases, llm, tools, client, arguments, settings)

    # The tools come from the MCP server, as in the web server.
    connection = McpConnection(settings.ticket_api_url)
    await connection.start()
    try:
        tools = await connection.load_tools()
        return await run_cases(cases, llm, tools, client, arguments, settings)
    finally:
        await connection.stop()


async def run_cases(cases: list, llm, tools: list, client: TicketApiClient, arguments, settings) -> int:
    graph = TicketAgent(llm, tools).build()

    passed = 0
    for case in cases:
        highest_before = highest_ticket_id(client)
        ids = seed_tickets(client)

        question = fill_in(case["question"], ids)
        expect = fill_in(case.get("expect", {}), ids)
        confirm = case.get("confirm", False)

        # A thread per case: every case is its own conversation.
        run = await run_question(graph, case["id"], question, confirm)
        checks = check_case(expect, run, client)

        remove_tickets_above(client, highest_before)

        case_ok = True
        for check in checks:
            if not check.ok:
                case_ok = False
        if case_ok:
            passed += 1

        tool_names = []
        for call in run.calls:
            tool_names.append(call["name"])
        label = "PASS" if case_ok else "FAIL"
        print(f"[{label}] {case['id']:<28} {run.seconds:5.1f}s  tools={tool_names}")

        for check in checks:
            if not check.ok:
                print(f"         FAILED {check.name}: {check.detail}")
            elif arguments.verbose:
                print(f"         ok     {check.name}")
        if arguments.verbose or not case_ok:
            print(f"         question: {question}")
            print(f"         answer:   {run.answer[:400]}")

    tools_from = "tools from the MCP server"
    if arguments.direct:
        tools_from = "direct tools"

    print()
    print(f"{passed}/{len(cases)} cases passed (model {settings.azure_deployment}, {tools_from})")

    if passed == len(cases):
        return 0
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Runs the agent evals in cases.yaml.")
    parser.add_argument("-k", "--keyword", help="run only the cases whose id contains this text")
    parser.add_argument("-v", "--verbose", action="store_true", help="show every check and every answer")
    parser.add_argument("--direct", action="store_true", help="let the agent call the API with its own tools instead of going through the MCP server")
    sys.exit(asyncio.run(run_suite(parser.parse_args())))
