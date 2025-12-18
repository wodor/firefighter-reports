import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Set

from .cache import Cache
from .config import Settings
from .slack_service import SlackService
from .summarizer import Summarizer

logger = logging.getLogger(__name__)


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

        if False and effective_dry_run:
            permalinks: List[str] = []
            for match in matches:
                plink = match.get("permalink")
                if isinstance(plink, str) and plink:
                    permalinks.append(plink)
                    continue
                channel_info = match.get("channel", {})
                ch_id = channel_info.get("id") or match.get("channel") or match.get("channel_id")
                ts = match.get("thread_ts") or match.get("ts")
                if isinstance(ch_id, str) and isinstance(ts, str):
                    resolved_permalink = slack.get_permalink(ch_id, ts)
                    if resolved_permalink:
                        permalinks.append(resolved_permalink)
            print(json.dumps(permalinks, indent=2))
            cache.close()
            return

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

    def is_placeholder_thread(blocks: List[Dict[str, Any]]) -> bool:
        """Check if blocks represent a placeholder/title-only thread."""
        placeholder_patterns = [
            "placeholder/title only",
            "placeholder/title",
            "no thread messages provided beyond the title",
            "no thread messages provided",
        ]
        # Collect all text content from blocks
        all_text = ""
        for block in blocks:
            if block.get("type") == "section" and "text" in block:
                text_obj = block["text"]
                if isinstance(text_obj, dict):
                    all_text += text_obj.get("text", "").lower()
            elif block.get("type") == "header" and "text" in block:
                text_obj = block["text"]
                if isinstance(text_obj, dict):
                    all_text += text_obj.get("text", "").lower()
            elif block.get("type") == "context" and "elements" in block:
                for element in block["elements"]:
                    if element.get("type") in ("mrkdwn", "plain_text"):
                        all_text += element.get("text", "").lower()
        
        # Check if any placeholder pattern is found in the combined text
        for pattern in placeholder_patterns:
            if pattern in all_text:
                return True
        return False

    blocks: List[Dict[str, Any]] = []
    for thread in threads:
        cache_key = f"thread-summary:{thread['thread_ts']}"
        cached = cache.get_json(cache_key)
        thread_text, participants = build_thread_text(thread["messages"], slack.resolve_user_name)
        logger.info("Thread text for %s:\n%s", thread["thread_ts"], thread_text)
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
        
        # Skip placeholder/title-only threads
        if not is_placeholder_thread(summary_blocks):
            blocks.extend(summary_blocks)
            permalink = slack.get_permalink(thread["channel_id"], thread["thread_ts"])
            if permalink:
                blocks.append({
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": f"<{permalink}|View thread>"}]
                })
            blocks.append({"type": "divider"})

    if not blocks:
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "No firefighter threads found in the selected window.",
                },
            }
        ]

    slack.post_blocks(settings.slack_channel_id, blocks)

    cache.close()

