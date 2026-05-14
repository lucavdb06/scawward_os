"""
VisionModule — captures the screen and asks Claude what's on it.

Two modes:
  * `describe()`     → on-demand summary of the current screen.
  * `watch()`        → background coroutine; emits `vision.screen.summary`
                       events whenever the screen changes meaningfully.

We downscale screenshots before sending (vision tokens are expensive).
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
from dataclasses import dataclass
from pathlib import Path

from anthropic import AsyncAnthropic

from ..config import Settings, get_settings
from ..core.event_bus import EventBus, get_bus

logger = logging.getLogger(__name__)


@dataclass
class Screenshot:
    png_bytes: bytes
    width: int
    height: int


class VisionModule:
    def __init__(self, bus: EventBus | None = None,
                 settings: Settings | None = None) -> None:
        self.cfg = settings or get_settings()
        self.bus = bus or get_bus()
        self.client = AsyncAnthropic(api_key=self.cfg.anthropic_api_key)
        self._last_hash: int | None = None

    # ─── Capture ──────────────────────────────────────────────────
    async def capture(self) -> Screenshot:
        return await asyncio.to_thread(self._capture_blocking)

    def _capture_blocking(self) -> Screenshot:
        from PIL import Image
        import mss

        with mss.mss() as sct:
            mon = sct.monitors[1]              # primary screen
            raw = sct.grab(mon)
            img = Image.frombytes("RGB", raw.size, raw.rgb)

        scale = self.cfg.screenshot_downscale
        if scale and scale < 1.0:
            new = (int(img.width * scale), int(img.height * scale))
            img = img.resize(new, Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return Screenshot(png_bytes=buf.getvalue(), width=img.width, height=img.height)

    # ─── Describe ─────────────────────────────────────────────────
    async def describe(self, question: str | None = None) -> str:
        shot = await self.capture()
        b64 = base64.b64encode(shot.png_bytes).decode()
        prompt = (
            question or
            "Describe what is currently on the user's screen in 2-3 sentences. "
            "Mention the active app, key UI regions, and anything actionable."
        )
        msg = await self.client.messages.create(
            model=self.cfg.vision_model,
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        await self.bus.emit("vision.screen.summary", {"summary": text}, source="vision")
        return text

    # ─── Background watcher ───────────────────────────────────────
    async def watch(self) -> None:
        """Fire-and-forget loop. Cancel the task to stop."""
        interval = max(1, self.cfg.screenshot_interval)
        while True:
            try:
                shot = await self.capture()
                h = hash(shot.png_bytes)
                if h != self._last_hash:
                    self._last_hash = h
                    summary = await self.describe()
                    logger.debug("screen changed: %s", summary[:80])
            except Exception:
                logger.exception("vision watch loop error")
            await asyncio.sleep(interval)

    # ─── Persistence (optional) ───────────────────────────────────
    def save_to(self, shot: Screenshot, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(shot.png_bytes)
        return p
