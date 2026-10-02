namespace TicketApi.Errors
{
    // The failures the API reports. TicketExceptionHandler turns them into
    // ProblemDetails responses with the message as "detail": 404 and 422 for the two
    // business rules, 503 when the search cannot be carried out.

    public class TicketNotFoundException : Exception
    {
        public long TicketId { get; private set; }

        public TicketNotFoundException(long ticketId)
            : base("Ticket " + ticketId + " does not exist.")
        {
            TicketId = ticketId;
        }
    }

    public class TicketValidationException : Exception
    {
        public TicketValidationException(string message)
            : base(message)
        {
        }
    }

    // The embedder service gave no answer, so a question cannot be turned into an
    // embedding and nothing can be searched. The rest of the API does not need it.
    public class EmbedderUnavailableException : Exception
    {
        // cause is the network error behind it. It ends up in the log, not in the response.
        public EmbedderUnavailableException(Exception cause)
            : base("The ticket search is not available right now. Listing tickets and getting a ticket by its id still work.", cause)
        {
        }
    }
}
