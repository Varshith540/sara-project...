"""
Sri AI — Omni-Heal Pillar D: Poly-Brain LLM Router
====================================================
Provides a single `generate_patch` function used by the Soft-Heal Engine
to generate code fixes via a three-tier LLM fallback hierarchy:

  Tier 1 (Primary)  : Gemini 1.5 Flash via google-genai SDK
  Tier 2 (Fallback) : OpenRouter (Gemma-2-27B / Llama-3-70B)
  Tier 3 (Local)    : Ollama (llama3 running on localhost)

Design principles
-----------------
- Each tier is independently try/except-guarded — a failure never leaks
  past its own block.
- The router strips ALL markdown fencing from LLM output before returning
  so callers always receive raw, executable code.
- Zero circular imports: this module has no dependency on core.views,
  core.gemini_service, or Django settings at module-load time.
"""

import json
import logging
import os
import re
import textwrap

import requests

logger = logging.getLogger("sri_ai.llm_router")

# ---------------------------------------------------------------------------
# Configuration (env-driven, no Django settings dependency at module level)
# ---------------------------------------------------------------------------
_GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY", "")
_GEMINI_MODEL        = "gemini-1.5-flash"          # SDK v1.0+ — NO models/ prefix

_OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY", "")
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_OPENROUTER_MODELS   = [
    "google/gemma-2-27b-it",
    "meta-llama/llama-3-70b-instruct",
]

_OLLAMA_BASE_URL     = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_OLLAMA_MODEL        = os.getenv("OLLAMA_MODEL", "llama3")

_REQUEST_TIMEOUT     = 60   # seconds — applies to OpenRouter & Ollama


# ---------------------------------------------------------------------------
# Helper: strip markdown fencing from LLM output
# ---------------------------------------------------------------------------
def _strip_markdown(raw: str) -> str:
    """
    Remove code fences like:
        ```python ... ```
        ``` ... ```
    and return only the inner content, dedented.
    """
    # Remove opening fence (with optional language tag)
    raw = re.sub(r"^```[a-zA-Z]*\s*\n?", "", raw.strip(), flags=re.MULTILINE)
    # Remove closing fence
    raw = re.sub(r"\n?```\s*$", "", raw.strip(), flags=re.MULTILINE)
    return raw.strip()


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------
def _build_prompt(error_type: str, error_trace: str,
                  broken_file: str, context: str) -> str:
    return textwrap.dedent(f"""\
        You are Sri AI, an expert autonomous SRE engineer.
        A production Python/JS file has a bug. Your job is to return ONLY the
        fully corrected file content — no explanations, no markdown, no code
        fences. Raw code only.

        === Error Type ===
        {error_type}

        === Stack Trace ===
        {error_trace[:3000]}

        === Additional Context ===
        {context[:1000]}

        === Broken File Content ===
        {broken_file[:6000]}

        Return the complete, corrected file content now.
    """).strip()


# ---------------------------------------------------------------------------
# Tier 1 — Gemini (google-genai SDK v1.0+, no models/ prefix)
# ---------------------------------------------------------------------------
def _tier1_gemini(prompt: str) -> str:
    """Try Gemini 1.5 Flash via google-genai SDK. Returns raw code string."""
    # Prefer runtime-configured key from Django settings if available
    api_key = _GEMINI_API_KEY
    try:
        from django.conf import settings as _settings
        api_key = getattr(_settings, "GEMINI_API_KEY", api_key).strip() or api_key
    except Exception:
        pass

    if not api_key or api_key == "your_gemini_api_key_here":
        raise RuntimeError("[LLMRouter/T1] GEMINI_API_KEY not configured.")

    from google import genai                                # late import
    client   = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=_GEMINI_MODEL,
        contents=[prompt],
    )
    raw = response.text or ""
    logger.info("[LLMRouter/T1] Gemini returned %d chars.", len(raw))
    return _strip_markdown(raw)


