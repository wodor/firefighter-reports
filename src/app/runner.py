import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Set

from .cache import Cache
from .config import Settings
from .slack_service import SlackService
from .summarizer import Summarizer

logger = logging.getLogger(__name__)


def get_week_commencing_date(dt: datetime) -> datetime:
    """Calculate the Monday of the week for a given datetime.
    
    Args:
        dt: The datetime to calculate the week commencing date for
        
    Returns:
        The Monday of the week (weekday 0) at midnight UTC
    """
    days_since_monday = dt.weekday()
    monday = dt - timedelta(days=days_since_monday)
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def build_thread_text(
    messages: List[Dict[str, Any]],
    resolve_user_name: Callable[[str], str],
) -> tuple[str, List[str]]:
    lines: List[str] = []
    participants: Set[str] = set()
    for message in messages:
        user_id = message.get("user")
        if isinstance(user_id, str):
            name = resolve_user_name(user_id)
            participants.add(name)
        else:
            name = "Unknown"
        text = message.get("text", "")
        lines.append(f"{name}: {text}")
    return "\nReply:\n".join(lines), sorted(participants)


def run_pipeline(settings: Settings, dry_run: bool | None = None, permalink: str | None = None) -> None:
    cache = Cache(settings.redis_url)
    slack = SlackService(
        bot_token=settings.slack_bot_token,
        user_token=settings.slack_user_token,
        cache=cache,
        user_cache_ttl=settings.user_cache_ttl,
    )
    summarizer = Summarizer(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
    )
    effective_dry_run = settings.dry_run if dry_run is None else dry_run

    threads: List[Dict[str, Any]] = []
    logger.info("Looking for threads in the last %d days", settings.lookback_days)

    if permalink:
        parsed = SlackService.parse_permalink(permalink)
        if not parsed:
            raise ValueError(f"Invalid permalink format: {permalink}")
        channel_id, message_ts = parsed
        thread_messages = slack.fetch_thread(channel_id, message_ts)
        if not thread_messages:
            raise ValueError(f"No messages found for permalink: {permalink}")
        dt = SlackService.ts_to_datetime(message_ts)
        logger.info("Single thread mode: %s, count: %d", permalink, len(thread_messages))
        threads.append({
            "channel_id": channel_id,
            "thread_ts": message_ts,
            "messages": thread_messages,
            "dt": dt,
        })
    else:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=settings.lookback_days)
        matches = slack.search_messages(settings.search_query, settings.search_limit)
        logger.info("Found %d matches", len(matches))
        
        for item in matches:
            ts = item.get("thread_ts") or item.get("ts")
            if not ts:
                continue
            dt = SlackService.ts_to_datetime(str(ts))
            if dt < cutoff:
                continue
            channel_info = item.get("channel", {})
            channel_id = channel_info.get("id") or item.get("channel") or item.get("channel_id")
            if not isinstance(channel_id, str):
                continue
            thread_messages = slack.fetch_thread(channel_id, str(ts))
            if not thread_messages or len(thread_messages) < 2:
                continue
            logger.info("Thread messages for %s, count: %d", slack.get_permalink(channel_id, ts), len(thread_messages))
            threads.append(
                {
                    "channel_id": channel_id,
                    "thread_ts": str(ts),
                    "messages": thread_messages,
                    "dt": dt,
                }
            )

    if settings.max_threads and len(threads) > settings.max_threads:
        threads = threads[: settings.max_threads]

    # Calculate week commencing date (Monday of current week)
    current_date = datetime.now(tz=timezone.utc)
    week_commencing = get_week_commencing_date(current_date)
    
    # Get or create the weekly thread
    weekly_thread_ts = slack.get_or_create_weekly_thread(
        settings.slack_channel_id, week_commencing
    )
    
    # Process threads and post summaries individually
    summaries_posted = 0
    for thread in threads:
        cache_key = f"thread-summary:{thread['thread_ts']}"
        cached = cache.get_json(cache_key)
        thread_text, participants = build_thread_text(thread["messages"], slack.resolve_user_name)
        timestamp_str = thread["dt"].strftime("%Y-%m-%d")
        if cached:
            summary_blocks = cached
        else:
            summary_blocks = summarizer.summarize(
                timestamp=timestamp_str,
                thread_text=thread_text,
                participants=participants,
            )
            cache.set_json(cache_key, summary_blocks, settings.thread_cache_ttl)
        
        # Post this summary as a separate message in the weekly thread
        message_blocks = summary_blocks.copy()
        permalink = slack.get_permalink(thread["channel_id"], thread["thread_ts"])
        if permalink:
            message_blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"<{permalink}|View thread>"}]
            })
        slack.post_blocks_in_thread(
            settings.slack_channel_id, weekly_thread_ts, message_blocks
        )
        summaries_posted += 1

    # If no summaries were posted, post a message indicating no threads found
    if summaries_posted == 0:
        no_threads_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "No firefighter threads found in the selected window.",
                },
            }
        ]
        slack.post_blocks_in_thread(
            settings.slack_channel_id, weekly_thread_ts, no_threads_blocks
        )

    cache.close()

