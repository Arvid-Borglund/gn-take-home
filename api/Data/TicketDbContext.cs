using Microsoft.EntityFrameworkCore;
using TicketApi.Models;

namespace TicketApi.Data
{
    // Maps the entities onto the hand-written schema in db/init/.
    // Column names follow from the snake_case naming convention registered in
    // Program.cs (TicketId -> ticket_id, TimeOfVersion -> time_of_version).
    public class TicketDbContext : DbContext
    {
        public TicketDbContext(DbContextOptions<TicketDbContext> options) : base(options)
        {
        }

        public DbSet<Ticket> Tickets { get; set; }
        public DbSet<TicketVersion> TicketVersions { get; set; }
        public DbSet<TicketComment> TicketComments { get; set; }
        public DbSet<TicketOverview> TicketOverview { get; set; }
        public DbSet<AppUser> Users { get; set; }
        public DbSet<TicketMatch> TicketMatches { get; set; }

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
                // Composite key: EF's way of saying PRIMARY KEY (ticket_id, version_no).
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

            modelBuilder.Entity<AppUser>(user =>
            {
                user.ToTable("app_user");
                user.HasKey(u => u.UserId);
                user.Property(u => u.UserId).UseIdentityAlwaysColumn();
                // Set by the database; EF leaves it out of the INSERT and reads it back.
                user.Property(u => u.Created).HasDefaultValueSql("now()");
            });

            // The rows of a search result. No table or view: they only ever come from
            // the SQL in TicketSearchService. Registered here so that EF can turn the
            // columns of that query into objects (ticket_id -> TicketId and so on).
            modelBuilder.Entity<TicketMatch>(match =>
            {
                match.HasNoKey();
                match.Property(m => m.Status).HasConversion<string>();
            });
        }
    }
}
