-- Search by meaning: the embeddings of the tickets, and the index that finds the
-- nearest ones.
--
-- An embedding is a list of 384 numbers that says what a text is about (see
-- embedder/main.py). The API stores one per ticket, made from its title and
-- description, and a search asks for the tickets whose embeddings lie closest to the
-- embedding of the question.
--
-- Like the other files in this directory, this one only creates what is missing.

-- pgvector: the column type "vector", the distance operators and the index type below.
-- The extension comes with the database image (db/Dockerfile).
CREATE EXTENSION IF NOT EXISTS vector;

-- One row per ticket that has an embedding. A ticket without a row has not been
-- embedded yet: the API fills those in before it searches.
--
-- A table of its own, and not a column on ticket: the trigger in 001_schema.sql
-- compares the whole ticket row to decide whether a change is a new version, and it
-- puts the whole row in the history. An embedding is neither a change to the ticket nor
-- something to keep 384 numbers of per version.
CREATE TABLE IF NOT EXISTS ticket_embedding (
    ticket_id BIGINT      PRIMARY KEY REFERENCES ticket (ticket_id) ON DELETE CASCADE,
    embedding vector(384) NOT NULL
);

-- Without an index, the nearest embeddings are found by comparing the question with
-- every row. HNSW is a graph over the embeddings that leads to the nearest ones in a
-- few steps, so a search does not read the whole table.
-- vector_cosine_ops: built for the cosine distance, the operator <=> that the search
-- in the API uses.
CREATE INDEX IF NOT EXISTS ticket_embedding_nearest
    ON ticket_embedding USING hnsw (embedding vector_cosine_ops);
