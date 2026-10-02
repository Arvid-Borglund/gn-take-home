"""The example requests the web interface offers, one click each.

They are the six requests from the assignment, plus a delete to show the confirmation
step. The assignment writes them with placeholders for a ticket id. Here the placeholders
are filled in from the tickets that exist when the list is asked for, so every example
is a request that can be sent as it stands.
"""

from api_client import TicketApiClient

# {valid_id} becomes the id of the newest ticket, {missing_id} an id that does not exist.
SCENARIOS = [
    "Create a new ticket about a keyboard not working.",
    "Retrieve all open tickets.",
    "Get details for ticket {valid_id}.",
    "Update ticket {valid_id} to have the status 'PROGRESS'.",
    "Update ticket {valid_id} to be RESOLVED, adding 'Replaced faulty cable' as the resolution.",
    "Update ticket {missing_id} to 'CLOSED'.",
    "Delete ticket {valid_id}.",
]


def list_scenarios(client: TicketApiClient) -> list:
    """All seven examples, with real ticket ids filled in."""
    highest_id = 0
    result = client.list_tickets(None)
    if result.ok:
        for ticket in result.data:
            if ticket["ticketId"] > highest_id:
                highest_id = ticket["ticketId"]

    # With no tickets yet there is no valid id to offer. The examples then say ticket 1,
    # and the agent answers that it does not exist. Once the first example has created
    # a ticket, the others are about that ticket.
    valid_id = highest_id
    if valid_id == 0:
        valid_id = 1

    texts = []
    for scenario in SCENARIOS:
        text = scenario.replace("{valid_id}", str(valid_id))
        text = text.replace("{missing_id}", str(highest_id + 1000))
        texts.append(text)
    return texts
