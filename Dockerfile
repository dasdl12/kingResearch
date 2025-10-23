FROM ghcr.io/astral-sh/uv:python3.12-bookworm

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Install system dependencies including libpq
RUN apt-get update && apt-get install -y \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*
    
WORKDIR /app

# Copy dependency files first
COPY pyproject.toml uv.lock ./

# Install dependencies (Railway has its own caching)
RUN uv sync --locked --no-install-project

# Copy the application into the container.
COPY . /app

# Install the project
RUN uv sync --locked

EXPOSE 8000

# Set Python path to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/.venv"

# Run the application
CMD ["sh", "-c", "python server.py --host 0.0.0.0 --port ${PORT:-8000}"]
