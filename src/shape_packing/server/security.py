"""Lightweight in-process security controls for the Shape Packing Coordinator.

Provides bounded LRU token-bucket rate limiting, short TTL caching for read endpoints,
ASGI request body size limits, security headers, and Azure proxy client IP extraction.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, Optional, Tuple

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def get_client_ip(request: Request) -> str:
    """Extract client IP, preferring Azure App Service's X-Azure-ClientIP header."""
    azure_ip = request.headers.get("x-azure-clientip", "").strip()
    if azure_ip:
        return azure_ip
    xff = request.headers.get("x-forwarded-for", "").strip()
    if xff:
        # Take first client entry only when behind reverse proxy; cap length to avoid key bloat
        return xff.split(",")[0].strip()[:64]
    if request.client and request.client.host:
        return str(request.client.host)[:64]
    return "unknown"


class TokenBucketRateLimiter:
    """Thread-safe bounded-LRU token-bucket rate limiter."""

    def __init__(self, rate_per_sec: float, capacity: float, max_keys: int = 10_000) -> None:
        self.rate_per_sec = float(rate_per_sec)
        self.capacity = float(capacity)
        self.max_keys = int(max_keys)
        self._buckets: OrderedDict[str, Tuple[float, float]] = OrderedDict()
        self._lock = threading.Lock()

    def allow(self, key: str, cost: float = 1.0) -> Tuple[bool, int]:
        """Consume `cost` tokens for `key`. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            tokens, last_ts = self._buckets.get(key, (self.capacity, now))
            elapsed = max(0.0, now - last_ts)
            tokens = min(self.capacity, tokens + elapsed * self.rate_per_sec)
            if tokens >= cost:
                tokens -= cost
                self._buckets[key] = (tokens, now)
                self._buckets.move_to_end(key)
                while len(self._buckets) > self.max_keys:
                    self._buckets.popitem(last=False)
                return True, 0

            self._buckets[key] = (tokens, now)
            self._buckets.move_to_end(key)
            deficit = cost - tokens
            retry_after = max(1, int(deficit / self.rate_per_sec) + 1) if self.rate_per_sec > 0 else 60
            return False, retry_after


class TTLCache:
    """Thread-safe bounded-LRU TTL cache for expensive read-only endpoints."""

    def __init__(self, ttl_seconds: float = 10.0, max_items: int = 256) -> None:
        self.ttl_seconds = float(ttl_seconds)
        self.max_items = int(max_items)
        self._store: OrderedDict[str, Tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        now = time.monotonic()
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            expires_at, value = item
            if now >= expires_at:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return value

    def set(self, key: str, value: Any) -> None:
        now = time.monotonic()
        with self._lock:
            self._store[key] = (now + self.ttl_seconds, value)
            self._store.move_to_end(key)
            while len(self._store) > self.max_items:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class BodySizeLimitMiddleware:
    """ASGI middleware enforcing per-path maximum request body sizes."""

    def __init__(self, app: ASGIApp, path_limits: Dict[str, int], default_limit: int = 16_384) -> None:
        self.app = app
        self.path_limits = dict(path_limits)
        self.default_limit = int(default_limit)

    def _limit_for_path(self, path: str) -> int:
        return self.path_limits.get(path, self.default_limit)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        if method in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return

        limit = self._limit_for_path(scope.get("path", ""))
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        raw_cl = headers.get(b"content-length")
        if raw_cl is not None:
            try:
                if int(raw_cl) > limit:
                    resp = JSONResponse({"detail": "Request payload too large"}, status_code=413)
                    await resp(scope, receive, send)
                    return
            except ValueError:
                resp = JSONResponse({"detail": "Invalid Content-Length header"}, status_code=400)
                await resp(scope, receive, send)
                return

        received_bytes = 0
        too_large = False

        async def limited_receive() -> Message:
            nonlocal received_bytes, too_large
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                received_bytes += len(body)
                if received_bytes > limit:
                    too_large = True
                    raise _PayloadTooLargeError()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _PayloadTooLargeError:
            if too_large:
                resp = JSONResponse({"detail": "Request payload too large"}, status_code=413)
                await resp(scope, receive, send)


class _PayloadTooLargeError(Exception):
    """Internal sentinel raised when streamed request body exceeds limit."""


class SecurityHeadersMiddleware:
    """ASGI middleware attaching defensive response headers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"x-frame-options", b"DENY"))
                headers.append((b"referrer-policy", b"strict-origin-when-cross-origin"))
                if path in ("/api/v1/export/db", "/api/v1/workers/register"):
                    headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
