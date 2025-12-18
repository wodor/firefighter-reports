from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from .cache import Cache


class SlackService:
    def __init__(
        self,
        bot_token: str,
        user_token: str,
        cache: Cache,
        user_cache_ttl: int,
    ) -> None:
        self.bot_client = WebClient(token=bot_token)
        self.user_client = WebClient(token=user_token)
        self.cache = cache
        self.user_cache_ttl = user_cache_ttl

    def search_messages(self, query: str, limit: int) -> List[Dict[str, Any]]:
        try:
            result = self.user_client.search_messages(query=query, count=limit)
        except SlackApiError as exc:
            raise RuntimeError(f"Slack search failed: {exc}") from exc
        return result.get("messages", {}).get("matches", [])

    def fetch_thread(self, channel_id: str, thread_ts: str) -> List[Dict[str, Any]]:
        try:
            result = self.user_client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                inclusive=True,
                limit=200,
            )
        except SlackApiError as exc:
            raise RuntimeError(f"Slack thread fetch failed: {exc}") from exc
        return result.get("messages", [])

    def post_blocks(self, channel_id: str, blocks: List[Dict[str, Any]]) -> None:
        if not blocks:
            return
        try:
            self.bot_client.chat_postMessage(
                channel=channel_id,
                blocks=blocks,
                text="Firefighter daily summary",
            )
        except SlackApiError as exc:
            raise RuntimeError(f"Slack post failed: {exc}") from exc

    def resolve_user_name(self, user_id: str) -> str:
        cache_key = f"user:{user_id}"
        cached = self.cache.get_json(cache_key)
        if isinstance(cached, dict) and "name" in cached:
            return str(cached["name"])
        try:
            result = self.user_client.users_info(user=user_id)
        except SlackApiError:
            return user_id
        user_obj: Optional[Dict[str, Any]] = result.get("user")
        if not user_obj:
            return user_id
        real_name = user_obj.get("real_name") or user_obj.get("name") or user_id
        self.cache.set_json(cache_key, {"name": real_name}, self.user_cache_ttl)
        return real_name

    @staticmethod
    def ts_to_datetime(ts: str) -> datetime:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)

