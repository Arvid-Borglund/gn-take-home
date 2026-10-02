using Microsoft.EntityFrameworkCore;
using TicketApi.Data;
using TicketApi.Errors;
using TicketApi.Services;

// Entry point of the API (top-level statements: this file is Main).
// Part 1 registers services in the DI container, part 2 builds the request pipeline,
// part 3 creates the first user of the web interface.

var builder = WebApplication.CreateBuilder(args);

// ----- 1. Services -----------------------------------------------------------

builder.Services.AddControllers();

// Swagger: the OpenAPI document and the UI at /swagger.
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// EF Core against Postgres. The schema is owned by the files in db/init/,
// not by EF: no migrations here. The naming convention maps TicketId -> ticket_id.
string connectionString = builder.Configuration.GetConnectionString("TicketDb");
builder.Services.AddDbContext<TicketDbContext>(options =>
{
    options.UseNpgsql(connectionString);
    options.UseSnakeCaseNamingConvention();
});

// One TicketService, one TicketSearchService and one UserService per request, each
// with the request's DbContext injected.
builder.Services.AddScoped<TicketService>();
builder.Services.AddScoped<TicketSearchService>();
builder.Services.AddScoped<UserService>();

// The embedder service makes the embeddings the search works with. AddHttpClient
// registers EmbedderClient and gives it an HttpClient with these settings.
// The address is the setting Embedder:Url (Embedder__Url in the environment).
string embedderUrl = builder.Configuration["Embedder:Url"];
builder.Services.AddHttpClient<EmbedderClient>(client =>
{
    client.BaseAddress = new Uri(embedderUrl);
    // Creating a ticket waits for the embedder at most this long.
    client.Timeout = TimeSpan.FromSeconds(5);
});

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

app.MapControllers();        // routes requests to the controllers

// ----- 3. The first user -------------------------------------------------------

// Someone has to be able to log in to the web interface. If a user name and a
// password are configured (SeedUser__Username and SeedUser__Password in the
// environment), that user is created here, unless it already exists. The password is
// never stored: UserService stores a salt and a hash.
string seedUsername = app.Configuration["SeedUser:Username"];
string seedPassword = app.Configuration["SeedUser:Password"];

if (!string.IsNullOrEmpty(seedUsername) && !string.IsNullOrEmpty(seedPassword))
{
    // UserService is made once per request. There is no request here, so the scope a
    // request would have had is made by hand.
    using (IServiceScope scope = app.Services.CreateScope())
    {
        UserService users = scope.ServiceProvider.GetRequiredService<UserService>();
        await users.EnsureUserAsync(seedUsername, seedPassword);
    }
}

app.Run();
