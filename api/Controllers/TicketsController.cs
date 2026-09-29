using Microsoft.AspNetCore.Mvc;
using TicketApi.Contracts;
using TicketApi.Services;

namespace TicketApi.Controllers;

// HTTP only: routing, request in, status code out. Rules and errors live in
// TicketService and TicketExceptionHandler.
[ApiController]
[Route("tickets")]
public sealed class TicketsController(TicketService tickets) : ControllerBase
{
    [HttpPost]
    public async Task<ActionResult<TicketResponse>> Create(CreateTicketRequest request, CancellationToken ct)
    {
        var ticket = await tickets.CreateAsync(request, ct);
        return CreatedAtAction(nameof(Get), new { id = ticket.TicketId }, ticket);
    }

    // GET /tickets?status=OPEN
    [HttpGet]
    public Task<List<TicketResponse>> List([FromQuery] string? status, CancellationToken ct)
        => tickets.ListAsync(status, ct);

    [HttpGet("{id:long}")]
    public Task<TicketDetailResponse> Get(long id, CancellationToken ct)
        => tickets.GetAsync(id, ct);

    [HttpPatch("{id:long}")]
    public Task<TicketResponse> Update(long id, UpdateTicketRequest request, CancellationToken ct)
        => tickets.UpdateAsync(id, request, ct);

    [HttpDelete("{id:long}")]
    public async Task<IActionResult> Delete(long id, CancellationToken ct)
    {
        await tickets.DeleteAsync(id, ct);
        return NoContent();
    }

    [HttpPost("{id:long}/comments")]
    public async Task<ActionResult<CommentResponse>> AddComment(long id, AddCommentRequest request, CancellationToken ct)
    {
        var comment = await tickets.AddCommentAsync(id, request, ct);
        return CreatedAtAction(nameof(Get), new { id }, comment);
    }

    [HttpGet("{id:long}/versions")]
    public Task<List<VersionResponse>> Versions(long id, CancellationToken ct)
        => tickets.ListVersionsAsync(id, ct);
}