# ---------------------------------------------------------------------------
# Tier 2 — OpenRouter (Gemma-2-27B → Llama-3-70B cascade)
# ---------------------------------------------------------------------------
def _tier2_openrouter(prompt: str) -> str:
    """Try OpenRouter models in cascade. Returns raw code string."""
    api_key = _OPENROUTER_API_KEY
    try:
        from django.conf import settings as _settings
        api_key = (
            getattr(_settings, "OPENROUTER_API_KEY", api_key).strip()
            or getattr(_settings, "OPENROUTER_SECONDARY_KEY", api_key).strip()
            or api_key
        )
    except Exception:
        pass

    if not api_key:
        raise RuntimeError("[LLMRouter/T2] OPENROUTER_API_KEY not configured.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://anti-gravity.app",
        "X-Title":       "Sri AI Omni-Heal",
    }
    last_exc: Exception = RuntimeError("No OpenRouter models attempted.")

    for model in _OPENROUTER_MODELS:
        try:
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are Sri AI, an autonomous SRE code-healing engine. "
                            "Return ONLY raw code — no markdown, no explanations."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            }
            resp = requests.post(
                f"{_OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            logger.info("[LLMRouter/T2] OpenRouter (%s) returned %d chars.", model, len(raw))
            return _strip_markdown(raw)
        except Exception as exc:
            logger.warning("[LLMRouter/T2] Model %s failed: %s", model, exc)
            last_exc = exc
            continue

    raise last_exc


# ---------------------------------------------------------------------------
# Tier 3 — Ollama (local, zero-cost, air-gapped fallback)
# ---------------------------------------------------------------------------
def _tier3_ollama(prompt: str) -> str:
    """Try local Ollama instance. Returns raw code string."""
    base_url = _OLLAMA_BASE_URL
    model    = _OLLAMA_MODEL

    payload = {
        "model":  model,
        "prompt": prompt,
        "stream": False,
    }
    resp = requests.post(
        f"{base_url}/api/generate",
        json=payload,
        timeout=_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    raw = resp.json().get("response", "").strip()
    logger.info("[LLMRouter/T3] Ollama (%s) returned %d chars.", model, len(raw))
    return _strip_markdown(raw)


# ---------------------------------------------------------------------------
# Public API — the single entry point for all healing patch generation
# ---------------------------------------------------------------------------
def generate_patch(
    error_type:  str,
    error_trace: str,
    broken_file: str = "",
    context:     str = "",
) -> str:
    """
    Generate a code patch using the Poly-Brain fallback hierarchy.

    Parameters
    ----------
    error_type   : Human-readable error category (e.g. "JS_RUNTIME")
    error_trace  : Full traceback or error message
    broken_file  : Current content of the file to be patched (if known)
    context      : Additional JSON/text context (job_id, severity, etc.)

    Returns
    -------
    str : The patched file content (raw code, no markdown fencing).
          Returns an empty string if all tiers are exhausted.

    Raises
    ------
    Never — all exceptions are caught and logged. Callers should treat an
    empty return value as a "no patch available" signal.
    """
    prompt = _build_prompt(error_type, error_trace, broken_file, context)

    # ── Tier 1: Gemini ────────────────────────────────────────────────────────
    try:
        logger.info("[LLMRouter] Attempting Tier 1 — Gemini (%s)…", _GEMINI_MODEL)
        patch = _tier1_gemini(prompt)
        if patch:
            logger.info("[LLMRouter] ✅ Tier 1 (Gemini) succeeded.")
            return patch
    except Exception as exc:
        logger.warning("[LLMRouter] ⚠️  Tier 1 (Gemini) failed: %s — escalating to Tier 2.", exc)

    # ── Tier 2: OpenRouter ───────────────────────────────────────────────────
    try:
        logger.info("[LLMRouter] Attempting Tier 2 — OpenRouter…")
        patch = _tier2_openrouter(prompt)
        if patch:
            logger.info("[LLMRouter] ✅ Tier 2 (OpenRouter) succeeded.")
            return patch
    except Exception as exc:
        logger.warning("[LLMRouter] ⚠️  Tier 2 (OpenRouter) failed: %s — escalating to Tier 3.", exc)

    # ── Tier 3: Ollama (local) ───────────────────────────────────────────────
    try:
        logger.info("[LLMRouter] Attempting Tier 3 — Ollama (%s)…", _OLLAMA_MODEL)
        patch = _tier3_ollama(prompt)
        if patch:
            logger.info("[LLMRouter] ✅ Tier 3 (Ollama) succeeded.")
            return patch
    except Exception as exc:
        logger.error("[LLMRouter] ❌ Tier 3 (Ollama) failed: %s — all tiers exhausted.", exc)

    logger.error(
        "[LLMRouter] ❌ All three LLM tiers failed for error_type=%r. "
        "Returning empty patch.",
        error_type,
    )
    return ""
