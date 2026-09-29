using Microsoft.EntityFrameworkCore;
using TicketApi.Contracts;
using TicketApi.Data;
using TicketApi.Errors;
using TicketApi.Models;

namespace TicketApi.Services;

// The business rules live here: unknown id -> TicketNotFoundException (404),
// bad input -> TicketValidationException (422). The controller only does HTTP.
public sealed class TicketService(TicketDbContext db)
{
    private static readonly string ValidStatuses = string.Join(", ", Enum.GetNames<TicketStatus>());

    public async Task<TicketResponse> CreateAsync(CreateTicketRequest request, CancellationToken ct)
    {
        var ticket = new Ticket
        {
            Title = Require(request.Title, "title"),
            Description = Require(request.Description, "description"),
        };

        db.Tickets.Add(ticket);
        await db.SaveChangesAsync(ct); // the trigger records version 1

        return await OverviewAsync(ticket.TicketId, ct);
    }

    public async Task<List<TicketResponse>> ListAsync(string? status, CancellationToken ct)
    {
        IQueryable<TicketOverview> query = db.TicketOverview;

        if (status is not null)
        {
            var wanted = ParseStatus(status);
            query = query.Where(o => o.Status == wanted);
        }

        var rows = await query.OrderBy(o => o.TicketId).ToListAsync(ct);
        return rows.Select(ToResponse).ToList();
    }

    public async Task<TicketDetailResponse> GetAsync(long ticketId, CancellationToken ct)
    {
        var ticket = await OverviewAsync(ticketId, ct);

        var comments = await db.TicketComments
            .Where(c => c.TicketId == ticketId)
            .OrderBy(c => c.CommentId)
            .ToListAsync(ct);

        return new TicketDetailResponse(ticket, comments.Select(ToResponse).ToList());
    }

    public async Task<TicketResponse> UpdateAsync(long ticketId, UpdateTicketRequest request, CancellationToken ct)
    {
        var ticket = await db.Tickets.FindAsync([ticketId], ct)
            ?? throw new TicketNotFoundException(ticketId);

        if (request.Title is not null)
        {
            ticket.Title = Require(request.Title, "title");
        }

        if (request.Description is not null)
        {
            ticket.Description = Require(request.Description, "description");
        }

        if (request.Status is not null)
        {
            ticket.Status = ParseStatus(request.Status);
        }

        if (request.Resolution is not null)
        {
            ticket.Resolution = request.Resolution.Trim();
        }

        if (ticket.Status == TicketStatus.RESOLVED && string.IsNullOrWhiteSpace(ticket.Resolution))
        {
            throw new TicketValidationException(
                "A resolution note is required when the status is set to RESOLVED.");
        }

        await db.SaveChangesAsync(ct); // the trigger records the next version, if anything changed

        return await OverviewAsync(ticketId, ct);
    }

    public async Task DeleteAsync(long ticketId, CancellationToken ct)
    {
        // The database cascades to versions and comments.
        var deleted = await db.Tickets.Where(t => t.TicketId == ticketId).ExecuteDeleteAsync(ct);

        if (deleted == 0)
        {
            throw new TicketNotFoundException(ticketId);
        }
    }

    public async Task<CommentResponse> AddCommentAsync(long ticketId, AddCommentRequest request, CancellationToken ct)
    {
        var body = Require(request.Body, "body");

        // A comment belongs to the version that is current when it is written.
        var currentVersion = await db.TicketVersions
            .Where(v => v.TicketId == ticketId)
            .MaxAsync(v => (int?)v.VersionNo, ct)
            ?? throw new TicketNotFoundException(ticketId);

        var comment = new TicketComment
        {
            TicketId = ticketId,
            VersionNo = currentVersion,
            Body = body,
        };

        db.TicketComments.Add(comment);
        await db.SaveChangesAsync(ct);

        return ToResponse(comment);
    }

    public async Task<List<VersionResponse>> ListVersionsAsync(long ticketId, CancellationToken ct)
    {
        var versions = await db.TicketVersions
            .Where(v => v.TicketId == ticketId)
            .OrderBy(v => v.VersionNo)
            .ToListAsync(ct);

        if (versions.Count == 0)
        {
            throw new TicketNotFoundException(ticketId);
        }

        return versions
            .Select(v => new VersionResponse(v.VersionNo, v.TimeOfVersion, v.Snapshot.RootElement.Clone()))
            .ToList();
    }

    private async Task<TicketResponse> OverviewAsync(long ticketId, CancellationToken ct)
    {
        var overview = await db.TicketOverview.SingleOrDefaultAsync(o => o.TicketId == ticketId, ct)
            ?? throw new TicketNotFoundException(ticketId);

        return ToResponse(overview);
    }

    private static TicketStatus ParseStatus(string value)
    {
        // Enum.TryParse would also accept "1"; match the names explicitly.
        foreach (var status in Enum.GetValues<TicketStatus>())
        {
            if (status.ToString().Equals(value, StringComparison.OrdinalIgnoreCase))
            {
                return status;
            }
        }

        throw new TicketValidationException(
            $"'{value}' is not a valid status. Valid statuses are: {ValidStatuses}.");
    }

    private static string Require(string? value, string field)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new TicketValidationException($"The field '{field}' is required and cannot be empty.");
        }

        return value.Trim();
    }

    private static TicketResponse ToResponse(TicketOverview o) => new(
        o.TicketId, o.Title, o.Description, o.Status.ToString(), o.Resolution,
        o.Created, o.Updated, o.VersionNo);

    private static CommentResponse ToResponse(TicketComment c) => new(
        c.CommentId, c.VersionNo, c.Body, c.TimeOfComment);
}
