using Microsoft.AspNetCore.Diagnostics;
using Microsoft.AspNetCore.Mvc;

namespace TicketApi.Errors
{
    // The one place where the API's own failures become HTTP responses.
    // ASP.NET's exception middleware (app.UseExceptionHandler() in Program.cs)
    // catches everything thrown during a request and calls TryHandleAsync.
    // The body is RFC 9457 ProblemDetails; clients (the agent) read "detail".
    public class TicketExceptionHandler : IExceptionHandler
    {
        private readonly IProblemDetailsService _problemDetails;

        public TicketExceptionHandler(IProblemDetailsService problemDetails)
        {
            _problemDetails = problemDetails;
        }

        // Signature dictated by IExceptionHandler (ValueTask is a lighter Task).
        // Returns true when this handler wrote the response, false to let the next one try.
        public async ValueTask<bool> TryHandleAsync(
            HttpContext httpContext, Exception exception, CancellationToken cancellationToken)
        {
            // 1. Which status code does this exception mean?
            int statusCode;

            if (exception is TicketNotFoundException)
            {
                statusCode = StatusCodes.Status404NotFound;
            }
            else if (exception is TicketValidationException)
            {
                statusCode = StatusCodes.Status422UnprocessableEntity;
            }
            else if (exception is EmbedderUnavailableException)
            {
                // Nothing is wrong with the request: a service the search needs is down.
                statusCode = StatusCodes.Status503ServiceUnavailable;
            }
            else
            {
                // Not one of ours: say no, and the default handler answers 500.
                return false;
            }

            // 2. Set the HTTP status line on the response being built.
            httpContext.Response.StatusCode = statusCode;

            // 3. Write the JSON body. The service fills in "title" and "type" from the
            //    status code; we supply "status" and "detail".
            var problem = new ProblemDetails();
            problem.Status = statusCode;
            problem.Detail = exception.Message;

            // HttpContext can only be set in the initializer (framework rule).
            var context = new ProblemDetailsContext
            {
                HttpContext = httpContext,
                ProblemDetails = problem
            };

            bool written = await _problemDetails.TryWriteAsync(context);

            // true tells the middleware the exception is handled.
            return written;
        }
    }
}
