FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*

# Copy repo (build context = repo root)
COPY . .

# Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Data dir for config.json + cache
RUN mkdir -p /app/data

EXPOSE 8080

ENV GC_HOST=0.0.0.0

CMD ["python3", "serve.py", "--no-browser", "--port", "8080"]
