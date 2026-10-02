namespace TicketApi.Models
{
    // A user of the web interface (table app_user). The password itself is never
    // stored: only the salt and the hash made from the two (see PasswordHasher).
    public class AppUser
    {
        public long UserId { get; set; }
        public string Username { get; set; }
        public byte[] PasswordSalt { get; set; }
        public byte[] PasswordHash { get; set; }
        public DateTime Created { get; set; }
    }
}
