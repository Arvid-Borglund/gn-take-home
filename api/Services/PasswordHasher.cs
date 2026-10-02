using System.Security.Cryptography;

namespace TicketApi.Services
{
    // Salted password hashing with PBKDF2.
    //
    // The salt is random bytes, new for every user. It is stored next to the hash and
    // is not secret. Its job is to make the same password give a different hash for
    // every user, so that a ready-made table of hashes of common passwords is useless.
    //
    // PBKDF2 runs the hash function many times in a row. A login pays that cost once.
    // Someone who has stolen the table pays it for every password they try.
    //
    // The settings are the ones ASP.NET Core Identity uses.
    public static class PasswordHasher
    {
        private const int SaltSizeInBytes = 16;
        private const int HashSizeInBytes = 32;
        private const int Iterations = 100000;

        public static byte[] NewSalt()
        {
            // Random bytes from the operating system's generator, not from Random.
            return RandomNumberGenerator.GetBytes(SaltSizeInBytes);
        }

        public static byte[] Hash(string password, byte[] salt)
        {
            return Rfc2898DeriveBytes.Pbkdf2(
                password,
                salt,
                Iterations,
                HashAlgorithmName.SHA512,
                HashSizeInBytes);
        }

        public static bool Verify(string password, byte[] salt, byte[] expectedHash)
        {
            byte[] actualHash = Hash(password, salt);

            // Looks at every byte, also after the first one that differs. A comparison
            // that stops at the first difference takes longer the more of the hash is
            // right, and that time can be measured from outside.
            return CryptographicOperations.FixedTimeEquals(actualHash, expectedHash);
        }
    }
}
