FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl libpq-dev ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir uv && uv pip install --system .

COPY FastApiClient /app/FastApiClient

EXPOSE 8002
CMD ["uvicorn", "FastApiClient.main:app", "--host", "0.0.0.0", "--port", "8002"]