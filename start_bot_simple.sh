#!/bin/bash
# Simple production start script

cd /home/ubuntu/telegrambot
source venv/bin/activate

# Kill any existing
pkill -9 -f "uvicorn webhook_server" || true
sleep 2

# Run migrations
alembic upgrade head

# Start bot (exec replaces this process)
exec python3 -m uvicorn webhook_server:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level warning

