FROM python:3.12-slim

WORKDIR /tests

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

# -v lists every test by name. The cache directory is turned off: the container is
# thrown away after the run.
CMD ["pytest", "-v", "-p", "no:cacheprovider"]
