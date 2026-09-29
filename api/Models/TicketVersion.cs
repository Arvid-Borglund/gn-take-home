using System.Text.Json;

namespace TicketApi.Models;

// One row per state a ticket has been in (table ticket_version).
// Read-only from the API's point of view: the database trigger writes these.
public class TicketVersion
{
    public long TicketId { get; set; }
    public int VersionNo { get; set; }
    public required JsonDocument Snapshot { get; set; }
    public DateTime TimeOfVersion { get; set; }
}
