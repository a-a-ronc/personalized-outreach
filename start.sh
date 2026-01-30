#!/bin/bash
set -e

# Use PORT from environment or default to 8080
PORT=${PORT:-8080}

echo "Starting gunicorn on port $PORT"
exec gunicorn wsgi:app --bind 0.0.0.0:$PORT --timeout 120 --workers 2
