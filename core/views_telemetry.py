"""
Sri AI — Omni-Heal Pillar A: Frontend Telemetry API
=====================================================
Secure endpoint that accepts browser/bot error payloads
and forwards them into the Soft-Heal queue.

Mount in urls.py:
    path("api/sri-heal/frontend/", FrontendTelemetryView.as_view(), name="sri_frontend_telemetry"),
"""

import hashlib
import hmac
import json
import logging
import os
import time
from collections import defaultdict
from threading import Lock

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from core.sri_autonomous_healer import sri_heal_silent

logger = logging.getLogger("sri_ai.telemetry")

# ──────────────────────────────────────────────
# Simple in-process rate limiter
# (for production, swap with Redis + django-ratelimit)
# ──────────────────────────────────────────────
_rate_store: dict = defaultdict(list)
_rate_lock = Lock()

RATE_LIMIT_MAX      = 20    # max requests
RATE_LIMIT_WINDOW   = 60    # per N seconds


def _is_rate_limited(ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        hits = _rate_store[ip]
        # Purge old hits outside the window
        _rate_store[ip] = [t for t in hits if now - t < RATE_LIMIT_WINDOW]
        if len(_rate_store[ip]) >= RATE_LIMIT_MAX:
            return True
        _rate_store[ip].append(now)
        return False


# ──────────────────────────────────────────────
# HMAC signature verification
# Set SRI_TELEMETRY_SECRET in Render environment variables
# ──────────────────────────────────────────────
_TELEMETRY_SECRET = os.getenv("SRI_TELEMETRY_SECRET", "")


def _verify_signature(request) -> bool:
    """
    Optional HMAC-SHA256 signature check.
    The QA Bot signs its payload with the shared secret.
    Real-user browser errors are allowed unsigned (no secret = skip check).
    """
    if not _TELEMETRY_SECRET:
        return True   # secret not configured — open mode (set it in production!)

    provided_sig = request.headers.get("X-Sri-Signature", "")
    if not provided_sig:
        # Allow unsigned payloads from real browsers (not bot traffic)
        try:
            source = json.loads(request.body or "{}").get("source", "")
        except (json.JSONDecodeError, UnicodeDecodeError):
            source = ""
        if source == "synthetic_bot":
            logger.warning("[Telemetry] Bot payload missing signature — rejected.")
            return False
        return True   # real browser — unsigned OK

    body = request.body
    expected_sig = hmac.new(
        _TELEMETRY_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(provided_sig, expected_sig)


# ──────────────────────────────────────────────
# Payload schema (validated manually — no DRF dependency)
# ──────────────────────────────────────────────
REQUIRED_FIELDS = {"error_type", "message"}
VALID_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
VALID_SOURCES    = {"browser", "synthetic_bot", "unknown"}


def _parse_payload(body: bytes) -> tuple:
    """Returns (payload_dict, error_string). error_string is '' on success."""
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, "Invalid JSON body."

    if not isinstance(data, dict):
        return None, "Payload must be a JSON object."

    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        return None, f"Missing required fields: {missing}"

    if "severity" in data and data["severity"] not in VALID_SEVERITIES:
        data["severity"] = "MEDIUM"   # sanitise unknown values

    if "source" in data and data["source"] not in VALID_SOURCES:
        data["source"] = "unknown"

    return data, ""


# ──────────────────────────────────────────────
# The View
# ──────────────────────────────────────────────
@method_decorator(csrf_exempt, name="dispatch")   # JS fetch() has no Django CSRF token
class FrontendTelemetryView(View):
    """
    POST /api/sri-heal/frontend/

    Expected JSON payload:
    {
        "error_type"  : "JS_RUNTIME" | "FETCH_FAIL" | "UI_BUG" | "CONSOLE_ERROR",
        "message"     : "Cannot read properties of undefined …",
        "stack"       : "Error: …\n    at uploadFile (upload_controller.js:42)",
        "url"         : "https://anti-gravity.onrender.com/upload/",
        "severity"    : "HIGH",
        "source"      : "browser" | "synthetic_bot",
        "screenshot"  : "<base64 PNG — optional, from bot only>"
    }

    Response (always 200 — never expose internals):
    { "status": "received", "job_id": "..." }
    """

    http_method_names = ["post"]   # GET/PUT/DELETE → 405

    def post(self, request, *args, **kwargs):
        # 1. Rate limit by IP
        client_ip = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", "unknown")
        )

        if _is_rate_limited(client_ip):
            logger.warning("[Telemetry] Rate limit hit for IP: %s", client_ip)
            # Return 200 anyway — never signal to attacker that they're blocked
            return JsonResponse({"status": "received"}, status=200)

        # 2. Signature check
        if not _verify_signature(request):
            return JsonResponse({"status": "received"}, status=200)

        # 3. Parse payload
        payload, parse_error = _parse_payload(request.body)
        if parse_error:
            logger.warning("[Telemetry] Bad payload from %s: %s", client_ip, parse_error)
            return JsonResponse({"status": "received"}, status=200)

        # 4. Build a human-readable trace string from JS stack
        error_source = f"frontend:{payload.get('url', 'unknown_url')}"
        error_trace  = (
            f"[{payload['error_type']}] {payload['message']}\n"
            f"Stack:\n{payload.get('stack', 'No stack provided.')}\n"
            f"Source: {payload.get('source', 'unknown')}\n"
            f"URL: {payload.get('url', '')}"
        )

        # 5. Enqueue into Soft-Heal
        accepted = sri_heal_silent(
            error_source=error_source,
            error_trace=error_trace,
            severity=payload.get("severity", "MEDIUM"),
            error_type="FRONTEND",
            context={
                "source"        : payload.get("source", "unknown"),
                "url"           : payload.get("url", ""),
                "has_screenshot": bool(payload.get("screenshot")),
            },
        )

        logger.info(
            "[Telemetry] Payload from %s → queued=%s | type=%s | severity=%s",
            client_ip,
            accepted,
            payload["error_type"],
            payload.get("severity", "MEDIUM"),
        )

        return JsonResponse({"status": "received"}, status=200)
