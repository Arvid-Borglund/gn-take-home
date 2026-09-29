namespace TicketApi.Contracts;

// Every field is nullable on purpose: the service validates the payload and
// answers 422 with a message, instead of ASP.NET's automatic 400.

public sealed record CreateTicketRequest(string? Title, string? Description);

// PATCH semantics: only the fields that are present are changed.
public sealed record UpdateTicketRequest(string? Title, string? Description, string? Status, string? Resolution);

public sealed record AddCommentRequest(string? Body);
