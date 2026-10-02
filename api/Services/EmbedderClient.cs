using TicketApi.Errors;

namespace TicketApi.Services
{
    // Talks to the embedder service (embedder/main.py): texts in, embeddings out.
    //
    // An embedding is a list of 384 numbers that says what a text is about. Two texts
    // that mean the same thing get embeddings that lie close to each other.
    public class EmbedderClient
    {
        // Made by ASP.NET with the address of the embedder already set (Program.cs).
        private readonly HttpClient _http;

        public EmbedderClient(HttpClient http)
        {
            _http = http;
        }

        // One embedding per text, in the same order as the texts.
        // Throws EmbedderUnavailableException when the embedder gives no usable answer.
        public async Task<List<float[]>> EmbedAsync(List<string> texts)
        {
            var request = new EmbedRequest();
            request.Texts = texts;

            try
            {
                // POST /embed with the body {"texts": [...]}.
                HttpResponseMessage response = await _http.PostAsJsonAsync("/embed", request);

                // Throws HttpRequestException when the status code is not 2xx.
                response.EnsureSuccessStatusCode();

                EmbedResponse body = await response.Content.ReadFromJsonAsync<EmbedResponse>();
                return body.Vectors;
            }
            catch (HttpRequestException error)
            {
                // No connection, or an answer that was not 2xx.
                throw new EmbedderUnavailableException(error);
            }
            catch (TaskCanceledException error)
            {
                // No answer within the timeout set in Program.cs.
                throw new EmbedderUnavailableException(error);
            }
        }

        // The two JSON bodies. Only this class uses them.

        private class EmbedRequest
        {
            public List<string> Texts { get; set; }
        }

        private class EmbedResponse
        {
            public List<float[]> Vectors { get; set; }
        }
    }
}
