using Microsoft.EntityFrameworkCore;
using TicketApi.Data;
using TicketApi.Errors;
using TicketApi.Services;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// The schema is owned by db/init/001_schema.sql, not by EF: no migrations here.
builder.Services.AddDbContext<TicketDbContext>(options =>
    options
        .UseNpgsql(builder.Configuration.GetConnectionString("TicketDb"))
        .UseSnakeCaseNamingConvention());

builder.Services.AddScoped<TicketService>();

// Every error body is ProblemDetails: business rules via TicketExceptionHandler,
// empty 4xx responses (unmatched routes) via UseStatusCodePages below.
builder.Services.AddProblemDetails();
builder.Services.AddExceptionHandler<TicketExceptionHandler>();

var app = builder.Build();

app.UseExceptionHandler();
app.UseStatusCodePages();

app.UseSwagger();
app.UseSwaggerUI();

app.MapControllers();

app.Run();
