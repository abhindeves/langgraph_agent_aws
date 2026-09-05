# Stage 1: Build virtual environment with uv
FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv for fast, reliable dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency specifications
COPY pyproject.toml uv.lock ./

# Install production dependencies into a standalone virtualenv
RUN uv sync --frozen --no-dev --no-install-project

# Stage 2: Minimal runtime container
FROM python:3.12-slim AS runtime

WORKDIR /app

# Create non-root user for container security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy application source code
COPY app /app/app

# Set non-root ownership
RUN chown -R appuser:appuser /app
USER appuser

# Expose FastAPI service port
EXPOSE 8000

# Run uvicorn on container startup
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
