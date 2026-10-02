-- Schema for the mock ticketing API.
--
-- Locally the postgres image runs the files in this directory the first time the
-- database volume is empty (/docker-entrypoint-initdb.d/). On the server the deploy
-- workflow runs them on every deploy. So every statement only creates what is
-- missing, and running a file again changes nothing.

-- Current state of every ticket. Timestamps live in the history, not here:
-- created = time_of_version of version 1, updated = time_of_version of the latest.
CREATE TABLE IF NOT EXISTS ticket (
    ticket_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'OPEN',
    resolution  TEXT,

    CONSTRAINT ticket_status_valid
        CHECK (status IN ('OPEN', 'RESOLVED', 'CLOSED')),
    CONSTRAINT ticket_resolution_required
        CHECK (status <> 'RESOLVED' OR resolution IS NOT NULL)
);

-- Append-only history: one row per state a ticket has been in.
-- Written by the trigger below, never by hand. The snapshot holds every
-- ticket field except the key.
CREATE TABLE IF NOT EXISTS ticket_version (
    ticket_id       BIGINT      NOT NULL REFERENCES ticket (ticket_id) ON DELETE CASCADE,
    version_no      INTEGER     NOT NULL,
    snapshot        JSONB       NOT NULL,
    time_of_version TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (ticket_id, version_no)
);

-- A comment belongs to the version the ticket had when the comment was written.
-- The composite foreign key guarantees that version belongs to that ticket.
CREATE TABLE IF NOT EXISTS ticket_comment (
    ticket_id       BIGINT      NOT NULL,
    version_no      INTEGER     NOT NULL,
    comment_id      BIGINT      GENERATED ALWAYS AS IDENTITY UNIQUE,
    body            TEXT        NOT NULL,
    time_of_comment TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (ticket_id, version_no, comment_id),
    CONSTRAINT ticket_comment_version_fk
        FOREIGN KEY (ticket_id, version_no)
        REFERENCES ticket_version (ticket_id, version_no) ON DELETE CASCADE
);

-- Read model: current state plus the timestamps derived from the history.
CREATE OR REPLACE VIEW ticket_overview AS
SELECT t.ticket_id, t.title, t.description, t.status, t.resolution,
       min(v.time_of_version) AS created,
       max(v.time_of_version) AS updated,
       max(v.version_no)      AS version_no
FROM ticket t
JOIN ticket_version v USING (ticket_id)
GROUP BY t.ticket_id;

-- History is never written by hand: every INSERT or UPDATE on ticket records
-- a version automatically. An update that changes nothing records nothing.
CREATE OR REPLACE FUNCTION ticket_record_version() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND to_jsonb(OLD) = to_jsonb(NEW) THEN
        RETURN NEW;
    END IF;

    INSERT INTO ticket_version (ticket_id, version_no, snapshot)
    SELECT NEW.ticket_id,
           coalesce(max(version_no), 0) + 1,
           to_jsonb(NEW) - 'ticket_id'
    FROM ticket_version
    WHERE ticket_id = NEW.ticket_id;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER ticket_record_version
AFTER INSERT OR UPDATE ON ticket
FOR EACH ROW EXECUTE FUNCTION ticket_record_version();
