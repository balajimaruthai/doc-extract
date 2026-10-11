FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY app/backend/requirements.txt ./app/backend/
RUN pip install --no-cache-dir -r ./app/backend/requirements.txt

COPY app/backend/ ./app/backend/
COPY app/frontend/dist/ ./app/frontend/dist/

RUN mkdir -p data/uploads data/exports data/logs models/small models/medium models/large

ENV DOCEXTRACT_HOST=0.0.0.0
ENV PORT=37240

EXPOSE 37240

WORKDIR /app/app/backend

CMD ["python", "main.py"]
