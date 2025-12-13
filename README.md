# Telegram Bot (Python, aiogram)

Minimal starter that you can run locally with polling and later host on AWS with a webhook.

## Setup (local, polling)
- Install Python 3.11+ and virtualenv.
- `python -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements.txt`
- Create your bot with @BotFather, copy the token (keep it private), then set `export BOT_TOKEN=123:ABC...`
- Run: `python bot.py`

## Files
- `bot.py` — aiogram dispatcher with `/start`, `/help`, and echo handlers. Uses polling for local use.
- `webhook_app.py` — FastAPI app exposing `/health` and a webhook endpoint (path configurable via `WEBHOOK_PATH`).
- `Dockerfile` — container entrypoint running `uvicorn` for the webhook app.
- `requirements.txt` — pinned deps.

## Going live on Telegram (webhook on AWS, high level)
1) Build and push the container to ECR: `docker build -t your-bot .` then `docker tag`/`docker push`.
2) Run on AWS (examples):
   - ECS Fargate behind an ALB (HTTPS termination).
   - Lambda behind API Gateway (HTTP API). For Lambda, you can wrap FastAPI with `mangum` (not included here).
3) Set env vars on the service: `BOT_TOKEN`, and optionally `WEBHOOK_PATH` (e.g., `/webhook/<random>`) to make the endpoint harder to guess.
4) Register the webhook once after deploy (replace domain/path):
   ```bash
   curl -X POST "https://api.telegram.org/bot$BOT_TOKEN/setWebhook" \
        -d "url=https://yourdomain.com/webhook/<random>"
   ```
5) Add persistence if you track state: DynamoDB or RDS; for caching/rate limits, ElastiCache Redis.
6) Lock down: HTTPS only, keep the webhook path secret-ish, rotate the token in Secrets Manager, and restrict outbound calls as needed.

If you want, I can add the FastAPI webhook entrypoint and a Dockerfile so it’s deploy-ready for AWS.***
