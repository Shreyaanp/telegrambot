#!/bin/bash
set -e

cd /home/ubuntu/telegrambot
source venv/bin/activate

# Kill any existing processes on port 8000
lsof -ti:8000 | xargs -r kill -9 || true
sleep 2

# Start uvicorn
exec uvicorn webhook_server:app --host 0.0.0.0 --port 8000

