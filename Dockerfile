FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# Use shell form so the PORT env var provided by hosting platforms (Render) is respected.
# Default to 8000 when PORT is not set (for local development).
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
