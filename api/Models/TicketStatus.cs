namespace TicketApi.Models;

// Stored as text in the database; the CHECK constraint ticket_status_valid
// allows exactly these names.
public enum TicketStatus
{
    OPEN,
    RESOLVED,
    CLOSED
}
