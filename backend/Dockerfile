FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt \
    && pip install --no-cache-dir psycopg2-binary ultralytics

COPY backend /app/backend
COPY data /app/data
COPY media /app/media
COPY scripts /app/scripts

ENV PYTHONPATH=/app/backend
ENV DETECTOR_BACKEND=demo
ENV PYTHONUNBUFFERED=1

WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
