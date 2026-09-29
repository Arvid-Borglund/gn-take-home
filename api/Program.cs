using Microsoft.EntityFrameworkCore;
using TicketApi.Data;
using TicketApi.Errors;
using TicketApi.Services;

// Entry point of the API (top-level statements: this file is Main).
// Part 1 registers services in the DI container, part 2 builds the request pipeline.

var builder = WebApplication.CreateBuilder(args);

// ----- 1. Services -----------------------------------------------------------

builder.Services.AddControllers();

// Swagger: the OpenAPI document and the UI at /swagger.
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// EF Core against Postgres. The schema is owned by db/init/001_schema.sql,
// not by EF: no migrations here. The naming convention maps TicketId -> ticket_id.
string connectionString = builder.Configuration.GetConnectionString("TicketDb");
builder.Services.AddDbContext<TicketDbContext>(options =>
{
    options.UseNpgsql(connectionString);
    options.UseSnakeCaseNamingConvention();
});

// One TicketService per request, with its own DbContext injected.
builder.Services.AddScoped<TicketService>();

// Every error body is ProblemDetails: business rules via TicketExceptionHandler,
// empty 4xx responses (unmatched routes) via UseStatusCodePages below.
builder.Services.AddProblemDetails();
builder.Services.AddExceptionHandler<TicketExceptionHandler>();

var app = builder.Build();

// ----- 2. Request pipeline (order matters: first in, last out) -----------------

app.UseExceptionHandler();   // try/catch around everything below
app.UseStatusCodePages();    // ProblemDetails body for empty 404s etc.

app.UseSwagger();
app.UseSwaggerUI();

app.MapControllers();        // routes requests to TicketsController

app.Run();
