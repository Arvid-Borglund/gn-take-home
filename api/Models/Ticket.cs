namespace TicketApi.Models;

// Current state of a ticket (table ticket). Timestamps are not stored here:
// they are derived from the version history, see TicketOverview.
public class Ticket
{
    public long TicketId { get; set; }
    public required string Title { get; set; }
    public required string Description { get; set; }
    public TicketStatus Status { get; set; } = TicketStatus.OPEN;
    public string? Resolution { get; set; }

    public List<TicketVersion> Versions { get; set; } = [];
    public List<TicketComment> Comments { get; set; } = [];
}
