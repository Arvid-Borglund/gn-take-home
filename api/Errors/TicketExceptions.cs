namespace TicketApi.Errors;

// The two business-rule failures the API reports. TicketExceptionHandler turns
// them into ProblemDetails responses (404 and 422) with the message as "detail".

public sealed class TicketNotFoundException(long ticketId)
    : Exception($"Ticket {ticketId} does not exist.")
{
    public long TicketId { get; } = ticketId;
}

public sealed class TicketValidationException(string message) : Exception(message);
