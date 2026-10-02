-- Example tickets, so that a new system has something to look at: tickets in every
-- status, some with a history of several versions, and comments written on different
-- versions.
--
-- The file runs with the others in this directory: locally the first time the database
-- volume is empty, on the server on every deploy. It only does something when there
-- are no tickets at all, so it never adds to a database that is in use.
--
-- The history is not written here. Every INSERT and UPDATE on ticket below gets its
-- row in ticket_version from the trigger in 001_schema.sql, exactly as when the API
-- makes the change. A comment is put on the version the ticket has at that point, which
-- is why the statements for one ticket stand in the order things happened.

DO $$
DECLARE
    first_id         BIGINT;   -- the id of the first example ticket
    new_id           BIGINT;   -- the id of the ticket being built
    first_comment_id BIGINT;   -- the id of the first example comment
BEGIN
    IF EXISTS (SELECT 1 FROM ticket) THEN
        RETURN;
    END IF;

    -- 1. Resolved, with a comment before the fix. Two versions.
    INSERT INTO ticket (title, description)
    VALUES ('Cannot log in to the payroll system',
            'The login page says "account locked" since this morning.')
    RETURNING ticket_id INTO new_id;
    first_id := new_id;

    INSERT INTO ticket_comment (ticket_id, version_no, body)
    VALUES (new_id, 1, 'The account was locked after five wrong passwords.')
    RETURNING comment_id INTO first_comment_id;

    UPDATE ticket
    SET status = 'RESOLVED', resolution = 'Unlocked the account and set a new password'
    WHERE ticket_id = new_id;

    -- 2. Open, never changed, one comment. One version.
    INSERT INTO ticket (title, description)
    VALUES ('Shared drive is almost full',
            'Less than 2 GB left on the shared drive. Saving large files fails.')
    RETURNING ticket_id INTO new_id;

    INSERT INTO ticket_comment (ticket_id, version_no, body)
    VALUES (new_id, 1, 'Finance holds 40 percent of the space. Asked them to archive last year.');

    -- 3. The description was filled in before the ticket was resolved. Three versions,
    --    comments on the first and the second.
    INSERT INTO ticket (title, description)
    VALUES ('Wi-Fi drops in meeting room 4',
            'Video calls freeze several times per meeting.')
    RETURNING ticket_id INTO new_id;

    INSERT INTO ticket_comment (ticket_id, version_no, body)
    VALUES (new_id, 1, 'Does it happen in every meeting, or only in the large ones?');

    UPDATE ticket
    SET description = 'Video calls freeze several times per meeting. It happens when more than ten people are in the room.'
    WHERE ticket_id = new_id;

    INSERT INTO ticket_comment (ticket_id, version_no, body)
    VALUES (new_id, 2, 'One access point is not enough for that many devices. Ordered a second one.');

    UPDATE ticket
    SET status = 'RESOLVED', resolution = 'Installed a second access point in the room'
    WHERE ticket_id = new_id;

    -- 4. Open, resolved, then closed. Three versions, a comment on the second.
    INSERT INTO ticket (title, description)
    VALUES ('New colleague needs accounts by Monday',
            'Email, the HR system and the door badge for a new colleague in sales.')
    RETURNING ticket_id INTO new_id;

    UPDATE ticket
    SET status = 'RESOLVED', resolution = 'Created the accounts and ordered the badge'
    WHERE ticket_id = new_id;

    INSERT INTO ticket_comment (ticket_id, version_no, body)
    VALUES (new_id, 2, 'The manager confirmed that everything works. This can be closed.');

    UPDATE ticket SET status = 'CLOSED' WHERE ticket_id = new_id;

    -- 5. Resolved without discussion. Two versions.
    INSERT INTO ticket (title, description)
    VALUES ('Email attachments over 10 MB bounce',
            'Customers get an error back when they send us drawings.')
    RETURNING ticket_id INTO new_id;

    UPDATE ticket
    SET status = 'RESOLVED', resolution = 'Raised the size limit on the mail gateway to 25 MB'
    WHERE ticket_id = new_id;

    -- 6. Closed without a resolution: the problem could not be reproduced. Two versions.
    INSERT INTO ticket (title, description)
    VALUES ('Phone headset crackles',
            'The other side hears a crackling noise on every call.')
    RETURNING ticket_id INTO new_id;

    INSERT INTO ticket_comment (ticket_id, version_no, body)
    VALUES (new_id, 1, 'Could not reproduce it with another headset on the same phone.');

    UPDATE ticket SET status = 'CLOSED' WHERE ticket_id = new_id;

    -- 7. Open and untouched. One version, no comments.
    INSERT INTO ticket (title, description)
    VALUES ('Badge reader at the side entrance is slow',
            'It takes about ten seconds before the door opens.')
    RETURNING ticket_id INTO new_id;

    -- 8. Open, with the title corrected afterwards. Two versions, a comment on the second.
    INSERT INTO ticket (title, description)
    VALUES ('Accounting software licence expires next month',
            'The renewal notice came by email. Twelve users.')
    RETURNING ticket_id INTO new_id;

    UPDATE ticket
    SET title = 'Accounting software licence expires on 31 October'
    WHERE ticket_id = new_id;

    INSERT INTO ticket_comment (ticket_id, version_no, body)
    VALUES (new_id, 2, 'Asked the vendor for a quote for twelve users.');

    -- 9. Resolved, reopened, resolved again. Four versions, one comment on the first
    --    and two on the third.
    INSERT INTO ticket (title, description)
    VALUES ('Backup job failed last night',
            'The nightly backup of the file server ended with an error.')
    RETURNING ticket_id INTO new_id;

    INSERT INTO ticket_comment (ticket_id, version_no, body)
    VALUES (new_id, 1, 'Reading the log of the job.');

    UPDATE ticket
    SET status = 'RESOLVED', resolution = 'Started the job again by hand and it finished'
    WHERE ticket_id = new_id;

    UPDATE ticket SET status = 'OPEN' WHERE ticket_id = new_id;

    INSERT INTO ticket_comment (ticket_id, version_no, body)
    VALUES (new_id, 3, 'It failed again tonight. The disk it writes to is full.');

    INSERT INTO ticket_comment (ticket_id, version_no, body)
    VALUES (new_id, 3, 'Backups from last year take most of the space. Asked if they can be moved.');

    UPDATE ticket
    SET status = 'RESOLVED', resolution = 'Moved old backups away and freed space on the disk'
    WHERE ticket_id = new_id;

    -- 10. Open, one comment. One version.
    INSERT INTO ticket (title, description)
    VALUES ('Conference phone has no dial tone',
            'The phone in the board room is silent when the handset is lifted.')
    RETURNING ticket_id INTO new_id;

    INSERT INTO ticket_comment (ticket_id, version_no, body)
    VALUES (new_id, 1, 'The phone works on another line, so the line itself is dead. Reported to the operator.');

    -- The times. Everything above happened within one moment, so the history is moved
    -- back and spread out: the first ticket was created ten days ago, the next one nine
    -- days ago and so on, with seven hours between the versions of a ticket. A comment
    -- is placed after the version it was written on: the first comment one hour after,
    -- and each later comment 25 minutes more than the one before it, so that they do
    -- not all sit at the same distance. This is the only place where ticket_version is
    -- written by hand.
    UPDATE ticket_version
    SET time_of_version = now()
        - interval '1 day' * (10 - (ticket_id - first_id))
        + interval '7 hours' * (version_no - 1)
    WHERE ticket_id >= first_id;

    UPDATE ticket_comment c
    SET time_of_comment = v.time_of_version
        + interval '1 hour'
        + interval '25 minutes' * (c.comment_id - first_comment_id)
    FROM ticket_version v
    WHERE v.ticket_id = c.ticket_id
      AND v.version_no = c.version_no
      AND c.ticket_id >= first_id;
END $$;
