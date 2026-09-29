namespace TicketApi.Contracts
{
    // Request bodies. Nothing is validated here on purpose: TicketService checks
    // the payload and answers 422 with a message, instead of ASP.NET's automatic 400.

    public class CreateTicketRequest
    {
        public string Title { get; set; }
        public string Description { get; set; }
    }

    // PATCH semantics: only the fields that are present (not null) are changed.
    public class UpdateTicketRequest
    {
        public string Title { get; set; }
        public string Description { get; set; }
        public string Status { get; set; }
        public string Resolution { get; set; }
    }

    public class AddCommentRequest
    {
        public string Body { get; set; }
    }
}
