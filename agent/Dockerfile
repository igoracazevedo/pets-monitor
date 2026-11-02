FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pets_agent ./pets_agent
# config.yaml, .env e a pasta fotos/ são montados como volume
CMD ["python", "-m", "pets_agent", "varrer"]
