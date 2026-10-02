"""The conversations of the web interface, stored in PostgreSQL.

Two things are stored, in the same database as the tickets:

- The list of conversations is the table "conversation" (db/init/003_conversations.sql):
  one row per conversation, with the user it belongs to. The class Conversations below
  reads and writes that table.
- The messages of a conversation are kept by the graph's checkpointer, which here is
  LangGraph's PostgreSQL checkpointer instead of the in-memory one. It creates its own
  tables. open_database() below sets it up.

Both use one pool of database connections, opened when the server starts.
"""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


async def open_database(database_url: str) -> AsyncConnectionPool:
    """Opens the pool of connections. The caller closes it with pool.close().

    autocommit: every statement is saved as it is run, there are no open transactions
    to remember to commit. dict_row: a row comes back as a dictionary, column name to
    value. The checkpointer requires both settings."""
    pool = AsyncConnectionPool(
        conninfo=database_url,
        kwargs={"autocommit": True, "row_factory": dict_row},
        min_size=1,
        max_size=5,
        open=False,
    )
    await pool.open()
    return pool


async def build_checkpointer(pool: AsyncConnectionPool) -> AsyncPostgresSaver:
    """The checkpointer that keeps the graph's state in the database.

    setup() creates the checkpointer's tables if they are not there yet, so it is run
    every time the server starts."""
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()
    return checkpointer


class Conversations:
    """The table "conversation". Every method that takes a username only sees that
    user's conversations: someone else's conversation is the same as no conversation."""

    def __init__(self, pool: AsyncConnectionPool):
        self._pool = pool

    async def create(self, username: str) -> dict:
        query = "INSERT INTO conversation (username) VALUES (%s) RETURNING *"
        return await self._fetch_one(query, [username])

    async def list_for(self, username: str) -> list:
        """The user's conversations, the latest one used first."""
        query = "SELECT * FROM conversation WHERE username = %s ORDER BY updated_at DESC"
        async with self._pool.connection() as connection:
            cursor = await connection.execute(query, [username])
            return await cursor.fetchall()

    async def find(self, conversation_id: int, username: str):
        """The conversation as a dictionary, or None if the user has no such one."""
        query = "SELECT * FROM conversation WHERE conversation_id = %s AND username = %s"
        return await self._fetch_one(query, [conversation_id, username])

    async def set_title(self, conversation_id: int, title: str) -> None:
        await self._execute("UPDATE conversation SET title = %s WHERE conversation_id = %s", [title, conversation_id])

    async def mark_failed(self, conversation_id: int) -> None:
        await self._execute("UPDATE conversation SET failed = true WHERE conversation_id = %s", [conversation_id])

    async def mark_used(self, conversation_id: int) -> None:
        await self._execute("UPDATE conversation SET updated_at = now() WHERE conversation_id = %s", [conversation_id])

    async def delete(self, conversation_id: int) -> None:
        await self._execute("DELETE FROM conversation WHERE conversation_id = %s", [conversation_id])

    # The values always go in as parameters (%s), never pasted into the SQL text.

    async def _fetch_one(self, query: str, parameters: list):
        async with self._pool.connection() as connection:
            cursor = await connection.execute(query, parameters)
            return await cursor.fetchone()

    async def _execute(self, query: str, parameters: list) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(query, parameters)
