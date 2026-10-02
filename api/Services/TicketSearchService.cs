using System.Globalization;
using Microsoft.EntityFrameworkCore;
using TicketApi.Contracts;
using TicketApi.Data;
using TicketApi.Errors;
using TicketApi.Models;

namespace TicketApi.Services
{
    // Search by meaning: "the screen keeps blinking" finds a ticket called
    // "Monitor flickers", although they share no words.
    //
    // Every ticket has an embedding of its title and description, stored in the table
    // ticket_embedding (db/init/005_search.sql). A search turns the question into an
    // embedding too and asks the database for the tickets whose embeddings lie closest.
    // The embeddings come from the embedder service; the comparing is done by the
    // database (pgvector).
    //
    // The table is only touched from this class, with SQL written by hand: EF has no
    // type for a vector column.
    public class TicketSearchService
    {
        // How alike a ticket and the question must be for the ticket to count as a match.
        private const double MinimumMatch = 0.3;

        private const int MaximumLimit = 20;

        private readonly TicketDbContext _db;
        private readonly EmbedderClient _embedder;
        private readonly ILogger<TicketSearchService> _logger;

        public TicketSearchService(TicketDbContext db, EmbedderClient embedder, ILogger<TicketSearchService> logger)
        {
            _db = db;
            _embedder = embedder;
            _logger = logger;
        }

        // The tickets that match the question, the best match first.
        public async Task<List<TicketMatchResponse>> SearchAsync(string question, int limit)
        {
            if (string.IsNullOrWhiteSpace(question))
            {
                throw new TicketValidationException("The parameter 'q' is required and cannot be empty.");
            }

            if (limit < 1 || limit > MaximumLimit)
            {
                throw new TicketValidationException(
                    "'" + limit + "' is not a valid limit. It must be between 1 and " + MaximumLimit + ".");
            }

            await EmbedMissingTicketsAsync();

            var texts = new List<string>();
            texts.Add(question.Trim());
            List<float[]> vectors = await _embedder.EmbedAsync(texts);
            string questionVector = ToVectorText(vectors[0]);

            // <=> is pgvector's cosine distance between two embeddings: 0 when they point
            // in the same direction, 1 when they have nothing in common. The match is
            // 1 minus the distance.
            //
            // The inner query is the one the index answers: the embeddings nearest to
            // the question, nearest first, and no more than the limit. The outer query
            // fetches the tickets they belong to and drops the ones that are too far
            // away to count as a match.
            //
            // Every {value} below is sent to the database as a parameter, apart from
            // the SQL text. ::vector turns the text "[0.1,0.2,...]" into a vector.
            List<TicketMatch> rows = await _db.TicketMatches.FromSql($@"
                SELECT o.ticket_id, o.title, o.description, o.status, o.resolution,
                       o.created, o.updated, o.version_no, nearest.match
                FROM (
                    SELECT ticket_id, 1 - (embedding <=> {questionVector}::vector) AS match
                    FROM ticket_embedding
                    ORDER BY embedding <=> {questionVector}::vector
                    LIMIT {limit}
                ) AS nearest
                JOIN ticket_overview o USING (ticket_id)
                WHERE nearest.match >= {MinimumMatch}
                ORDER BY nearest.match DESC").ToListAsync();

            var result = new List<TicketMatchResponse>();
            foreach (TicketMatch row in rows)
            {
                result.Add(ToResponse(row));
            }

            return result;
        }

        // Called by TicketService when a ticket has been created, and when its title or
        // description has changed.
        //
        // Saving a ticket must not depend on the embedder. If the embedder does not
        // answer, the ticket is left without an embedding, and the next search fills
        // it in (EmbedMissingTicketsAsync).
        public async Task EmbedTicketAsync(Ticket ticket)
        {
            var texts = new List<string>();
            texts.Add(TextOf(ticket));

            List<float[]> vectors;
            try
            {
                vectors = await _embedder.EmbedAsync(texts);
            }
            catch (EmbedderUnavailableException error)
            {
                // An embedding from before the change is of a text the ticket no longer
                // has. It is removed, so that the ticket counts as not embedded.
                await _db.Database.ExecuteSqlAsync(
                    $"DELETE FROM ticket_embedding WHERE ticket_id = {ticket.TicketId}");

                _logger.LogWarning(
                    error,
                    "Ticket {TicketId} was saved without an embedding: the embedder did not answer.",
                    ticket.TicketId);
                return;
            }

            await SaveEmbeddingAsync(ticket.TicketId, vectors[0]);
        }

        // Embeds the tickets that have no embedding yet: the example tickets, which are
        // put into the database with SQL, and tickets that were saved while the embedder
        // did not answer. Usually there are none.
        private async Task EmbedMissingTicketsAsync()
        {
            List<Ticket> tickets = await _db.Tickets.FromSql($@"
                SELECT t.*
                FROM ticket t
                WHERE NOT EXISTS (SELECT 1 FROM ticket_embedding e WHERE e.ticket_id = t.ticket_id)")
                .ToListAsync();

            if (tickets.Count == 0)
            {
                return;
            }

            var texts = new List<string>();
            foreach (Ticket ticket in tickets)
            {
                texts.Add(TextOf(ticket));
            }

            // One call for all of them. The embeddings come back in the same order.
            List<float[]> vectors = await _embedder.EmbedAsync(texts);

            for (int index = 0; index < tickets.Count; index++)
            {
                await SaveEmbeddingAsync(tickets[index].TicketId, vectors[index]);
            }
        }

        private async Task SaveEmbeddingAsync(long ticketId, float[] vector)
        {
            string vectorText = ToVectorText(vector);

            // SELECT ... FROM ticket instead of VALUES: nothing is inserted if the ticket
            // was deleted while its embedding was being made.
            // ON CONFLICT: the ticket already has an embedding, of its old text, and
            // the new one takes its place.
            await _db.Database.ExecuteSqlAsync($@"
                INSERT INTO ticket_embedding (ticket_id, embedding)
                SELECT ticket_id, {vectorText}::vector FROM ticket WHERE ticket_id = {ticketId}
                ON CONFLICT (ticket_id) DO UPDATE SET embedding = EXCLUDED.embedding");
        }

        // The text an embedding is made from.
        private static string TextOf(Ticket ticket)
        {
            return ticket.Title + ". " + ticket.Description;
        }

        // pgvector reads a vector written as text: [0.12,-0.03,...]
        private static string ToVectorText(float[] vector)
        {
            var numbers = new List<string>();
            foreach (float number in vector)
            {
                // InvariantCulture: a point as the decimal sign, whatever the language
                // settings of the machine are.
                numbers.Add(number.ToString(CultureInfo.InvariantCulture));
            }

            return "[" + string.Join(",", numbers) + "]";
        }

        private static TicketMatchResponse ToResponse(TicketMatch row)
        {
            var response = new TicketMatchResponse();
            response.TicketId = row.TicketId;
            response.Title = row.Title;
            response.Description = row.Description;
            response.Status = row.Status.ToString();
            response.Resolution = row.Resolution;
            response.Created = row.Created;
            response.Updated = row.Updated;
            response.VersionNo = row.VersionNo;
            response.Match = Math.Round(row.Match, 2);
            return response;
        }
    }
}
