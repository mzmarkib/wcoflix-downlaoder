# Multi-stage Dockerfile for Wcoflix Downloader
# Build stage for frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Build stage for backend
FROM python:3.12-slim AS backend-builder

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.12-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy backend dependencies
COPY --from=backend-builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy backend code
COPY backend/ ./backend/

# Copy frontend build
COPY --from=frontend-builder /app/frontend/build ./frontend/build

# Create directories for temp files
RUN mkdir -p /tmp/wcoflix_downloads && chown -R appuser:appuser /tmp/wcoflix_downloads

# Switch to non-root user
USER appuser

# Set Python path to include backend directory
ENV PYTHONPATH=/app/backend

# Expose port
EXPOSE 8000

# Health check - use curl to check the health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run the application from the backend directory
WORKDIR /app/backend
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]