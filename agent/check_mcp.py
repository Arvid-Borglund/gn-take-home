"""Checks the MCP server without a language model and without the ticket API.

    python check_mcp.py

1. Starts mcp_server.py the same way the agent does and asks it for its tools.
2. Compares them with the direct tools in tools.py, the ones --direct uses. The tools
   are written down twice, once for each way of reaching the API, and the model should
   see the same thing either way: the same names, descriptions and arguments.

The exit code is 0 only when the two sets are the same, so the command can gate a
pipeline. CI runs it.
"""

import asyncio
import inspect
import sys

from langchain_core.utils.function_calling import convert_to_openai_tool

from mcp_client import McpConnection
from tools import build_tools


def as_the_model_sees_it(tools: list) -> dict:
    """Tool name -> the definition that is sent to the model for that tool."""
    definitions = {}
    for tool in tools:
        definition = convert_to_openai_tool(tool)["function"]

        # A docstring keeps the indentation of the function it is written in, which
        # differs between the two files. cleandoc removes it, so the texts compare.
        definition["description"] = inspect.cleandoc(definition["description"])

        definitions[tool.name] = definition
    return definitions


async def check() -> int:
    # Listing the tools does not call the API, so the address is never used.
    connection = McpConnection("http://localhost:8080")
    await connection.start()
    try:
        mcp_tools = await connection.load_tools()
    finally:
        await connection.stop()

    # The same goes for the direct tools: without a client they can still be listed.
    direct_tools = build_tools(None)

    from_mcp = as_the_model_sees_it(mcp_tools)
    direct = as_the_model_sees_it(direct_tools)

    print(f"The MCP server offers {len(from_mcp)} tools:")
    for name in from_mcp:
        first_line = from_mcp[name]["description"].split("\n")[0]
        print(f"  {name}: {first_line}")

    problems = []

    for name in direct:
        if name not in from_mcp:
            problems.append(f"{name} is in tools.py but not in the MCP server")

    for name in from_mcp:
        if name not in direct:
            problems.append(f"{name} is in the MCP server but not in tools.py")
            continue
        if from_mcp[name]["description"] != direct[name]["description"]:
            problems.append(f"{name} has different descriptions in the two places")
        if from_mcp[name]["parameters"] != direct[name]["parameters"]:
            problems.append(f"{name} has different arguments in the two places")

    if len(problems) > 0:
        print()
        for problem in problems:
            print(f"MISMATCH: {problem}")
        return 1

    print()
    print("They match the direct tools in tools.py: names, descriptions and arguments.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(check()))
