# firefighter-reports

LangChain + Slack application that scans recent firefighter threads, summarizes them with OpenAI, caches user and summary data in Redis, and posts Slack Block Kit reports. Runs locally or in GitHub Actions with a Redis service.

## Setup

1) Python 3.12.  
2) Install:
```
pip install .
```
3) Configure environment (can use `.env`):
- `OPENAI_API_KEY` – OpenAI key.  
- `SLACK_BOT_TOKEN` – for posting.  
- `SLACK_USER_TOKEN` – for search/thread fetch.  
- `SLACK_CHANNEL_ID` – target channel for summaries.  
- Optional tuning: `REDIS_URL` (default `redis://localhost:6379/0`), `SEARCH_QUERY` (default `@platform-firefighter`), `LOOKBACK_DAYS` (default `7`), `SEARCH_LIMIT` (default `50`), `OPENAI_MODEL` (default `gpt-4o-mini`), `USER_CACHE_TTL`, `THREAD_CACHE_TTL`, `MAX_THREADS`, `DRY_RUN`.

## Run
```
python -m app.main run              # posts to Slack
python -m app.main run --dry-run    # prints blocks only
```

## Flow (mapped to provided pseudocode)
- Search messages (`SearchMessages`) with `SEARCH_QUERY`; filter to `LOOKBACK_DAYS` window (`DateLimit`).
- Fetch thread replies (`GetReplies`/`GetThread`), aggregate text and participants (`SummarizeThread`).
- Resolve Slack users via Redis-backed cache (`UsersLib` analogue).
- Summarize with OpenAI via LangChain into Slack blocks (`AI_Agent` + `StructuredOutputParser` role).
- Cache thread summaries in Redis, then post blocks to `SLACK_CHANNEL_ID` (`SendMessage`).

## GitHub Actions
Workflow `.github/workflows/firefighter.yml` runs daily at 07:00 UTC or on dispatch, starts a `redis:7` service, installs the project, and executes `python -m app.main run`. Provide secrets: `OPENAI_API_KEY`, `SLACK_BOT_TOKEN`, `SLACK_USER_TOKEN`, `SLACK_CHANNEL_ID`.
