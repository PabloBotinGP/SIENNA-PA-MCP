FROM python:3.11-slim

WORKDIR /workspace

# Install git and other dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY mcp-server/pyproject.toml /tmp/
RUN pip install --no-cache-dir -e /workspace/mcp-server

# Set environment variables
ENV PYTHONUNBUFFERED=1

CMD ["/bin/bash"]
