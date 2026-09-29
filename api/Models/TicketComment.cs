namespace TicketApi.Models
{
    // A comment on the version the ticket had when the comment was written
    // (table ticket_comment).
    public class TicketComment
    {
        public long TicketId { get; set; }
        public int VersionNo { get; set; }
        public long CommentId { get; set; }
        public string Body { get; set; }
        public DateTime TimeOfComment { get; set; }
    }
}
