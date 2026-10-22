"""
Redis client interface with in-memory fallback for ephemeral task state and caching.
"""
import asyncio
import json
import logging
import subprocess
import time
from typing import Any, Optional
import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger("web_agent.redis")


class InMemoryFallbackStore:
    """
    In-memory Key-Value store fallback when Redis is not running locally.
    """
    def __init__(self):
        self._store = {}
        self._expires = {}

    async def get(self, key: str) -> Optional[str]:
        expires_at = self._expires.get(key)
        if expires_at is not None and expires_at <= time.time():
            self._store.pop(key, None)
            self._expires.pop(key, None)
            return None
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        self._store[key] = value
        if ex is not None:
            self._expires[key] = time.time() + ex
        return True

    async def delete(self, key: str) -> bool:
        self._store.pop(key, None)
        self._expires.pop(key, None)
        return True

    async def exists(self, key: str) -> bool:
        return key in self._store

    async def close(self):
        pass


class RedisClientWrapper:
    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._fallback: Optional[InMemoryFallbackStore] = None
        self._is_fallback: bool = False

    async def initialize(self):
        try:
            client = self._create_client()
            await client.ping()
            self._redis = client
            self._is_fallback = False
            logger.info("Connected to Redis successfully.")
        except Exception as e:
            if settings.REDIS_AUTO_START:
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["sc.exe", "start", settings.REDIS_SERVICE_NAME],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0 or "already been started" in (result.stdout + result.stderr).lower():
                    client = self._create_client()
                    await client.ping()
                    self._redis = client
                    self._is_fallback = False
                    logger.info("Redis service started automatically and connected successfully.")
                    return
            if settings.USE_REDIS_MEMORY_FALLBACK:
                self._fallback = InMemoryFallbackStore()
                self._is_fallback = True
                logger.warning("Redis unavailable; using in-memory fallback store.")
                return
            raise RuntimeError("Redis is required to start the application.") from e

    @staticmethod
    def _create_client():
        timeout = settings.REDIS_CONNECT_TIMEOUT_SECONDS
        return redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=timeout,
            socket_timeout=timeout,
        )

    async def get_json(self, key: str) -> Optional[Any]:
        try:
            raw = await (self._fallback.get(key) if self._is_fallback else self._redis.get(key))
        except Exception as error:
            logger.warning("Redis get failed for %s: %s", key, error)
            return None
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                return None
        return None

    async def set_json(self, key: str, value: Any, ttl_seconds: int = 3600) -> bool:
        raw = json.dumps(value)
        try:
            if self._is_fallback:
                return await self._fallback.set(key, raw, ex=ttl_seconds)
            return await self._redis.set(key, raw, ex=ttl_seconds)
        except Exception as error:
            logger.warning("Redis set failed for %s: %s", key, error)
            return False

    async def delete(self, key: str) -> bool:
        try:
            if self._is_fallback:
                return await self._fallback.delete(key)
            return await self._redis.delete(key)
        except Exception as error:
            logger.warning("Redis delete failed for %s: %s", key, error)
            return False

    async def close(self):
        if self._redis:
            await self._redis.close()
        if self._fallback:
            await self._fallback.close()


redis_client = RedisClientWrapper()
