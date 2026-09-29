using System.Text.Json;

namespace TicketApi.Contracts;

public sealed record TicketResponse(
    long TicketId,
    string Title,
    string Description,
    string Status,
    string? Resolution,
    DateTime Created,
    DateTime Updated,
    int VersionNo);

public sealed record TicketDetailResponse(
    TicketResponse Ticket,
    List<CommentResponse> Comments);

public sealed record CommentResponse(
    long CommentId,
    int VersionNo,
    string Body,
    DateTime TimeOfComment);

public sealed record VersionResponse(
    int VersionNo,
    DateTime TimeOfVersion,
    JsonElement Snapshot);
