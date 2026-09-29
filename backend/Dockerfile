# syntax=docker/dockerfile:1
# Multi-stage build: dependencies are installed in a builder stage so the
# runtime image carries no compilers or pip caches.

FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt requirements-dev.txt ./
ARG INSTALL_DEV=true
RUN if [ "$INSTALL_DEV" = "true" ]; then pip install -r requirements-dev.txt; else pip install -r requirements.txt; fi

# Download the embedding model at build time so containers start fast and
# work offline (instead of downloading ~130 MB on first request).
ENV EMBEDDING_CACHE_DIR=/opt/models
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/opt/models')"

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" EMBEDDING_CACHE_DIR=/opt/models
# Run as an unprivileged user (defense in depth if the app is compromised).
RUN useradd --create-home --uid 1000 app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder --chown=app:app /opt/models /opt/models
WORKDIR /app
COPY --chown=app:app . .
RUN mkdir -p /app/storage/uploads && chown -R app:app /app/storage
USER app
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
