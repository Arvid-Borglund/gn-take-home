using Microsoft.EntityFrameworkCore;
using TicketApi.Data;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// The schema is owned by db/init/001_schema.sql, not by EF: no migrations here.
builder.Services.AddDbContext<TicketDbContext>(options =>
    options
        .UseNpgsql(builder.Configuration.GetConnectionString("TicketDb"))
        .UseSnakeCaseNamingConvention());

var app = builder.Build();

app.UseSwagger();
app.UseSwaggerUI();

app.MapControllers();

app.Run();
