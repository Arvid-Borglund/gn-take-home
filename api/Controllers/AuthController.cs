using System.Text;
using Microsoft.AspNetCore.Mvc;
using TicketApi.Services;

namespace TicketApi.Controllers
{
    // GET /auth/check answers one question: does this request carry a valid login?
    //
    // The web interface uses basic auth: the browser sends the user name and the
    // password in the Authorization header of every request. nginx, in front of the
    // web interface, passes that header here before it serves anything
    // (auth_request in web/nginx/private/on.conf):
    //
    //   200  the login is valid; the user name is in the X-User header
    //   401  no login, or a wrong one; WWW-Authenticate makes the browser ask for one
    [ApiController]
    [Route("auth")]
    public class AuthController : ControllerBase
    {
        private readonly UserService _users;

        public AuthController(UserService users)
        {
            _users = users;
        }

        [HttpGet("check")]
        public async Task<IActionResult> Check()
        {
            string header = Request.Headers.Authorization;

            string username;
            string password;
            bool hasLogin = TryReadBasicAuth(header, out username, out password);

            if (!hasLogin || !await _users.IsValidLoginAsync(username, password))
            {
                Response.Headers.WWWAuthenticate = "Basic realm=\"Ticket desk\"";
                return Unauthorized();
            }

            Response.Headers["X-User"] = username;
            return Ok();
        }

        // The header looks like "Basic dXNlcjpzZWNyZXQ=", where the second part is
        // "user:secret" in base64. Base64 is a way of writing bytes as text, not
        // encryption: what protects the password on its way here is HTTPS.
        private static bool TryReadBasicAuth(string header, out string username, out string password)
        {
            username = null;
            password = null;

            if (header == null || !header.StartsWith("Basic ", StringComparison.Ordinal))
            {
                return false;
            }

            string decoded;
            try
            {
                byte[] bytes = Convert.FromBase64String(header.Substring("Basic ".Length));
                decoded = Encoding.UTF8.GetString(bytes);
            }
            catch (FormatException)
            {
                return false;
            }

            // The user name ends at the first colon. The password may contain colons.
            int colon = decoded.IndexOf(':');
            if (colon < 0)
            {
                return false;
            }

            username = decoded.Substring(0, colon);
            password = decoded.Substring(colon + 1);
            return true;
        }
    }
}
