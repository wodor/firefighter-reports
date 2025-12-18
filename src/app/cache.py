import json
from typing import Any, Optional

import redis


class Cache:
    def __init__(self, redis_url: str) -> None:
        self.client = redis.Redis.from_url(redis_url, decode_responses=True)

    def get_json(self, key: str) -> Optional[Any]:
        value = self.client.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        self.client.set(name=key, value=json.dumps(value), ex=ttl_seconds)

    def close(self) -> None:
        self.client.close()

