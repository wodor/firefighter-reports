# Firefighter Reports

LangChain-powered Slack application that automates the generation of technical incident reports. It scans recent "firefighter" threads (urgent tech support), summarizes them using OpenAI, and posts structured reports back to Slack.

## Overview

The application automates the tedious task of tracking and summarizing urgent technical requests. It identifies relevant conversations, aggregates thread context, resolves participants, and uses LLMs to extract clear "Problem" and "Solution" descriptions.

### Key Features
- **Intelligent Search**: Scans Slack for specific mentions (e.g., `@platform-firefighter`) within a lookback window.
- **Thread Contextualization**: Fetches entire conversation histories to ensure summaries are accurate and complete.
- **AI-Driven Summaries**: Uses LangChain + OpenAI to generate structured Slack Block Kit reports.
- **Smart Link Extraction**: Automatically identifies and formats JIRA, Zendesk, and Datadog links from conversation text.
- **Efficient Caching**: Redis-backed cache for Slack user profiles and thread summaries to minimize API costs and latency.
- **Weekly Aggregation**: Groups summaries into a single weekly thread to maintain channel cleanliness.

## Architecture

1.  **Slack Service**: Interfaces with Slack API for searching messages, fetching thread replies, and resolving user identities.
2.  **Summarizer**: Orchestrates the LLM chain. It transforms raw thread text into a structured JSON schema compatible with Slack's Block Kit.
3.  **Cache Layer**: Redis storage for persistent user mapping and summary deduplication.
4.  **Runner**: The main pipeline logic that ties search, resolution, summarization, and reporting together.

## Setup

### Prerequisites
- Python 3.12+
- Redis server (local or cloud)

### Installation
```bash
pip install .
```

### Environment Configuration
Create a `.env` file or export the following:
- `OPENAI_API_KEY`: OpenAI API key.
- `SLACK_BOT_TOKEN`: Bot token with `chat:write` and `users:read` scopes.
- `SLACK_USER_TOKEN`: User token with `search:read` and `channels:history` scopes (required for global search).
- `SLACK_CHANNEL_ID`: Destination channel for reports.
- `REDIS_URL`: Defaults to `redis://localhost:6379/0`.

## Usage

Run the pipeline via the CLI:

```bash
# Generate and post reports
python -m app.main run

# Dry run (prints blocks to console without posting)
python -m app.main run --dry-run

# Summarize a specific thread by permalink
python -m app.main run --permalink https://workspace.slack.com/archives/C123/p123456789
```

## Example Output

Firefighter summaries are posted as rich blocks:

> **Slow queue backlog impacting report card generation**
> *2025-12-18 00:00*
> **Problem:** Slow queue had a buildup of jobs, causing report cards to take a long time to generate.
> **Solution:** Temporarily increased worker count from 4 to 6 to help clear the backlog.
> **Participants:** John Doe, Jane Doe

## Next Steps

- **External Integration**: Direct integration with JIRA/Zendesk/Confluence MCPs to pull ticket status and update cross-references automatically.
- **Trend Analysis**: Export data to a warehouse or dashboard (e.g., Datadog, Google Sheets) for long-term tracking of firefighter load.
- **Interaction**: Add Slack actions (buttons) to the reports for direct follow-up or incident acknowledgement.
