FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src/ src/
COPY server/ server/

RUN pip install --no-cache-dir ".[server]"

EXPOSE 8100

ENV ENGRAM_DB_PATH=/data/memory.db

VOLUME ["/data"]

CMD ["uvicorn", "server.api:app", "--host", "0.0.0.0", "--port", "8100"]
