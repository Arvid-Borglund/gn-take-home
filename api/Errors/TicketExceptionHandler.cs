using Microsoft.AspNetCore.Diagnostics;
using Microsoft.AspNetCore.Mvc;

namespace TicketApi.Errors;

// The one place where business-rule failures become HTTP responses.
// The body is RFC 9457 ProblemDetails; clients (the agent) read "detail".
public sealed class TicketExceptionHandler(IProblemDetailsService problemDetails) : IExceptionHandler
{
    public async ValueTask<bool> TryHandleAsync(
        HttpContext httpContext, Exception exception, CancellationToken cancellationToken)
    {
        int? status = exception switch
        {
            TicketNotFoundException => StatusCodes.Status404NotFound,
            TicketValidationException => StatusCodes.Status422UnprocessableEntity,
            _ => null,
        };

        if (status is null)
        {
            return false; // not ours: the default handler answers 500
        }

        httpContext.Response.StatusCode = status.Value;
        return await problemDetails.TryWriteAsync(new ProblemDetailsContext
        {
            HttpContext = httpContext,
            ProblemDetails = new ProblemDetails
            {
                Status = status,
                Detail = exception.Message,
            },
        });
    }
}
