# CLOTE Server - FastAPI + SQLite
FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install (skip venv — Docker IS the isolation)
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server source (exclude venv, storage, db — handled by volumes)
COPY server/main.py .
COPY server/auth.py .
COPY server/config.py .
COPY server/database.py .
COPY server/routes/ ./routes/
COPY server/models/ ./models/

# Copy client (served as static file)
COPY client/CLOTE.html ./client/CLOTE.html

# Create storage directories (will be overridden by volume mounts)
RUN mkdir -p storage/files storage/versions logs

# Non-root user for security
RUN useradd -m -u 1000 clote && chown -R clote:clote /app
USER clote

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
