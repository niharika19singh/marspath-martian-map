FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend codebase
COPY backend/ ./backend/
COPY docs/ ./docs/

ENV PYTHONPATH=/app/backend
ENV MARSPATH_ENV=production
ENV MARSPATH_HOST=0.0.0.0
ENV MARSPATH_PORT=8000

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "backend"]
