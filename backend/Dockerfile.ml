FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 YOLO_OFFLINE=true YOLO_AUTOINSTALL=false
WORKDIR /app/backend
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./requirements.txt
COPY ML/requirements-inference.txt /app/ML/requirements-inference.txt
RUN pip install --no-cache-dir torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir -r requirements.txt -r /app/ML/requirements-inference.txt
COPY backend/ .
COPY ML/inference.py ML/predict_objects.py ML/train_detector.py ML/interaction_timeline.py /app/ML/
COPY ML/deployment/ /app/ML/deployment/
CMD ["python", "-m", "flask", "--app", "app", "analysis-worker"]
