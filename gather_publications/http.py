from __future__ import annotations

import time
from typing import Any

import httpx

from .cache import JsonCache


class CachedHttpClient:
    def __init__(self, cache: JsonCache, user_agent: str, timeout: float = 30.0):
        self.cache = cache
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
        )

    def get_json(
        self,
        namespace: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        use_cache: bool = True,
        retries: int = 3,
    ) -> Any:
        key = str(httpx.URL(url, params=params))
        if use_cache and (cached := self.cache.get(namespace, key)) is not None:
            return cached
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                response = self.client.get(url, params=params, headers=headers)
                if response.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
                response.raise_for_status()
                payload = response.json()
                self.cache.put(namespace, key, payload)
                return payload
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                time.sleep(2 ** attempt)
        raise RuntimeError(f"Request failed after {retries} attempts: {key}") from last_error

    def close(self) -> None:
        self.client.close()
