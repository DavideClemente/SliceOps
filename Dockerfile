FROM python:3.12-slim

# Install system deps, PrusaSlicer, and xvfb for BambuStudio headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    prusa-slicer \
    xvfb \
    libgl1 \
    libegl1 \
    libgstreamer-plugins-base1.0-0 \
    fuse \
    && rm -rf /var/lib/apt/lists/*

# Download BambuStudio AppImage
RUN wget -q "https://github.com/bambulab/BambuStudio/releases/download/v02.02.00.04/Bambu_Studio_linux_ubuntu-v02.02.00.04.AppImage" \
    -O /usr/local/bin/bambu-studio-app \
    && chmod +x /usr/local/bin/bambu-studio-app

# Create wrapper script that runs BambuStudio through xvfb
RUN printf '#!/bin/sh\nxvfb-run --auto-servernum --server-args="-screen 0 1024x768x24" /usr/local/bin/bambu-studio-app --appimage-extract-and-run "$@"\n' \
    > /usr/local/bin/bambu-studio \
    && chmod +x /usr/local/bin/bambu-studio

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for caching
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY app/ app/

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
