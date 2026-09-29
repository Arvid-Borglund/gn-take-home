using Microsoft.EntityFrameworkCore;
using TicketApi.Contracts;
using TicketApi.Data;
using TicketApi.Errors;
using TicketApi.Models;

namespace TicketApi.Services
{
    // The business rules live here: unknown id -> TicketNotFoundException (404),
    // bad input -> TicketValidationException (422). The controller only does HTTP.
    public class TicketService
    {
        private readonly TicketDbContext _db;

        public TicketService(TicketDbContext db)
        {
            _db = db;
        }

        public async Task<TicketResponse> CreateAsync(CreateTicketRequest request)
        {
            var ticket = new Ticket();
            ticket.Title = Require(request.Title, "title");
            ticket.Description = Require(request.Description, "description");
            ticket.Status = TicketStatus.OPEN; // a new ticket always starts open
            ticket.Resolution = null;

            _db.Tickets.Add(ticket);
            await _db.SaveChangesAsync(); // the trigger records version 1

            return await GetOverviewAsync(ticket.TicketId);
        }

        public async Task<List<TicketResponse>> ListAsync(string status)
        {
            IQueryable<TicketOverview> query = _db.TicketOverview;

            if (status != null)
            {
                TicketStatus wanted = ParseStatus(status);
                query = query.Where(o => o.Status == wanted);
            }

            List<TicketOverview> rows = await query.OrderBy(o => o.TicketId).ToListAsync();

            var result = new List<TicketResponse>();
            foreach (var row in rows)
            {
                result.Add(ToResponse(row));
            }

            return result;
        }

        public async Task<TicketDetailResponse> GetAsync(long ticketId)
        {
            TicketResponse ticket = await GetOverviewAsync(ticketId);

            List<TicketComment> comments = await _db.TicketComments
                .Where(c => c.TicketId == ticketId)
                .OrderBy(c => c.CommentId)
                .ToListAsync();

            var response = new TicketDetailResponse();
            response.Ticket = ticket;
            response.Comments = new List<CommentResponse>();
            foreach (var comment in comments)
            {
                response.Comments.Add(ToResponse(comment));
            }

            return response;
        }

        public async Task<TicketResponse> UpdateAsync(long ticketId, UpdateTicketRequest request)
        {
            Ticket ticket = await _db.Tickets.FirstOrDefaultAsync(t => t.TicketId == ticketId);
            if (ticket == null)
            {
                throw new TicketNotFoundException(ticketId);
            }

            if (request.Title != null)
            {
                ticket.Title = Require(request.Title, "title");
            }

            if (request.Description != null)
            {
                ticket.Description = Require(request.Description, "description");
            }

            if (request.Status != null)
            {
                ticket.Status = ParseStatus(request.Status);
            }

            if (request.Resolution != null)
            {
                ticket.Resolution = request.Resolution.Trim();
            }

            if (ticket.Status == TicketStatus.RESOLVED && string.IsNullOrWhiteSpace(ticket.Resolution))
            {
                throw new TicketValidationException(
                    "A resolution note is required when the status is set to RESOLVED.");
            }

            await _db.SaveChangesAsync(); // the trigger records the next version, if anything changed

            return await GetOverviewAsync(ticketId);
        }

        public async Task DeleteAsync(long ticketId)
        {
            // One DELETE statement; the database cascades to versions and comments.
            int deleted = await _db.Tickets.Where(t => t.TicketId == ticketId).ExecuteDeleteAsync();

            if (deleted == 0)
            {
                throw new TicketNotFoundException(ticketId);
            }
        }

        public async Task<CommentResponse> AddCommentAsync(long ticketId, AddCommentRequest request)
        {
            string body = Require(request.Body, "body");

            // A comment belongs to the version that is current when it is written.
            IQueryable<TicketVersion> versions = _db.TicketVersions.Where(v => v.TicketId == ticketId);

            bool ticketExists = await versions.AnyAsync();
            if (!ticketExists)
            {
                throw new TicketNotFoundException(ticketId);
            }

            int currentVersion = await versions.MaxAsync(v => v.VersionNo);

            var comment = new TicketComment();
            comment.TicketId = ticketId;
            comment.VersionNo = currentVersion;
            comment.Body = body;

            _db.TicketComments.Add(comment);
            await _db.SaveChangesAsync();

            return ToResponse(comment);
        }

        public async Task<List<VersionResponse>> ListVersionsAsync(long ticketId)
        {
            List<TicketVersion> versions = await _db.TicketVersions
                .Where(v => v.TicketId == ticketId)
                .OrderBy(v => v.VersionNo)
                .ToListAsync();

            if (versions.Count == 0)
            {
                throw new TicketNotFoundException(ticketId);
            }

            var result = new List<VersionResponse>();
            foreach (var version in versions)
            {
                var response = new VersionResponse();
                response.VersionNo = version.VersionNo;
                response.TimeOfVersion = version.TimeOfVersion;
                response.Snapshot = version.Snapshot.RootElement.Clone();
                result.Add(response);
            }

            return result;
        }

        // Reads one ticket from the view, with the derived timestamps.
        private async Task<TicketResponse> GetOverviewAsync(long ticketId)
        {
            TicketOverview overview = await _db.TicketOverview.FirstOrDefaultAsync(o => o.TicketId == ticketId);
            if (overview == null)
            {
                throw new TicketNotFoundException(ticketId);
            }

            return ToResponse(overview);
        }

        // "open" and "OPEN" are both accepted; anything else is a 422 that lists the valid names.
        private static TicketStatus ParseStatus(string value)
        {
            string[] validNames = Enum.GetNames(typeof(TicketStatus));

            foreach (string name in validNames)
            {
                if (string.Equals(name, value, StringComparison.OrdinalIgnoreCase))
                {
                    return (TicketStatus)Enum.Parse(typeof(TicketStatus), name);
                }
            }

            throw new TicketValidationException(
                "'" + value + "' is not a valid status. Valid statuses are: " + string.Join(", ", validNames) + ".");
        }

        private static string Require(string value, string fieldName)
        {
            if (string.IsNullOrWhiteSpace(value))
            {
                throw new TicketValidationException("The field '" + fieldName + "' is required and cannot be empty.");
            }

            return value.Trim();
        }

        private static TicketResponse ToResponse(TicketOverview overview)
        {
            var response = new TicketResponse();
            response.TicketId = overview.TicketId;
            response.Title = overview.Title;
            response.Description = overview.Description;
            response.Status = overview.Status.ToString();
            response.Resolution = overview.Resolution;
            response.Created = overview.Created;
            response.Updated = overview.Updated;
            response.VersionNo = overview.VersionNo;
            return response;
        }

        private static CommentResponse ToResponse(TicketComment comment)
        {
            var response = new CommentResponse();
            response.CommentId = comment.CommentId;
            response.VersionNo = comment.VersionNo;
            response.Body = comment.Body;
            response.TimeOfComment = comment.TimeOfComment;
            return response;
        }
    }
}
