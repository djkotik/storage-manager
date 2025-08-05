# Multi-stage build for unRAID Storage Analyzer
FROM node:18-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --only=production

COPY frontend/ ./
RUN npm run build

FROM python:3.11-alpine AS backend-builder

WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-alpine

# Install system dependencies
RUN apk add --no-cache \
    ffmpeg \
    mediainfo \
    && rm -rf /var/cache/apk/*

WORKDIR /app

# Copy backend dependencies
COPY --from=backend-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin

# Copy application code
COPY backend/ ./backend/
COPY --from=frontend-builder /app/frontend/dist ./backend/static

# Create necessary directories
RUN mkdir -p /app/data /app/logs

# Set environment variables
ENV PYTHONPATH=/app
ENV FLASK_APP=backend.app
ENV FLASK_ENV=production
ENV DATA_PATH=/data
ENV SCAN_TIME=01:00
ENV MAX_SCAN_DURATION=6

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8080/api/health || exit 1

# Start the application
CMD ["python", "-m", "flask", "run", "--host=0.0.0.0", "--port=8080"] 