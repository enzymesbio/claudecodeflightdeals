FROM python:3.11-slim

# Minimal system deps + git for GitHub push
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Let Playwright install Chromium + ALL its own deps (handles libasound2 vs libasound2t64 automatically)
RUN playwright install chromium --with-deps

COPY . .

RUN mkdir -p /data/archive /data/logs

CMD ["python", "railway_entrypoint.py"]
