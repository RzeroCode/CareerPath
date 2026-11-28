# Local development image (see compose.yaml). Not a production server.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# The app user must own /app so `docker compose up --watch` can update files in it.
RUN useradd --create-home app && install -d -o app -g app /app
WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY --chown=app:app . .
USER app
