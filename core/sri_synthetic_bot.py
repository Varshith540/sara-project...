import asyncio
import base64
import hashlib
import hmac
import io
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, ConsoleMessage, Page, async_playwright

logger = logging.getLogger("sri_ai.synthetic_bot")

CI_MODE          = os.getenv("CI", "false").lower() == "true"
TARGET_URL       = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8000")
UPLOAD_PATH_URL  = f"{TARGET_URL}/upload/"
TELEMETRY_URL    = f"{TARGET_URL}/api/sri-heal/frontend/"
TELEMETRY_SECRET = os.getenv("SRI_TELEMETRY_SECRET", "")

SCREENSHOT_DIR   = Path("/tmp/sri_bot_screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

FAKE_RESUME_TEXT = """
John Test
test@sri-ai-bot.internal | +1-555-0100
EDUCATION: B.Tech Computer Science — Test University (2020)
EXPERIENCE: Software Engineer — Fake Corp (2020–2024)
SKILLS: Python, Django, React, PostgreSQL, Docker, Kubernetes
"""

BOT_TIMEOUT_MS   = 30_000
UPLOAD_WAIT_MS   = 20_000

def _sign_payload(body: bytes) -> str:
    if not TELEMETRY_SECRET: return ""
    return hmac.new(TELEMETRY_SECRET.encode(), body, hashlib.sha256).hexdigest()

async def _post_telemetry(error_type: str, message: str, stack: str = "", severity: str = "HIGH", screenshot_b64: str = ""):
    try:
        import aiohttp
        payload = {"error_type": error_type, "message": message[:500], "stack": stack[:2000], "url": UPLOAD_PATH_URL, "severity": severity, "source": "synthetic_bot", "timestamp": datetime.now(timezone.utc).isoformat(), "screenshot": screenshot_b64}
        body = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json", "X-Sri-Signature": _sign_payload(body)}
        async with aiohttp.ClientSession() as session:
            async with session.post(TELEMETRY_URL, data=body, headers=headers, timeout=10) as resp:
                logger.info("[Bot] Telemetry → %s | %s", resp.status, error_type)
    except Exception as exc:
        logger.warning("[Bot] Telemetry post failed: %s", exc)

def _save_screenshot(png_bytes: bytes, label: str) -> str:
    try:
        fname = SCREENSHOT_DIR / f"failure_{label}_{int(time.time())}.png"
        fname.write_bytes(png_bytes)
    except Exception: pass
    return base64.b64encode(png_bytes).decode("utf-8")

class SriSyntheticBot:
    def __init__(self):
        self.console_errors: list[str] = []
        self.network_errors: list[str] = []
        self._errors_found:  list[str] = []

    def _on_console(self, msg: ConsoleMessage):
        if msg.type in ("error", "warning"): self.console_errors.append(f"[{msg.type.upper()}] {msg.text}")

    def _on_request_failed(self, request):
        self.network_errors.append(f"NETWORK_FAIL: {request.method} {request.url} — {request.failure}")

    async def _capture_and_report(self, page: Page, error_type: str, message: str, severity: str):
        self._errors_found.append(message)
        logger.error("[Bot] %s: %s", error_type, message)
        png_b64 = ""
        try:
            png = await page.screenshot(full_page=True)
            png_b64 = _save_screenshot(png, error_type.lower())
        except Exception: pass
        await _post_telemetry(error_type, message, severity=severity, screenshot_b64=png_b64)

    async def run(self) -> bool:
        fake_resume = Path("/tmp/sri_fake_resume.txt")
        fake_resume.write_text(FAKE_RESUME_TEXT, encoding="utf-8")

        async with async_playwright() as pw:
            browser: Browser = await pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--single-process"])
            ctx: BrowserContext = await browser.new_context(viewport={"width": 1280, "height": 900}, user_agent="Mozilla/5.0 (Sri-AI-SyntheticBot/2.0-CI; AntiGravity-QA)")
            page: Page = await ctx.new_page()
            page.set_default_timeout(BOT_TIMEOUT_MS)
            page.on("console", self._on_console)
            page.on("requestfailed", self._on_request_failed)

            try:
                resp = await page.goto(UPLOAD_PATH_URL, wait_until="networkidle")
                if not resp or resp.status >= 400:
                    await self._capture_and_report(page, "UI_BUG", f"Upload page HTTP {resp.status if resp else 'None'}", "CRITICAL")
                    return False

                file_input = page.locator('input[type="file"]').first
                if not await file_input.count():
                    await self._capture_and_report(page, "UI_BUG", "File input element not found", "HIGH")
                    return False

                await file_input.set_input_files(str(fake_resume))
                submit_btn = page.locator('button[type="submit"], #uploadBtn, .upload-btn, [data-action="upload"]').first
                if await submit_btn.count(): await submit_btn.click()

                try:
                    await page.wait_for_selector("#analysisResult, .result-container, #scoreSection, [data-testid='analysis-result']", timeout=UPLOAD_WAIT_MS)
                except Exception:
                    await self._capture_and_report(page, "UI_BUG", f"Analysis result did not render within timeout", "CRITICAL")
                    return False

            except Exception as exc:
                await self._capture_and_report(page, "JS_RUNTIME", f"Playwright exception: {exc}", "CRITICAL")
                return False

            finally:
                for err in self.console_errors:
                    self._errors_found.append(err)
                    await _post_telemetry("CONSOLE_ERROR", err, severity="MEDIUM")
                for err in self.network_errors:
                    self._errors_found.append(err)
                    await _post_telemetry("FETCH_NETWORK_ERROR", err, severity="HIGH")
                await browser.close()

        fake_resume.unlink(missing_ok=True)
        return len(self._errors_found) == 0

async def _async_main() -> bool:
    logging.basicConfig(level=logging.INFO)
    bot = SriSyntheticBot()
    return await bot.run()

def run_synthetic_check():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    success = loop.run_until_complete(_async_main())
    loop.close()
    return success

if __name__ == "__main__":
    success = asyncio.run(_async_main())
    sys.exit(0 if success else 1)
