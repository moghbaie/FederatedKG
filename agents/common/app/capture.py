"""Test-only payload capture so the leak scan can inspect every byte an agent sends or receives."""
from __future__ import annotations

import threading
from pathlib import Path

_lock = threading.Lock()


class Capture:
    def __init__(self, path: Path | None):
        self.path = path
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, direction: str, where: str, body: bytes) -> None:
        if not self.path or not body:
            return
        with _lock, open(self.path, "ab") as f:
            f.write(f"\n--- {direction} {where}\n".encode() + body)


class CaptureMiddleware:
    """Pure ASGI middleware: records inbound request bodies and outbound response bodies."""

    def __init__(self, app, capture: Capture):
        self.app = app
        self.capture = capture

    async def __call__(self, scope, receive, send):
        # The owner's own graph view goes only to its owner's browser; it is not inter-party traffic.
        if scope["type"] != "http" or not self.capture.path or scope.get("path", "").startswith("/owner/"):
            return await self.app(scope, receive, send)
        path = scope.get("path", "")

        async def recv():
            msg = await receive()
            if msg["type"] == "http.request":
                self.capture.write("inbound-request", path, msg.get("body", b""))
            return msg

        async def snd(msg):
            if msg["type"] == "http.response.body":
                self.capture.write("outbound-response", path, msg.get("body", b""))
            await send(msg)

        await self.app(scope, recv, snd)
