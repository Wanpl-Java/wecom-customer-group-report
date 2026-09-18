FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data ./data
COPY config.example.yaml ./config.example.yaml
COPY lib ./lib

RUN mkdir -p /app/output /app/keys /app/data

ENV PYTHONUNBUFFERED=1 \
    WECOM_REPORT_CONFIG=/app/config.yaml

EXPOSE 8088

# 默认 Web；同步/出报表可用 docker compose exec 调 CLI
CMD ["python", "-m", "app.main", "serve"]
