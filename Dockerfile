# Web console (frontend + backend in one server) for container hosts such as
# Render, Railway, Fly.io or Hugging Face Spaces.
#
#   docker build -t fsoc-console .
#   docker run -p 8420:8420 -e FSOC_PASSWORD=choose-one fsoc-console
#
# Public mode is on by default here, since plugin code runs on the server.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8420 \
    FSOC_PUBLIC=1 \
    FSOC_DATA_DIR=/data

WORKDIR /app
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

COPY algorithms ./algorithms
COPY config ./config
COPY control ./control
COPY perception ./perception
COPY perf_logging ./perf_logging
COPY simulator ./simulator
COPY user_algorithms ./user_algorithms
COPY web ./web

RUN mkdir -p /data && useradd -m -u 1000 app && chown -R app /data /app
USER app

EXPOSE 8420
CMD ["python", "web/dashboard_server.py"]
