# Build context is the repository root; .dockerignore removes all private fixtures from the context.
FROM python:3.12-slim-bookworm
WORKDIR /app
RUN useradd --system --uid 10001 registry
COPY registry/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY registry/app /app/app
COPY registry/alembic.ini /app/alembic.ini
COPY registry/migrations /app/migrations
COPY similarity/public_topics /app/similarity/public_topics
COPY similarity/__init__.py /app/similarity/__init__.py
COPY data/synthetic/public /app/public
USER registry
EXPOSE 8000
# Schema is owned by Alembic migrations; the app only seeds public profiles.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app_factory --factory --host 0.0.0.0 --port 8000"]
