using Microsoft.EntityFrameworkCore;
using TicketApi.Data;
using TicketApi.Models;

namespace TicketApi.Services
{
    // The users of the web interface: checking a login and creating a user.
    public class UserService
    {
        private readonly TicketDbContext _db;

        public UserService(TicketDbContext db)
        {
            _db = db;
        }

        // True when the user exists and the password is the right one.
        public async Task<bool> IsValidLoginAsync(string username, string password)
        {
            AppUser user = await _db.Users.FirstOrDefaultAsync(u => u.Username == username);
            if (user == null)
            {
                return false;
            }

            return PasswordHasher.Verify(password, user.PasswordSalt, user.PasswordHash);
        }

        // Creates the user if nobody has that user name yet. A user that exists is left
        // alone, so starting the API again never changes a password.
        public async Task EnsureUserAsync(string username, string password)
        {
            bool exists = await _db.Users.AnyAsync(u => u.Username == username);
            if (exists)
            {
                return;
            }

            var user = new AppUser();
            user.Username = username;
            user.PasswordSalt = PasswordHasher.NewSalt();
            user.PasswordHash = PasswordHasher.Hash(password, user.PasswordSalt);

            _db.Users.Add(user);
            await _db.SaveChangesAsync();
        }
    }
}
