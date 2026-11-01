# Multi-stage Dockerfile for Wcoflix Downloader
# Build: force rebuild - setuptools fix
ARG BUILD_DATE=2026-11-01
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

# Install Playwright browsers in builder stage (without --with-deps to avoid font issues)
RUN python -m playwright install chromium

# Final stage
FROM python:3.12-slim

# Install runtime dependencies for Playwright (minimal set, avoiding broken font packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    fonts-liberation \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Install setuptools for pkg_resources (required by cloudscraper in Python 3.12+)
RUN pip install --no-cache-dir setuptools==81.0.0

# Create non-root user
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy backend dependencies
COPY --from=backend-builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy Playwright browsers from builder
COPY --from=backend-builder /root/.cache/ms-playwright /home/appuser/.cache/ms-playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/home/appuser/.cache/ms-playwright

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
ENV PLAYWRIGHT_BROWSERS_PATH=/home/appuser/.cache/ms-playwright

# Expose port
EXPOSE 8000

# Health check - use curl to check the health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run the application from the backend directory
WORKDIR /app/backend
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]