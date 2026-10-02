"""Finding tickets by what they are about.

A small language model turns a text into a list of numbers, an embedding. Texts that
mean the same thing get embeddings that point in the same direction, also when they
share no words: "cannot sign in" lands close to "login fails". The search turns the
question and every ticket into embeddings and returns the tickets that lie closest to
the question.

The model is all-MiniLM-L6-v2: 384 numbers per text, about 90 MB, and it runs on the CPU.
It is downloaded when the image is built (Dockerfile), not when the agent runs.
"""

import os

import numpy
from fastembed import TextEmbedding

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Where the Dockerfile put the model: the directory "models" next to this file. It is
# given here, in the code, and not through the environment, because the MCP server is
# started with an environment of its own that holds the API address and nothing else.
MODEL_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")

# How alike a ticket and the question must be for the ticket to count as a match.
# The similarity is 1 for the same meaning and around 0 for unrelated texts.
MIN_SIMILARITY = 0.3


class TicketSearch:
    def __init__(self):
        # Loaded at the first search, not when the program starts: it takes a second.
        self._model = None
        # The text of a ticket -> its embedding. A ticket is embedded once, and again
        # only when its title or description has changed.
        self._ticket_vectors = {}

    def find(self, query: str, tickets: list, limit: int) -> list:
        """The tickets that match the query, the best match first. Every ticket in the
        result is the ticket as the API gave it, plus "match": how alike the ticket and
        the query are, from 0 to 1."""
        query_vector = self._embed([query])[0]

        texts = []
        for ticket in tickets:
            texts.append(ticket["title"] + ". " + ticket["description"])

        self._remember(texts)

        matches = []
        for index in range(len(tickets)):
            ticket_vector = self._ticket_vectors[texts[index]]
            # Both vectors have length 1, so their dot product is the cosine of the
            # angle between them: the usual measure of how alike two embeddings are.
            similarity = float(numpy.dot(query_vector, ticket_vector))
            if similarity >= MIN_SIMILARITY:
                match = dict(tickets[index])
                match["match"] = round(similarity, 2)
                matches.append(match)

        matches.sort(key=match_of, reverse=True)
        return matches[:limit]

    def _remember(self, texts: list) -> None:
        """Embeds the ticket texts that have not been embedded before."""
        new_texts = []
        for text in texts:
            if text not in self._ticket_vectors:
                new_texts.append(text)

        if len(new_texts) == 0:
            return

        vectors = self._embed(new_texts)
        for index in range(len(new_texts)):
            self._ticket_vectors[new_texts[index]] = vectors[index]

    def _embed(self, texts: list) -> list:
        """One embedding per text, each scaled to length 1."""
        if self._model is None:
            # local_files_only: use the files in the image and never go to the network.
            self._model = TextEmbedding(MODEL_NAME, cache_dir=MODEL_DIRECTORY, local_files_only=True)

        vectors = []
        for vector in self._model.embed(texts):
            vectors.append(vector / numpy.linalg.norm(vector))
        return vectors


def match_of(match: dict) -> float:
    return match["match"]
