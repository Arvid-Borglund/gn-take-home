"""The embedder: turns texts into embeddings, over HTTP. This is the program the
embedder container runs.

    python main.py    starts the server on port 8000

    POST /embed    {"texts": ["...", "..."]}  ->  {"vectors": [[384 numbers], ...]}
    GET  /health

A small language model turns a text into a list of numbers, an embedding. Texts that
mean the same thing get embeddings that point in the same direction, also when they
share no words: "cannot sign in" lands close to "login fails".

The ticket API is the only caller. It asks for an embedding when a ticket is written and
when someone searches, and it stores the embeddings of the tickets in the database. The
search itself happens there (db/init/005_search.sql). This service stores nothing.

The model is all-MiniLM-L6-v2: 384 numbers per text, about 90 MB, and it runs on the CPU.
It is downloaded when the image is built (Dockerfile), not when the service runs.
"""

import os

import numpy
import uvicorn
from fastapi import FastAPI
from fastembed import TextEmbedding
from pydantic import BaseModel

PORT = 8000

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Where the Dockerfile put the model: the directory "models" next to this file.
MODEL_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")

# Loaded once, when the service starts. It takes about a second.
# local_files_only: use the files in the image and never go to the network.
model = TextEmbedding(MODEL_NAME, cache_dir=MODEL_DIRECTORY, local_files_only=True)


# The JSON bodies. FastAPI checks an incoming body against the class and answers 422
# when it does not fit.

class EmbedRequest(BaseModel):
    texts: list[str]


class EmbedResponse(BaseModel):
    vectors: list[list[float]]


def embed(request: EmbedRequest) -> EmbedResponse:
    """One embedding per text, in the same order as the texts."""
    vectors = []
    for vector in model.embed(request.texts):
        # Scaled to length 1. The database compares two embeddings by the angle between
        # them, and with length 1 the comparison is the same whichever way it is done.
        unit_vector = vector / numpy.linalg.norm(vector)
        vectors.append(unit_vector.tolist())

    response = EmbedResponse(vectors=vectors)
    return response


def health() -> dict:
    # The model is loaded before the server starts, so an answer means it is there.
    return {"status": "ok", "model": MODEL_NAME}


app = FastAPI(title="Embedder")
app.add_api_route("/embed", embed, methods=["POST"])
app.add_api_route("/health", health, methods=["GET"])


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
