-- The conversations of the web interface: one row per conversation, with who it belongs
-- to. The messages of a conversation are not here. They are in the tables that the
-- agent's graph creates for itself when the agent server starts (its checkpointer),
-- under the thread id "web-<conversation_id>".
--
-- This file can be run any number of times: it only creates what is missing.

CREATE TABLE IF NOT EXISTS conversation (
    conversation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- The login name of the user the conversation belongs to.
    username        TEXT        NOT NULL,
    -- The first message, shortened. Empty until the first message is sent.
    title           TEXT        NOT NULL DEFAULT '',
    -- Set when a turn crashed. A failed conversation takes no more messages.
    failed          BOOLEAN     NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The list of a user's conversations, the latest one used first.
CREATE INDEX IF NOT EXISTS conversation_username_updated_at
    ON conversation (username, updated_at DESC);
