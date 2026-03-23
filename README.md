# caltrain-alerts (MVP)

This project ingests Caltrain disruption signals from:

1. `511.org` GTFS-RT service alerts
2. Reddit (`r/caltrain`, `r/bayarea`)

It then classifies whether an SMS alert is needed (using Anthropic Claude Haiku) and sends texts to subscribers via Twilio.

## Architecture (MVP)

### High-level flow

```
┌─────────────┐     enqueue periodic tasks      ┌─────────────┐
│ Celery Beat │ ──────────────────────────────► │ Redis       │
│ (scheduler) │   (broker + result backend)     │ (broker)    │
└─────────────┘                                 └──────┬──────┘
                                                       │
                                                       │ workers consume
                                                       ▼
                                                ┌─────────────┐
                                                │ Celery      │
                                                │ Worker(s)   │
                                                └──────┬──────┘
                                                       │
                       ┌───────────────────────────────┼───────────────────────────────┐
                       ▼                               ▼                               ▼
              poll_511 / poll_reddit            handle_raw_report              (optional)
              fetch external APIs               classify + dedup + SMS
                       │                               │
                       ▼                               ▼
                ┌──────────────┐                 ┌──────────────┐
                │ Postgres     │◄──────────────│ Postgres     │
                │ raw_reports  │               │ incidents,   │
                └──────────────┘               │ subscribers, │
                                               │ send_log, …  │
                                               └──────────────┘

┌─────────────┐
│ FastAPI     │  HTTP: admin subscribers, health, etc. (reads/writes Postgres)
│ (uvicorn)   │
└─────────────┘
```

### Processes (what runs where)

| Process | Role |
|--------|------|
| **Celery Beat** | Reads `beat_schedule` in `app.tasks.celery_app` and **publishes** `poll_511` / `poll_reddit` to Redis on each interval. Only one Beat instance should run per schedule (avoid duplicate ticks). |
| **Celery Worker** | **Consumes** tasks from Redis, executes Python in `app.tasks.poll_tasks`, and writes results back via the configured backend. |
| **Redis** | **Message broker** (task queue) and **result backend** for Celery. |
| **FastAPI (`app.main`)** | Serves HTTP; not required for polling, but used for admin APIs and app wiring. |
| **Postgres** | Durable store: `raw_reports`, `incidents`, classifications, subscribers, send logs. |

### Task pipeline (data path)

1. **Beat → broker**: Beat emits tasks named `app.tasks.poll_tasks.poll_511` and `app.tasks.poll_tasks.poll_reddit` on configurable intervals (`poll_*_interval_seconds` in settings).
2. **Worker → poll tasks**: Workers run `poll_511` / `poll_reddit`, which call ingestion code, normalize rows, and insert new rows into **`raw_reports`** (skipping duplicates by source + external id).
3. **Chained work**: For each newly created raw report, `handle_raw_report` is queued. It:
   - **Dedupes / merges** into an **`incidents`** row (`dedup.py`)
   - **Classifies** severity via Claude Haiku (`claude_classifier.py`)
   - **Sends SMS** via Twilio when severity ≥ `SEND_MIN_SEVERITY`, with per-subscriber cooldown via **`send_log`**

### How to read worker logs

- **`Task … received` / `succeeded`**: The worker registered the task and finished it. A return value of **`0`** from `poll_511` / `poll_reddit` means *no new* `raw_reports` rows were inserted this run (nothing new from the source, or sources disabled in env).
- **`Received unregistered task`**: Worker did not import the module that defines that task name; fix by ensuring `poll_tasks` is loaded on worker startup (see `backend/app/tasks/celery_app.py`).
- **Bursts of duplicate tasks** at the same timestamp: Often a **backlog** in Redis, a **restarted** Beat/Worker, or **multiple Beat processes** scheduling the same jobs—run a single Beat and `celery purge` if you need a clean queue.

### Code map

