namespace TicketApi.Errors
{
    // The two business-rule failures the API reports. TicketExceptionHandler turns
    // them into ProblemDetails responses (404 and 422) with the message as "detail".

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
}
