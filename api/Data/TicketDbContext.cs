using Microsoft.EntityFrameworkCore;
using TicketApi.Models;

namespace TicketApi.Data;

// Maps the entities onto the hand-written schema in db/init/001_schema.sql.
// Column names follow from the snake_case naming convention registered in
// Program.cs (TicketId -> ticket_id, TimeOfVersion -> time_of_version).
public sealed class TicketDbContext(DbContextOptions<TicketDbContext> options) : DbContext(options)
{
    public DbSet<Ticket> Tickets => Set<Ticket>();
    public DbSet<TicketVersion> TicketVersions => Set<TicketVersion>();
    public DbSet<TicketComment> TicketComments => Set<TicketComment>();
    public DbSet<TicketOverview> TicketOverview => Set<TicketOverview>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Ticket>(ticket =>
        {
            ticket.ToTable("ticket");
            ticket.HasKey(t => t.TicketId);
            // GENERATED ALWAYS AS IDENTITY: EF must never send a value.
            ticket.Property(t => t.TicketId).UseIdentityAlwaysColumn();
            ticket.Property(t => t.Status).HasConversion<string>();
            ticket.HasMany(t => t.Versions).WithOne().HasForeignKey(v => v.TicketId);
            ticket.HasMany(t => t.Comments).WithOne().HasForeignKey(c => c.TicketId);
        });

        modelBuilder.Entity<TicketVersion>(version =>
        {
            version.ToTable("ticket_version");
            version.HasKey(v => new { v.TicketId, v.VersionNo });
            version.Property(v => v.Snapshot).HasColumnType("jsonb");
        });

        modelBuilder.Entity<TicketComment>(comment =>
        {
            comment.ToTable("ticket_comment");
            comment.HasKey(c => new { c.TicketId, c.VersionNo, c.CommentId });
            comment.Property(c => c.CommentId).UseIdentityAlwaysColumn();
            // Set by the database; EF leaves it out of the INSERT and reads it back.
            comment.Property(c => c.TimeOfComment).HasDefaultValueSql("now()");
        });

        modelBuilder.Entity<TicketOverview>(overview =>
        {
            overview.HasNoKey();
            overview.ToView("ticket_overview");
            overview.Property(o => o.Status).HasConversion<string>();
        });
    }
}
