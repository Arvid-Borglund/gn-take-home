# Demo run

Output of `docker compose run --rm agent python main.py --demo`, captured on 2026-10-01
from a fresh clone with an empty database, against the Azure OpenAI deployment
`gpt-6-luna-c1`.

The demo sends the six requests from the assignment, plus a delete to show the
confirmation step. Each request runs as its own conversation. The lines marked
`[tool call]` and `[tool result]` are printed by the CLI while the graph runs: they show
which tool the model chose, with which arguments, and what the API answered. Results
longer than 300 characters are cut on screen; the model always gets them in full.

```text
--- Scenario 1 ---
you> Create a new ticket about a keyboard not working.
  [tool call]   create_ticket(title='Keyboard not working', description='The keyboard is not working. Please investigate and resolve the issue.')
  [tool result] {"ticketId": 1, "title": "Keyboard not working", "description": "The keyboard is not working. Please investigate and resolve the issue.", "status": "OPEN", "resolution": null, "created": "2026-10-01T09:59:35.624113Z", "updated": "2026-10-01T09:59:35.624113Z", "versionNo": 1}
agent> Created ticket #1: Keyboard not working. Status: OPEN.

--- Scenario 2 ---
you> Retrieve all open tickets.
  [tool call]   list_tickets(status='open')
  [tool result] [{"ticketId": 1, "title": "Keyboard not working", "description": "The keyboard is not working. Please investigate and resolve the issue.", "status": "OPEN", "resolution": null, "created": "2026-10-01T09:59:35.624113Z", "updated": "2026-10-01T09:59:35.624113Z", "versionNo": 1}]
agent> #1 [OPEN] Keyboard not working

--- Scenario 3 ---
you> Get details for ticket 1.
  [tool call]   get_ticket(ticket_id=1)
  [tool result] {"ticket": {"ticketId": 1, "title": "Keyboard not working", "description": "The keyboard is not working. Please investigate and resolve the issue.", "status": "OPEN", "resolution": null, "created": "2026-10-01T09:59:35.624113Z", "updated": "2026-10-01T09:59:35.624113Z", "versionNo": 1}, "comments":  ...
agent> Ticket 1: Keyboard not working
Description: The keyboard is not working. Please investigate and resolve the issue.
Status: OPEN
Resolution: None
Created: 2026-10-01
Last updated: 2026-10-01
Comments: None

--- Scenario 4 ---
you> Update ticket 1 to have the status 'PROGRESS'.
  [tool call]   update_ticket(ticket_id=1, status='PROGRESS')
  [tool result] API ERROR 422: 'PROGRESS' is not a valid status. Valid statuses are: OPEN, RESOLVED, CLOSED.
agent> The API rejected PROGRESS; valid statuses are OPEN, RESOLVED, and CLOSED. Choose one of those to update ticket 1.

--- Scenario 5 ---
you> Update ticket 1 to be RESOLVED, adding 'Replaced faulty cable' as the resolution.
  [tool call]   update_ticket(ticket_id=1, status='RESOLVED', resolution='Replaced faulty cable')
  [tool result] {"ticketId": 1, "title": "Keyboard not working", "description": "The keyboard is not working. Please investigate and resolve the issue.", "status": "RESOLVED", "resolution": "Replaced faulty cable", "created": "2026-10-01T09:59:35.624113Z", "updated": "2026-10-01T09:59:46.607331Z", "versionNo": 2}
agent> Ticket 1 is now RESOLVED. Resolution: Replaced faulty cable.

--- Scenario 6 ---
you> Update ticket 1001 to 'CLOSED'.
  [tool call]   update_ticket(ticket_id=1001, status='CLOSED')
  [tool result] API ERROR 404: Ticket 1001 does not exist.
agent> Ticket 1001 does not exist, so it wasn’t updated. List tickets to find the correct ticket ID.

--- Scenario 7 ---
you> Delete ticket 1.
  [tool call]   delete_ticket(ticket_id=1)
  [confirm]     Delete ticket 1 permanently? [y/N] y   (answered automatically in demo mode)
  [tool result] Ticket 1 was deleted.
agent> Ticket 1 was deleted.
```
