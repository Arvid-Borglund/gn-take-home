using Microsoft.AspNetCore.Mvc;
using TicketApi.Contracts;
using TicketApi.Services;

namespace TicketApi.Controllers
{
    // HTTP only: routing, request in, status code out. Rules and errors live in
    // TicketService and TicketExceptionHandler.
    [ApiController]
    [Route("tickets")]
    public class TicketsController : ControllerBase
    {
        private readonly TicketService _tickets;

        public TicketsController(TicketService tickets)
        {
            _tickets = tickets;
        }

        // POST /tickets
        [HttpPost]
        public async Task<ActionResult<TicketResponse>> Create([FromBody] CreateTicketRequest request)
        {
            TicketResponse ticket = await _tickets.CreateAsync(request);
            return CreatedAtAction(nameof(Get), new { id = ticket.TicketId }, ticket);
        }

        // GET /tickets or GET /tickets?status=OPEN
        [HttpGet]
        public async Task<ActionResult<List<TicketResponse>>> List([FromQuery] string status)
        {
            List<TicketResponse> tickets = await _tickets.ListAsync(status);
            return Ok(tickets);
        }

        // GET /tickets/1
        [HttpGet("{id:long}")]
        public async Task<ActionResult<TicketDetailResponse>> Get(long id)
        {
            TicketDetailResponse ticket = await _tickets.GetAsync(id);
            return Ok(ticket);
        }

        // PATCH /tickets/1
        [HttpPatch("{id:long}")]
        public async Task<ActionResult<TicketResponse>> Update(long id, [FromBody] UpdateTicketRequest request)
        {
            TicketResponse ticket = await _tickets.UpdateAsync(id, request);
            return Ok(ticket);
        }

        // DELETE /tickets/1
        [HttpDelete("{id:long}")]
        public async Task<IActionResult> Delete(long id)
        {
            await _tickets.DeleteAsync(id);
            return NoContent();
        }

        // POST /tickets/1/comments
        [HttpPost("{id:long}/comments")]
        public async Task<ActionResult<CommentResponse>> AddComment(long id, [FromBody] AddCommentRequest request)
        {
            CommentResponse comment = await _tickets.AddCommentAsync(id, request);
            return CreatedAtAction(nameof(Get), new { id = id }, comment);
        }

        // GET /tickets/1/versions
        [HttpGet("{id:long}/versions")]
        public async Task<ActionResult<List<VersionResponse>>> Versions(long id)
        {
            List<VersionResponse> versions = await _tickets.ListVersionsAsync(id);
            return Ok(versions);
        }
    }
}
