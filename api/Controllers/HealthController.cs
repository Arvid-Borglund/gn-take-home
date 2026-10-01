using Microsoft.AspNetCore.Mvc;
using TicketApi.Contracts;
using TicketApi.Data;

namespace TicketApi.Controllers
{
    // GET /health tells whoever runs the API (a test, a proxy in front of it) whether
    // it can serve requests. The API is only useful when it reaches its database, so
    // that is what is checked.
    [ApiController]
    [Route("health")]
    public class HealthController : ControllerBase
    {
        private readonly TicketDbContext _db;

        public HealthController(TicketDbContext db)
        {
            _db = db;
        }

        [HttpGet]
        public async Task<ActionResult<HealthResponse>> Get()
        {
            // CanConnectAsync returns false when the database does not answer.
            // It does not throw.
            bool databaseReachable = await _db.Database.CanConnectAsync();

            var response = new HealthResponse();

            if (!databaseReachable)
            {
                response.Status = "unhealthy";
                response.Database = "unreachable";
                return StatusCode(StatusCodes.Status503ServiceUnavailable, response);
            }

            response.Status = "healthy";
            response.Database = "reachable";
            return Ok(response);
        }
    }
}
