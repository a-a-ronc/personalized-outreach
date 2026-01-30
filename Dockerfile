# Use official Python image
FROM python:3.12-slim

# Install Node.js
RUN apt-get update && apt-get install -y \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy dashboard and build frontend
COPY dashboard/package*.json ./dashboard/
RUN cd dashboard && npm install

COPY dashboard/ ./dashboard/
RUN cd dashboard && npm run build

# Copy rest of application
COPY . .

# Expose port (Railway will override with $PORT)
EXPOSE 8080

# Start command
CMD gunicorn wsgi:app --bind 0.0.0.0:$PORT --timeout 120 --workers 2
