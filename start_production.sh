#!/bin/bash
# Production startup script for Telegram Bot
# This ensures clean startup with single process

set -e

cd /home/ubuntu/telegrambot

# Activate virtual environment
source venv/bin/activate

# Kill ALL uvicorn processes (more aggressive cleanup)
echo "Killing any existing uvicorn processes..."
pkill -9 -f "uvicorn webhook_server" 2>/dev/null || true
sleep 3

# Double check port is free
if lsof -ti:8000 >/dev/null 2>&1; then
    echo "Port 8000 still in use, force killing..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    sleep 2
fi

# Start uvicorn in single process mode (no workers, no auto-reload)
echo "Starting Telegram Bot (Production Mode)..."
exec uvicorn webhook_server:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level warning

