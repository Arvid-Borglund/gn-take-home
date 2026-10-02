using System.Text.Json;

namespace TicketApi.Contracts
{
    // Response bodies. Built by TicketService from the entities.

    public class TicketResponse
    {
        public long TicketId { get; set; }
        public string Title { get; set; }
        public string Description { get; set; }
        public string Status { get; set; }
        public string Resolution { get; set; }
        public DateTime Created { get; set; }
        public DateTime Updated { get; set; }
        public int VersionNo { get; set; }
    }

    // A ticket in a search result: every field of TicketResponse, plus how well the
    // ticket matches the question, from 0 to 1.
    public class TicketMatchResponse : TicketResponse
    {
        public double Match { get; set; }
    }

    public class TicketDetailResponse
    {
        public TicketResponse Ticket { get; set; }
        public List<CommentResponse> Comments { get; set; }
    }

    public class CommentResponse
    {
        public long CommentId { get; set; }
        public int VersionNo { get; set; }
        public string Body { get; set; }
        public DateTime TimeOfComment { get; set; }
    }

    public class VersionResponse
    {
        public int VersionNo { get; set; }
        public DateTime TimeOfVersion { get; set; }
        public JsonElement Snapshot { get; set; }
    }

    public class HealthResponse
    {
        public string Status { get; set; }
        public string Database { get; set; }
    }
}
