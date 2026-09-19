FROM python:3.10-slim

# Install ffmpeg for Whisper
RUN apt-get update && \
    apt-get install -y ffmpeg git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (to cache the layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the worker script
COPY worker.py .

# Run the worker
CMD ["python", "-u", "worker.py"]
