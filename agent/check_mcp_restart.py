"""Checks that the agent survives the MCP server dying, without a language model and
without the ticket API.

    python check_mcp_restart.py

The MCP server is a subprocess of the agent. This script kills it the hard way
(SIGKILL, as the operating system would when it runs out of memory) and checks what
McpConnection in mcp_client.py does about it:

1. A healthy server is not restarted: two calls, no restart.
2. After the server is killed, the next call starts it again and gets an answer.
3. Two calls at the same time after a kill start one new server, not two.
4. When the server cannot be started again, the call fails with a clear error, and the
   call after that works once the server can be started.

A "call" here is list_tickets against an address where no ticket API listens. The
answer is then "the API could not be reached", which is fine: it still went to the MCP
server and back, and that is the part being checked.

It finds the server process through /proc, so it runs on Linux, which is what the
image and CI are. The exit code is 0 only when every check passes. CI runs it.
"""

import asyncio
import os
import signal
import sys

import mcp_client
from mcp_client import McpConnection, McpServerError, text_of_result

# Nothing listens here, so the ticket API is "down" and answers at once.
NO_API_URL = "http://127.0.0.1:9"


def server_process_ids() -> list:
    """The ids of the running mcp_server.py processes."""
    ids = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/cmdline") as file:
                command_line = file.read()
        except OSError:
            # The process ended between the listing and the reading.
            continue
        if "mcp_server.py" in command_line:
            ids.append(int(name))
    return ids


async def kill_server() -> None:
    for process_id in server_process_ids():
        os.kill(process_id, signal.SIGKILL)
    # A moment for the connection to notice that the other end is gone.
    await asyncio.sleep(0.5)


async def call(connection: McpConnection) -> str:
    result = await connection.call_tool("list_tickets", {})
    return text_of_result(result)


def report(problems: list, name: str, ok: bool, detail: str) -> None:
    if ok:
        print(f"ok      {name}")
    else:
        print(f"FAILED  {name}: {detail}")
        problems.append(name)


async def check() -> int:
    problems = []

    connection = McpConnection(NO_API_URL)
    await connection.start()
    try:
        # 1. A healthy server is left alone.
        await call(connection)
        answer = await call(connection)
        report(problems, "a healthy server answers", "could not be reached" in answer, answer)
        report(problems, "a healthy server is not restarted", connection.restarts == 0, f"{connection.restarts} restarts")

        # 2. Killed, then the next call.
        await kill_server()
        report(problems, "the server process is gone after the kill", len(server_process_ids()) == 0, f"{server_process_ids()}")

        answer = await call(connection)
        report(problems, "the next call gets an answer", "could not be reached" in answer, answer)
        report(problems, "the server was started again once", connection.restarts == 1, f"{connection.restarts} restarts")

        # 3. Killed, then two calls at the same time.
        await kill_server()
        answers = await asyncio.gather(call(connection), call(connection))
        both_answered = "could not be reached" in answers[0] and "could not be reached" in answers[1]
        report(problems, "two calls at the same time both get an answer", both_answered, f"{answers}")
        report(problems, "they started one server, not two", connection.restarts == 2, f"{connection.restarts} restarts")
        report(problems, "one server process is running", len(server_process_ids()) == 1, f"{server_process_ids()}")

        # 4. Killed, and the server cannot be started: the file it is started from is
        # pointed somewhere else for a moment.
        real_server_file = mcp_client.MCP_SERVER_FILE
        mcp_client.MCP_SERVER_FILE = "/does/not/exist.py"
        await kill_server()

        error_text = ""
        try:
            await call(connection)
        except McpServerError as error:
            error_text = str(error)
        report(problems, "a server that cannot be started gives a clear error", "could not be started again" in error_text, error_text)

        mcp_client.MCP_SERVER_FILE = real_server_file
        answer = await call(connection)
        report(problems, "the call after that works again", "could not be reached" in answer, answer)
        report(problems, "which took one more restart", connection.restarts == 3, f"{connection.restarts} restarts")
    finally:
        await connection.stop()

    report(problems, "no server process is left after stop()", len(server_process_ids()) == 0, f"{server_process_ids()}")

    print()
    if len(problems) > 0:
        print(f"{len(problems)} checks failed.")
        return 1

    print("The connection restarts a dead MCP server, once, and reports it when it cannot.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(check()))
