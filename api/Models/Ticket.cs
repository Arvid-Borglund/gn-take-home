namespace TicketApi.Models
{
    // Current state of a ticket (table ticket). Timestamps are not stored here:
    // they are derived from the version history, see TicketOverview.
    public class Ticket
    {
        public long TicketId { get; set; }
        public string Title { get; set; }
        public string Description { get; set; }
        public TicketStatus Status { get; set; }
        public string Resolution { get; set; }

        public List<TicketVersion> Versions { get; set; }
        public List<TicketComment> Comments { get; set; }

        public Ticket()
        {
            Versions = new List<TicketVersion>();
            Comments = new List<TicketComment>();
        }
    }
}
