# Demo run with the direct tools

Output of `docker compose run --rm agent python main.py --demo --direct`, captured on
2026-10-01 with an empty database, against the Azure OpenAI deployment `gpt-6-luna-c1`.

The same seven requests as in [demo.md](demo.md). With `--direct` the agent does not
start the MCP server: it calls the ticket API with its own tools (`agent/tools.py`).

```text
(direct tools: the agent calls the ticket API itself, without the MCP server)

--- Scenario 1 ---
you> Create a new ticket about a keyboard not working.
  [tool call]   create_ticket(title='Keyboard not working', description='The keyboard is not working. Please investigate and resolve the issue.')
  [tool result] {"ticketId": 1, "title": "Keyboard not working", "description": "The keyboard is not working. Please investigate and resolve the issue.", "status": "OPEN", "resolution": null, "created": "2026-10-01T12:04:15.314662Z", "updated": "2026-10-01T12:04:15.314662Z", "versionNo": 1}
agent> Created ticket #1 [OPEN]: Keyboard not working.

--- Scenario 2 ---
you> Retrieve all open tickets.
  [tool call]   list_tickets(status='OPEN')
  [tool result] [{"ticketId": 1, "title": "Keyboard not working", "description": "The keyboard is not working. Please investigate and resolve the issue.", "status": "OPEN", "resolution": null, "created": "2026-10-01T12:04:15.314662Z", "updated": "2026-10-01T12:04:15.314662Z", "versionNo": 1}]
agent> #1 [OPEN] Keyboard not working

--- Scenario 3 ---
you> Get details for ticket 1.
  [tool call]   get_ticket(ticket_id=1)
  [tool result] {"ticket": {"ticketId": 1, "title": "Keyboard not working", "description": "The keyboard is not working. Please investigate and resolve the issue.", "status": "OPEN", "resolution": null, "created": "2026-10-01T12:04:15.314662Z", "updated": "2026-10-01T12:04:15.314662Z", "versionNo": 1}, "comments":  ...
agent> Ticket 1: Keyboard not working
Description: The keyboard is not working. Please investigate and resolve the issue.
Status: OPEN
Resolution: None
Created: 2026-10-01T12:04:15.314662Z
Updated: 2026-10-01T12:04:15.314662Z
Version: 1
Comments: None

--- Scenario 4 ---
you> Update ticket 1 to have the status 'PROGRESS'.
  [tool call]   update_ticket(ticket_id=1, status='PROGRESS')
  [tool result] API ERROR 422: 'PROGRESS' is not a valid status. Valid statuses are: OPEN, RESOLVED, CLOSED.
agent> Ticket 1 was not updated. “PROGRESS” isn’t a valid status; choose OPEN, RESOLVED, or CLOSED.

--- Scenario 5 ---
you> Update ticket 1 to be RESOLVED, adding 'Replaced faulty cable' as the resolution.
  [tool call]   update_ticket(ticket_id=1, status='RESOLVED', resolution='Replaced faulty cable')
  [tool result] {"ticketId": 1, "title": "Keyboard not working", "description": "The keyboard is not working. Please investigate and resolve the issue.", "status": "RESOLVED", "resolution": "Replaced faulty cable", "created": "2026-10-01T12:04:15.314662Z", "updated": "2026-10-01T12:04:26.968554Z", "versionNo": 2}
agent> Ticket #1 is now RESOLVED. Resolution: Replaced faulty cable.

--- Scenario 6 ---
you> Update ticket 1001 to 'CLOSED'.
  [tool call]   update_ticket(ticket_id=1001, status='CLOSED')
  [tool result] API ERROR 404: Ticket 1001 does not exist.
agent> Ticket 1001 does not exist, so nothing was changed. You can list the tickets to find the correct ID.

--- Scenario 7 ---
you> Delete ticket 1.
  [tool call]   delete_ticket(ticket_id=1)
  [confirm]     Delete ticket 1 permanently? [y/N] y   (answered automatically in demo mode)
  [tool result] Ticket 1 was deleted.
agent> Ticket 1 was deleted.
```
