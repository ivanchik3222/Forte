FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 YOLO_OFFLINE=true YOLO_AUTOINSTALL=false \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
WORKDIR /app/backend
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./requirements.txt
COPY ML/requirements-inference.txt /app/ML/requirements-inference.txt
RUN pip install --no-cache-dir torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir -r requirements.txt -r /app/ML/requirements-inference.txt gunicorn
# Fetch only the pinned R3D backbone at build time, never during inference.
# Qwen/MLX weights and packages are deliberately absent from this Linux image.
COPY ML/download_models.py /app/ML/download_models.py
RUN python /app/ML/download_models.py --r3d
COPY backend/ .
COPY ML/*.py /app/ML/
COPY ML/deployment/ /app/ML/deployment/
COPY ML/regulations/ /app/ML/regulations/
RUN python /app/ML/check_reviewed_runtime.py
RUN mkdir -p /app/database /app/media && chmod +x /app/backend/entrypoint.sh

FROM runtime AS api
EXPOSE 6767
CMD ["/app/backend/entrypoint.sh"]

FROM runtime AS worker
CMD ["python", "-m", "flask", "--app", "app", "analysis-worker"]
