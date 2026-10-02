FROM python:3.12-slim

WORKDIR /app

# Dependencies first, in their own layer: it is rebuilt only when the two files change.
# requirements.txt lists what the agent uses, constraints.txt pins the exact version of
# everything that gets installed, so the image is the same next month as today.
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

COPY *.py ./
COPY evals ./evals

# No root in the container. The agent writes nothing to disk.
RUN useradd --system --uid 10001 agent
USER agent

# Print output straight away instead of buffering it.
ENV PYTHONUNBUFFERED=1

# The web server around the agent (server.py). The evals and the checks run in the same
# image with another command.
CMD ["python", "server.py"]
