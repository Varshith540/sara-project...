"""
Sri AI — Omni-Heal Pillar C: Synthetic QA Bot
==============================================
Headless Playwright script that simulates a full user journey every 12 hours,
collects errors, and reports them to the Telemetry API (Pillar A).

Schedule via apscheduler (already wired in scheduler.py):
    scheduler.add_job(run_synthetic_check, "interval", hours=12, ...)

First-time setup (run once on Render build):
    playwright install chromium --with-deps
"""

import asyncio
import base64
import hashlib
import hmac
import io
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("sri_ai.synthetic_bot")

TARGET_URL       = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8000")
UPLOAD_PATH_URL  = f"{TARGET_URL}/upload/"
TELEMETRY_URL    = f"{TARGET_URL}/api/sri-heal/frontend/"
TELEMETRY_SECRET = os.getenv("SRI_TELEMETRY_SECRET", "")

FAKE_RESUME_TEXT = """
John Test
test@example.com | +1-555-0100

EDUCATION
B.Tech Computer Science — Test University (2020)

EXPERIENCE
Software Engineer — Fake Corp (2020–2024)
- Built scalable microservices with Python and Django
- Deployed to AWS ECS using Docker and Terraform

SKILLS
Python, Django, React, PostgreSQL, Docker, Kubernetes

PROJECTS
ResumeXpert — AI-powered resume analysis platform (Django + Gemini AI)
"""

SCREENSHOT_MAX_BYTES = 200_000
BOT_TIMEOUT_MS       = 30_000
UPLOAD_WAIT_MS       = 15_000


def _sign_payload(body: bytes) -> str:
    if not TELEMETRY_SECRET:
        return ""
    return hmac.new(TELEMETRY_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _compress_screenshot(png_bytes: bytes) -> str:
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(png_bytes))
        img.thumbnail((1280, 900))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=60)
        compressed = buf.getvalue()
    except ImportError:
        compressed = png_bytes
    if len(compressed) > SCREENSHOT_MAX_BYTES:
        compressed = compressed[:SCREENSHOT_MAX_BYTES]
    return base64.b64encode(compressed).decode("utf-8")


async def _post_telemetry(error_type, message, stack="", severity="HIGH", screenshot_b64=""):
    import aiohttp
    payload = {
        "error_type" : error_type,
        "message"    : message[:500],
        "stack"      : stack[:2000],
        "url"        : UPLOAD_PATH_URL,
        "severity"   : severity,
        "source"     : "synthetic_bot",
        "timestamp"  : datetime.now(timezone.utc).isoformat(),
        "screenshot" : screenshot_b64,
    }
    body = json.dumps(payload).encode()
    headers = {
        "Content-Type"   : "application/json",
        "X-Sri-Signature": _sign_payload(body),
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(TELEMETRY_URL, data=body, headers=headers, timeout=10) as resp:
                logger.info("[SyntheticBot] Telemetry POST → %s | type=%s", resp.status, error_type)
    except Exception as exc:
        logger.error("[SyntheticBot] Failed to POST telemetry: %s", exc)


class SriSyntheticBot:
    """Simulates a full user journey; reports errors to the Telemetry API."""

    def __init__(self):
        self.console_errors = []
        self.network_errors = []

    def _on_console(self, msg):
        if msg.type in ("error", "warning"):
            self.console_errors.append(f"[{msg.type.upper()}] {msg.text}")

    def _on_request_failed(self, request):
        self.network_errors.append(f"NETWORK_FAIL: {request.method} {request.url} — {request.failure}")

    async def run(self) -> dict:
        result = {"success": False, "errors_found": [], "timestamp": datetime.now(timezone.utc).isoformat()}
        fake_resume_path = Path("/tmp/sri_fake_resume.txt")
        fake_resume_path.write_text(FAKE_RESUME_TEXT, encoding="utf-8")

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("[SyntheticBot] playwright not installed — skipping. Run: playwright install chromium --with-deps")
            fake_resume_path.unlink(missing_ok=True)
            return result

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Sri-AI-SyntheticBot/1.0; AntiGravity-QA; +https://anti-gravity.onrender.com)",
            )
            page = await context.new_page()
            page.set_default_timeout(BOT_TIMEOUT_MS)
            page.on("console",       self._on_console)
            page.on("requestfailed", self._on_request_failed)

            try:
                logger.info("[SyntheticBot] Navigating to %s", UPLOAD_PATH_URL)
                response = await page.goto(UPLOAD_PATH_URL, wait_until="networkidle")
                if not response or response.status >= 400:
                    await self._report_and_capture(page, "UI_BUG", f"Upload page returned HTTP {response.status if response else 'None'}", "CRITICAL", result)
                    return result

                file_input = page.locator('input[type="file"]').first
                if not await file_input.count():
                    await self._report_and_capture(page, "UI_BUG", "File input not found on upload page — possible layout regression", "HIGH", result)
                    return result

                await file_input.set_input_files(str(fake_resume_path))
                logger.info("[SyntheticBot] Fake resume uploaded.")

                submit_btn = page.locator('button[type="submit"], #uploadBtn, .upload-btn').first
                if await submit_btn.count():
                    await submit_btn.click()

                try:
                    await page.wait_for_selector("#analysisResult, .result-container, #scoreSection", timeout=UPLOAD_WAIT_MS)
                    logger.info("[SyntheticBot] Analysis result rendered ✓")
                    result["success"] = True
                except Exception:
                    await self._report_and_capture(page, "UI_BUG", "Analysis result did not appear within timeout — possible backend failure", "CRITICAL", result)

            except Exception as exc:
                await self._report_and_capture(page, "JS_RUNTIME", f"Playwright unhandled exception: {exc}", "CRITICAL", result)

            finally:
                for err in self.console_errors:
                    result["errors_found"].append(err)
                    await _post_telemetry("CONSOLE_ERROR", err, severity="MEDIUM")
                for err in self.network_errors:
                    result["errors_found"].append(err)
                    await _post_telemetry("FETCH_NETWORK_ERROR", err, severity="HIGH")
                await browser.close()

        fake_resume_path.unlink(missing_ok=True)
        logger.info("[SyntheticBot] Run complete. success=%s", result["success"])
        return result

    async def _report_and_capture(self, page, error_type, message, severity, result):
        result["errors_found"].append(message)
        logger.error("[SyntheticBot] %s: %s", error_type, message)
        screenshot_b64 = ""
        try:
            png = await page.screenshot(full_page=True)
            screenshot_b64 = _compress_screenshot(png)
        except Exception as exc:
            logger.warning("[SyntheticBot] Screenshot failed: %s", exc)
        await _post_telemetry(error_type, message, severity=severity, screenshot_b64=screenshot_b64)


def run_synthetic_check():
    """Synchronous wrapper called by apscheduler."""
    logger.info("[SyntheticBot] ── Scheduled check starting ──")
    start = time.monotonic()
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        bot = SriSyntheticBot()
        result = loop.run_until_complete(bot.run())
        loop.close()
    except Exception as exc:
        logger.exception("[SyntheticBot] Fatal error during run: %s", exc)
        return
    elapsed = time.monotonic() - start
    logger.info("[SyntheticBot] ── Check finished in %.1fs | success=%s | errors=%d ──", elapsed, result.get("success"), len(result.get("errors_found", [])))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_synthetic_check()
