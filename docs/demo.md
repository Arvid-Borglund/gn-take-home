# Demo run

Output of `docker compose run --rm agent python main.py --demo`, captured on 2026-10-01
against the Azure OpenAI deployment `gpt-6-luna-c1`.

The demo sends the six requests from the assignment, plus a delete to show the
confirmation step. Each request runs as its own conversation. The lines marked
`[tool call]` and `[tool result]` are printed by the CLI while the graph runs: they show
which tool the model chose, with which arguments, and what the API answered. Results
longer than 300 characters are cut on screen; the model always gets them in full.

The database already held a ticket from earlier testing (#2), which is why the new
ticket got id 6.

```text
--- Scenario 1 ---
you> Create a new ticket about a keyboard not working.
  [tool call]   create_ticket(title='Keyboard not working', description='The keyboard is not working. Please investigate and resolve the issue.')
  [tool result] {"ticketId": 6, "title": "Keyboard not working", "description": "The keyboard is not working. Please investigate and resolve the issue.", "status": "OPEN", "resolution": null, "created": "2026-10-01T09:48:42.567935Z", "updated": "2026-10-01T09:48:42.567935Z", "versionNo": 1}
agent> Created ticket #6, currently OPEN: Keyboard not working.

--- Scenario 2 ---
you> Retrieve all open tickets.
  [tool call]   list_tickets(status='open')
  [tool result] [{"ticketId": 2, "title": "Mouse lagging", "description": "Cursor jumps around", "status": "OPEN", "resolution": null, "created": "2026-09-29T14:11:37.369555Z", "updated": "2026-09-29T14:11:37.369555Z", "versionNo": 1}, {"ticketId": 6, "title": "Keyboard not working", "description": "The keyboard is ...
agent> #2 [OPEN] Mouse lagging
#6 [OPEN] Keyboard not working

--- Scenario 3 ---
you> Get details for ticket 6.
  [tool call]   get_ticket(ticket_id=6)
  [tool result] {"ticket": {"ticketId": 6, "title": "Keyboard not working", "description": "The keyboard is not working. Please investigate and resolve the issue.", "status": "OPEN", "resolution": null, "created": "2026-10-01T09:48:42.567935Z", "updated": "2026-10-01T09:48:42.567935Z", "versionNo": 1}, "comments":  ...
agent> Ticket 6: Keyboard not working
Status: OPEN
Description: The keyboard is not working. Please investigate and resolve the issue.
Created: 2026-10-01
Updated: 2026-10-01
Comments: None

--- Scenario 4 ---
you> Update ticket 6 to have the status 'PROGRESS'.
  [tool call]   update_ticket(ticket_id=6, status='PROGRESS')
  [tool result] API ERROR 422: 'PROGRESS' is not a valid status. Valid statuses are: OPEN, RESOLVED, CLOSED.
agent> Ticket 6 wasn’t changed. “PROGRESS” isn’t a valid status; choose OPEN, RESOLVED, or CLOSED.

--- Scenario 5 ---
you> Update ticket 6 to be RESOLVED, adding 'Replaced faulty cable' as the resolution.
  [tool call]   update_ticket(ticket_id=6, status='RESOLVED', resolution='Replaced faulty cable')
  [tool result] {"ticketId": 6, "title": "Keyboard not working", "description": "The keyboard is not working. Please investigate and resolve the issue.", "status": "RESOLVED", "resolution": "Replaced faulty cable", "created": "2026-10-01T09:48:42.567935Z", "updated": "2026-10-01T09:50:14.111699Z", "versionNo": 2}
agent> Ticket 6 is now RESOLVED. Resolution: Replaced faulty cable.

--- Scenario 6 ---
you> Update ticket 1006 to 'CLOSED'.
  [tool call]   update_ticket(ticket_id=1006, status='CLOSED')
  [tool result] API ERROR 404: Ticket 1006 does not exist.
agent> Ticket 1006 does not exist, so no change was made. List the tickets to find the correct ID.

--- Scenario 7 ---
you> Delete ticket 6.
  [tool call]   delete_ticket(ticket_id=6)
  [confirm]     Delete ticket 6 permanently? [y/N] y   (answered automatically in demo mode)
  [tool result] Ticket 6 was deleted.
agent> Ticket 6 was deleted.
```
