FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/models/huggingface XDG_CACHE_HOME=/models/cache
RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 libespeak-ng1 ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY voice_backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY voice_backend /app/voice_backend
RUN mkdir -p /app/data /models
EXPOSE 7860
CMD ["python", "-m", "voice_backend.app"]
