namespace TicketApi.Models
{
    // One row of a search result: a ticket as in TicketOverview, plus how well it
    // matches the question. There is no table behind it. The rows come from the query
    // in TicketSearchService.
    public class TicketMatch
    {
        public long TicketId { get; set; }
        public string Title { get; set; }
        public string Description { get; set; }
        public TicketStatus Status { get; set; }
        public string Resolution { get; set; }
        public DateTime Created { get; set; }
        public DateTime Updated { get; set; }
        public int VersionNo { get; set; }

        // From 0 to 1: 1 for the same meaning, around 0 for unrelated texts.
        public double Match { get; set; }
    }
}
