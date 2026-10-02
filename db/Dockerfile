# PostgreSQL 16 with the pgvector extension installed (db/init/005_search.sql turns it
# on). The image is the official postgres:16 image plus that one extension, on the same
# Debian release.
FROM pgvector/pgvector:pg16-trixie
COPY init/ /docker-entrypoint-initdb.d/
