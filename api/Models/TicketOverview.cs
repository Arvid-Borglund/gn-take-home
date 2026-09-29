namespace TicketApi.Models
{
    // Read model over the view ticket_overview: the current state plus the
    // timestamps derived from the version history. Keyless and read-only.
    public class TicketOverview
    {
        public long TicketId { get; set; }
        public string Title { get; set; }
        public string Description { get; set; }
        public TicketStatus Status { get; set; }
        public string Resolution { get; set; }
        public DateTime Created { get; set; }
        public DateTime Updated { get; set; }
        public int VersionNo { get; set; }
    }
}
