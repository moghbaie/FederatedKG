# One image for all agents; persona identity comes from agents/persona_*/agent.env and the
# private graph from a per-agent read-only mount. Build context is the repository root.
FROM python:3.12-slim-bookworm
WORKDIR /app
RUN useradd --system --uid 10002 agent && mkdir -p /var/lib/fkg && chown agent /var/lib/fkg
COPY agents/common/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY agents/common/app /app/app
COPY similarity /app/similarity
USER agent
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
