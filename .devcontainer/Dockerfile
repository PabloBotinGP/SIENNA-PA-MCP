# =============================================================================
# SIENNA-PA-MCP dev-container
# =============================================================================
FROM python:3.12-slim

# ----------------------------------------------------------------------------- 
# Allow Docker to pass along the target platform (e.g., linux/amd64 or linux/arm64)
# ----------------------------------------------------------------------------- 
ARG TARGETPLATFORM

# ----------------------------------------------------------------------------- 
# 1. System packages + Node.js 20
# ----------------------------------------------------------------------------- 
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl wget git vim nano build-essential gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# ----------------------------------------------------------------------------- 
# 2. Runtime environment variables
# ----------------------------------------------------------------------------- 
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ----------------------------------------------------------------------------- 
# 3. Python package manager (uv) for faster dependency installation
# ----------------------------------------------------------------------------- 
RUN pip install --no-cache-dir uv

# ----------------------------------------------------------------------------- 
# 4. Non-root user (for VS Code Remote-Containers)
# ----------------------------------------------------------------------------- 
RUN useradd --create-home --shell /bin/bash vscode && \
    mkdir -p /workspace && \
    chown -R vscode:vscode /workspace

USER vscode

# ----------------------------------------------------------------------------- 
# 5. Workspace location and default shell
# ----------------------------------------------------------------------------- 
WORKDIR /workspace/SIENNA-PA-MCP
CMD ["/bin/bash"]
