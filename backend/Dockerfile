# base: the runtime dependencies. ffmpeg normalises uploaded audio before transcription.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# test: what CI runs the tests in (test-docker mounts the checkout at /src).
FROM base AS test
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

FROM base
COPY app ./app
# Data (SQLite, audio, documents) lives in /data, owned by an unprivileged user with the owner's uid.
RUN useradd --system --uid 1000 --create-home memoir \
    && mkdir -p /data && chown memoir:memoir /data
USER memoir
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
