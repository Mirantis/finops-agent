FROM python:3.11-slim as builder

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install PDM
RUN pip install --no-cache-dir pdm

COPY pyproject.toml /app/

# Install dependencies in a virtual environment
RUN pdm install --prod --no-editable --frozen-lockfile

# ----------- Runtime image -------------
FROM python:3.11-slim as runtime

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

COPY --from=builder /app/.venv/lib/python3.11/site-packages /app/site-packages

COPY src/ /app/src/
COPY toto/ /app/toto/
COPY config.yaml /app/

# Set environment variables
ENV PYTHONPATH="/app/src:/app:/app/site-packages"
ENV PATH="/app/site-packages/bin:$PATH"

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

LABEL org.opencontainers.image.description="A forecasting agent for resource optimization"

# Expose forecast API/metrics port
EXPOSE 8081

# Entrypoint
CMD ["python", "-m", "main", "--config", "/app/config.yaml"]
