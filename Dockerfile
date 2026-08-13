# Stage 1: Build React Frontend UI (meeting-summariser-ui)
FROM node:20-alpine AS ui-builder
WORKDIR /ui
COPY meeting-summariser-ui/package*.json ./
RUN npm install
COPY meeting-summariser-ui/ .
ARG BUILD_TIMESTAMP
ENV VITE_API_URL=""
RUN npm run build

# Stage 2: Python Backend Application
FROM python:3.9-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    libsndfile1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install CUDA-enabled PyTorch, torchaudio, and Python dependencies in a single layer
RUN pip install --no-cache-dir torch torchaudio --extra-index-url https://download.pytorch.org/whl/cu121 -r requirements.txt

# Copy application code
COPY . .

# Copy compiled React UI build into application
COPY --from=ui-builder /ui/dist ./meeting-summariser-ui/dist

# Create storage directory
RUN mkdir -p job_results

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0

# Expose port
EXPOSE 8000

# Command to run the application with multi-process workers
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]