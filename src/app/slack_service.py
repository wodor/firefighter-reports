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
        all_matches: List[Dict[str, Any]] = []
        page = 1
        max_pages = 20  # Safety limit to avoid infinite loops
        per_page = 100  # Slack API max is 100 per page
        
        try:
            while page <= max_pages and len(all_matches) < limit:
                result = self.user_client.search_messages(
                    query=query,
                    count=per_page,
                    page=page,
                    sort="timestamp",  # Sort by timestamp to get most recent first
                )
                messages_data = result.get("messages", {})
                matches = messages_data.get("matches", [])
                filtered_matches = [match for match in matches if self._is_human_message(match)]
                all_matches.extend(filtered_matches)
                
                # Check if there are more pages
                paging = messages_data.get("paging", {})
                total_pages = paging.get("pages", 1)
                if page >= total_pages:
                    break
                page += 1
        except SlackApiError as exc:
            raise RuntimeError(f"Slack search failed: {exc}") from exc
        
        # Return up to the requested limit
        return all_matches[:limit]

    def _is_human_message(self, match: Dict[str, Any]) -> bool:
        subtype = match.get("subtype")
        if subtype in {"bot_message", "slackbot_response", "app_message"}:
            return False
        if match.get("bot_id") or match.get("app_id"):
            return False
        if match.get("username") and not match.get("user"):
            return False
        user = match.get("user")
        if isinstance(user, str) and user.upper() == "USLACKBOT":
            return False
        if isinstance(user, str) and self._is_bot_user(user):
            return False
        profile = match.get("user_profile")
        if isinstance(profile, dict):
            if profile.get("is_bot"):
                return False
            name = (
                profile.get("display_name_normalized")
                or profile.get("real_name_normalized")
                or profile.get("name")
            )
            if isinstance(name, str) and name.lower() == "slackbot":
                return False
        return True

    def _is_bot_user(self, user_id: str) -> bool:
        cache_key = f"user_is_bot:{user_id}"
        cached = self.cache.get_json(cache_key)
        if isinstance(cached, dict) and "is_bot" in cached and isinstance(cached["is_bot"], bool):
            return cached["is_bot"]
        try:
            result = self.user_client.users_info(user=user_id)
        except SlackApiError:
            return False
        user_obj: Optional[Dict[str, Any]] = result.get("user")
        if not user_obj:
            return False
        is_bot = bool(user_obj.get("is_bot"))
        self.cache.set_json(cache_key, {"is_bot": is_bot}, self.user_cache_ttl)
        return is_bot

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

    def get_permalink(self, channel_id: str, message_ts: str) -> Optional[str]:
        try:
            result = self.user_client.chat_getPermalink(
                channel=channel_id,
                message_ts=message_ts,
            )
        except SlackApiError:
            return None
        permalink = result.get("permalink")
        return permalink if isinstance(permalink, str) else None

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
            # If bot is not in channel, try to join it first
            if exc.response and exc.response.get("error") == "not_in_channel":
                try:
                    self.bot_client.conversations_join(channel=channel_id)
                    # Retry posting after joining
                    self.bot_client.chat_postMessage(
                        channel=channel_id,
                        blocks=blocks,
                        text="Firefighter daily summary",
                    )
                except SlackApiError as join_exc:
                    raise RuntimeError(
                        f"Slack post failed: Could not join channel {channel_id}. "
                        f"Please invite the bot to the channel. Error: {join_exc}"
                    ) from join_exc
            else:
                raise RuntimeError(f"Slack post failed: {exc}") from exc

    def post_blocks_in_thread(
        self, channel_id: str, thread_ts: str, blocks: List[Dict[str, Any]]
    ) -> None:
        """Post blocks as a reply in an existing thread.
        
        Args:
            channel_id: The channel ID to post in
            thread_ts: The thread timestamp to reply to
            blocks: The blocks to post
        """
        if not blocks:
            return
        try:
            self.bot_client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                blocks=blocks,
                text="Firefighter thread summary",
            )
        except SlackApiError as exc:
            # If bot is not in channel, try to join it first
            if exc.response and exc.response.get("error") == "not_in_channel":
                try:
                    self.bot_client.conversations_join(channel=channel_id)
                    # Retry posting after joining
                    self.bot_client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=thread_ts,
                        blocks=blocks,
                        text="Firefighter thread summary",
                    )
                except SlackApiError as join_exc:
                    raise RuntimeError(
                        f"Slack post failed: Could not join channel {channel_id}. "
                        f"Please invite the bot to the channel. Error: {join_exc}"
                    ) from join_exc
            else:
                raise RuntimeError(f"Slack post in thread failed: {exc}") from exc

    def get_or_create_weekly_thread(
        self, channel_id: str, week_commencing_date: datetime
    ) -> str:
        """Get or create a weekly thread for the given week commencing date.
        
        Args:
            channel_id: The channel ID to post in
            week_commencing_date: The Monday date of the week
            
        Returns:
            The thread timestamp (ts) of the weekly thread
        """
        date_str = week_commencing_date.strftime("%Y-%m-%d")
        search_query = f'Firefighter weekly summary {date_str}'
        
        # Search for existing weekly thread
        try:
            result = self.user_client.search_messages(
                query=search_query,
                count=10,
                sort="timestamp",
            )
            messages_data = result.get("messages", {})
            matches = messages_data.get("matches", [])
            
            # Look for a message with the exact pattern in the correct channel
            for match in matches:
                text = match.get("text", "")
                if f"Firefighter weekly summary {date_str}" in text:
                    # Verify it's in the correct channel
                    channel_info = match.get("channel", {})
                    match_channel_id = channel_info.get("id") if isinstance(channel_info, dict) else match.get("channel")
                    if match_channel_id == channel_id:
                        ts = match.get("ts")
                        if isinstance(ts, str):
                            return ts
        except SlackApiError:
            # If search fails, we'll create a new thread
            pass
        
        # Create new weekly thread
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Firefighter weekly summary {date_str}",
                },
            }
        ]
        
        try:
            response = self.bot_client.chat_postMessage(
                channel=channel_id,
                blocks=blocks,
                text=f"Firefighter weekly summary {date_str}",
            )
        except SlackApiError as exc:
            # If bot is not in channel, try to join it first
            if exc.response and exc.response.get("error") == "not_in_channel":
                try:
                    self.bot_client.conversations_join(channel=channel_id)
                    # Retry posting after joining
                    response = self.bot_client.chat_postMessage(
                        channel=channel_id,
                        blocks=blocks,
                        text=f"Firefighter weekly summary {date_str}",
                    )
                except SlackApiError as join_exc:
                    raise RuntimeError(
                        f"Slack post failed: Could not join channel {channel_id}. "
                        f"Please invite the bot to the channel. Error: {join_exc}"
                    ) from join_exc
            else:
                raise RuntimeError(f"Slack post failed: {exc}") from exc
        
        message_ts = response.get("ts")
        if not isinstance(message_ts, str):
            raise RuntimeError("Failed to get thread timestamp from Slack response")
        return message_ts

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

    @staticmethod
    def parse_permalink(permalink: str) -> tuple[str, str] | None:
        """Extract channel_id and message_ts from a Slack permalink.
        
        Permalink format: https://workspace.slack.com/archives/C12345678/p1234567890123456
        Returns (channel_id, message_ts) or None if parsing fails.
        """
        import re
        match = re.search(r'/archives/([A-Z0-9]+)/p(\d+)', permalink)
        if not match:
            return None
        channel_id = match.group(1)
        ts_raw = match.group(2)
        message_ts = f"{ts_raw[:10]}.{ts_raw[10:]}"
        return channel_id, message_ts

