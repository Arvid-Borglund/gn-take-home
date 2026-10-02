FROM python:3.12-slim

WORKDIR /app

# Dependencies first, in their own layer: it is rebuilt only when the two files change.
# requirements.txt lists what the service uses, constraints.txt pins the exact version
# of everything that gets installed, so the image is the same next month as today.
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

# The embedding model, about 90 MB. It is downloaded here, when the image is built, into
# the directory main.py reads it from. The service fetches nothing when it runs.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/all-MiniLM-L6-v2', cache_dir='/app/models')"

COPY *.py ./

# No root in the container. The service only reads the model and writes nothing to disk.
RUN useradd --system --uid 10001 embedder
USER embedder

# Print output straight away instead of buffering it.
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
