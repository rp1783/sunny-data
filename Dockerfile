FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    rsync \
    openssh-client \
    ffmpeg \
    libcapnp-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .
COPY schemas/ /app/schemas/

RUN adduser --disabled-password --gecos "" appuser \
    && mkdir -p /app/data \
    && chown appuser:appuser /app/data
USER appuser

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
