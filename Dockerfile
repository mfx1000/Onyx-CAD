FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for cadquery/OCP
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglx-mesa0 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway sets PORT automatically, default to 8080
ENV PORT=8080

# Run gunicorn on 0.0.0.0 (required for Railway)
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120 app:app
