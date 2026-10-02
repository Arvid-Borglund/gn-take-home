-- The users of the web interface.
--
-- A password is never stored. What is stored is a random salt, made when the user is
-- created, and the hash of salt + password (PBKDF2, see api/Services/PasswordHasher.cs).
-- To check a login the API hashes the given password with the stored salt and compares
-- the result with the stored hash.
--
-- The salt is different for every user, so two users with the same password have
-- different hashes, and a table of ready-made hashes of common passwords is useless.
CREATE TABLE IF NOT EXISTS app_user (
    user_id       BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username      TEXT        NOT NULL UNIQUE,
    password_salt BYTEA       NOT NULL,
    password_hash BYTEA       NOT NULL,
    created       TIMESTAMPTZ NOT NULL DEFAULT now()
);