- Celery app + schedule: `backend/app/tasks/celery_app.py`
- Polling and downstream handling: `backend/app/tasks/poll_tasks.py`

## Required environment variables

Copy `.env.example` to `.env` and fill in values.

### Core
- `DATABASE_URL`
- Redis connection:
  - `REDIS_URL` (full URL), or
  - `REDIS_HOST` + `REDIS_PORT` + `REDIS_PASSWORD` + (`REDIS_TLS=true|false`)
  - Railway managed Redis aliases: `REDISHOST`, `REDISPORT`, `REDISUSER`, `REDISPASSWORD`, and/or `REDIS_PUBLIC_URL`

### 511.org
- `SOURCES_511_ENABLED=true/false`
- `API_511_KEY`

### Reddit (praw)
- `SOURCES_REDDIT_ENABLED=true/false`
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USERNAME`
- `REDDIT_PASSWORD`
- `REDDIT_USER_AGENT`
- `REDDIT_SUBREDDITS` (comma-separated)

### Anthropic / Claude
- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MODEL` (default: `claude-3-5-haiku-latest`)

### Twilio
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`

### Notification controls
- `SEND_MIN_SEVERITY` (default: `CRITICAL`)
- `INCIDENT_DEDUP_WINDOW_MINUTES` (default: `10`)
- `SUBSCRIBER_SEND_COOLDOWN_MINUTES` (default: `60`)
- `SMS_TEMPLATE` (supports `{{severity}}`, `{{title}}`, `{{message}}`)

### Admin (optional)
- `ADMIN_API_KEY` (if set, requires `X-Admin-Token` header on admin routes)

## Database migrations

From `backend/`:

```bash
alembic upgrade head
```

## Run locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Run Postgres + Redis (examples: `docker compose` or your preferred local setup), then:

1. Run DB migrations:
   ```bash
   cd backend
   alembic upgrade head
   ```
2. Start the API (run from `backend/` so Python can import `app.*`):
   ```bash
   cd backend
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
3. Start the worker (from `backend/`):
   ```bash
   cd backend
   celery -A app.tasks.celery_app:celery_app worker --loglevel=INFO
   ```
4. Start the scheduler (beat):
   ```bash
   cd backend
   celery -A app.tasks.celery_app:celery_app beat --loglevel=INFO
   ```

Notes:
- If you already have a local Postgres on `5432`, this repo’s `docker-compose.yml` maps the container’s Postgres to host port `5433`.
- For local smoke tests, this repo includes `backend/.env` with `DATABASE_URL` pointing at that `5433` mapping and disables external sources.

## Add subscribers (MVP admin endpoints)

If `ADMIN_API_KEY` is set:

- include header `X-Admin-Token: <ADMIN_API_KEY>`

### `POST /admin/subscribers`
Body:

```json
{
  "phone_number": "+14155550123",
  "route_preferences": {},
  "is_active": true
}
```

### `GET /admin/subscribers`

## Few-shot classification examples

Edit:

- `backend/app/prompts/severity_examples.jsonl`

Each line must be JSON with:

```json
{"input":"...","output":{"severity":"NO_ALERT|INFO|WARNING|CRITICAL","title":"...","message":"...","evidence_sources":["511","reddit"]}}
```

Claude will be prompted to return strict JSON matching the schema.

## Deploy to Railway

The repo includes:

- `Dockerfile`
- `Procfile` with process types: `web`, `worker`, `beat`

1. Create a Railway project from this repo and connect a Postgres DB and a Redis instance.
2. Set `DATABASE_URL` and Redis vars from `.env.example` in Railway.
3. Ensure your Railway services expose process types `web`, `worker`, and `beat`.

## Railway Redis tips

If Railway gives you a full Redis URL, set `REDIS_URL` directly.
If it gives you host/port/password pieces, set:

- `REDIS_HOST`
- `REDIS_PORT`
- `REDIS_PASSWORD`
- `REDIS_TLS=true` if the connection is `rediss://...`

