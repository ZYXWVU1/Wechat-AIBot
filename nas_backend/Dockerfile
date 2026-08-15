FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY app /app/app
COPY requirements.txt /app/requirements.txt

RUN python -m pip install --no-cache-dir -r /app/requirements.txt \
    && useradd --create-home --uid 10001 bot \
    && mkdir -p /data /config \
    && chown -R bot:bot /app /data /config

USER bot

CMD ["python", "-m", "app.main"]

