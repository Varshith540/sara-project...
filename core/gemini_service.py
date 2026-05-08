"""
ResumeXpert – Gemini AI Service
Powered by Sre AI — Intelligent LLM Router

Sre AI dynamically routes each task to the optimal AI model:
  vision     → Gemini Vision → Gemma-4-Vision → Llama 3.3 70B  (OCR / image scan)
  formatting → Llama 3.3 70B → Gemma-4 → Gemini                (ATS rewrite / analysis)
  research   → Gemini Flash (web-grounded)                      (company intel / scratch)
  general    → Gemini → Gemma-4 → Llama 3.3 70B                (exams / misc)
"""

import json
import re
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

MODEL_NAME = 'models/gemini-2.0-flash-lite'   # primary — best free-tier limits
FALLBACKS  = ['models/gemini-flash-latest', 'models/gemini-2.0-flash']

# ── OpenRouter models ────────────────────────────────────────────────────────
_OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1'

# Tier-3  ── Best FREE text / chat-completions model (formatting, analysis)
_OPENROUTER_MODEL           = 'meta-llama/llama-3.3-70b-instruct:free'

# Tier-2  ── Secondary text model (Google Gemma 4)
_OPENROUTER_SECONDARY_MODEL = 'google/gemma-3-27b-it'

# Vision  ── Free multimodal model for image-based OpenRouter fallback
_OPENROUTER_VISION_MODEL    = 'meta-llama/llama-3.2-11b-vision-instruct:free'

# ---------------------------------------------------------------------------
# Lazy client initialisation
# ---------------------------------------------------------------------------
_client = None   # reset on each server reload


def _get_client():
    """Return a cached google.genai.Client or None if unavailable."""
    global _client
    if _client is not None:
        return _client

    api_key = getattr(settings, 'GEMINI_API_KEY', '').strip()
    if not api_key or api_key == 'your_gemini_api_key_here':
        return None

    try:
        from google import genai
        _client = genai.Client(api_key=api_key)
        return _client
    except Exception as exc:
        logger.warning(f"[Gemini] Could not initialise client: {exc}")
        return None


# ---------------------------------------------------------------------------
# Strict system prompt injected into every OpenRouter request
# ---------------------------------------------------------------------------
_OPENROUTER_SYSTEM_PROMPT = """\
You are 'Sri AI', an expert ATS resume coach and career advisor integrated into the ResumeXpert platform.

STRICT DATA VALIDATION RULES — follow these without exception:

1. PHONE NUMBER FIELD:
   - Must contain ONLY numeric digits and standard phone formatting characters: +, -, spaces, (, ).
   - VALID examples  : "+91 98765 43210", "(555) 123-4567", "+1-800-555-0199"
   - INVALID examples: "2020-2022", "B.Tech 2019-2023", "Jan 2021 – Dec 2022"
   - Date ranges, year spans, or any value containing 4-digit calendar years (1900-2099)
     are NEVER phone numbers. If the phone number is not clearly present, return "Not Provided".

2. MISSING FIELDS:
   - If a field (phone, email, address, etc.) cannot be definitively identified in the document,
     return the string "Not Provided" — do NOT guess or infer from nearby text.

3. JSON FIDELITY:
   - Return ONLY valid JSON that matches the schema requested in the user prompt.
   - Do NOT add extra keys, comments, or markdown fences around the JSON.
   - Every string value must be properly escaped.

4. DATE HANDLING:
   - Date ranges belong ONLY in 'experience', 'education', or 'projects' sections.
   - Never place date ranges in contact-information fields (phone, email, address).

5. CONTACT SYMBOL AMBIGUITY:
   - Resume templates often use icons (📞 ✉ 🔗) followed by contact details.
   - A phone icon (📞 or similar) followed by "2020-2022" means the icon is decorative;
     "2020-2022" is a date range, NOT a phone number. Treat it as such.

6. NUMERIC DISCRIMINATION:
   - A valid phone number has 7–15 digits.
   - A year range such as "2020-2022" or "2019–2023" has exactly 4+4 = 8 digits but
     matches the pattern YYYY[-–]YYYY or YYYY[-–]present. Always classify these as dates.

7. LANGUAGE & TONE:
   - Responses must be professional, concise, and actionable.

8. ACCURACY OVER CREATIVITY:
   - Do not fabricate or hallucinate contact details, companies, or qualifications.

9. SCHEMA COMPLIANCE:
   - Always return every key specified in the user prompt's JSON schema.
   - If a list is expected, return a list even if it has only one item.
"""


def _sanitise_phone(phone: str) -> str:
    """
    Post-processing guard: reject any phone string that looks like a year range
    or contains a standalone 4-digit calendar year (1900-2099).

    Returns the original string if it passes, or '' if it is clearly not a phone.
    """
    if not phone:
        return phone

    # Pattern 1: YYYY-YYYY or YYYY–YYYY (year range)
    if re.search(r'\b(19|20)\d{2}\s*[-–—]\s*(19|20)\d{2}\b', phone):
        print(f'[PhoneSanitiser] Rejected year-range misread as phone: {phone!r}')
        return ''

    # Pattern 2: Contains any standalone 4-digit calendar year (1900-2099)
    if re.search(r'\b(19|20)\d{2}\b', phone):
        print(f'[PhoneSanitiser] Rejected date-containing value as phone: {phone!r}')
        return ''

    # Pattern 3: Fewer than 7 digits total (too short for any real phone number)
    digits_only = re.sub(r'\D', '', phone)
    if len(digits_only) < 7:
        print(f'[PhoneSanitiser] Rejected short non-phone value: {phone!r}')
        return ''

    return phone


def _call_openrouter(prompt: str) -> tuple[str, str]:
    """
    Call the OpenRouter API with the given prompt.
    Returns (response_text, model_label) or raises on failure.
    """
    api_key = getattr(settings, 'OPENROUTER_API_KEY', '').strip()
    model   = getattr(settings, 'OPENROUTER_MODEL', _OPENROUTER_MODEL)
    base    = getattr(settings, 'OPENROUTER_BASE_URL', _OPENROUTER_BASE_URL)

    if not api_key:
        raise RuntimeError("[OpenRouter] OPENROUTER_API_KEY is not configured.")

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type':  'application/json',
        'HTTP-Referer':  'https://resumexpert.app',
        'X-Title':       'ResumeXpert',
    }
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': _OPENROUTER_SYSTEM_PROMPT},
            {'role': 'user',   'content': prompt},
        ],
    }
    response = requests.post(
        f'{base}/chat/completions',
        headers=headers,
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    raw_text = data['choices'][0]['message']['content'].strip()

    # ── Post-processing: sanitise phone-like fields in JSON responses ─────────
    # If the response is JSON, scan for a 'phone' key and validate its value.
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict):
            for key in ('phone', 'phone_number', 'contact_number', 'mobile'):
                if key in parsed:
                    parsed[key] = _sanitise_phone(str(parsed[key]))
            raw_text = json.dumps(parsed)
    except (json.JSONDecodeError, TypeError):
        pass   # not JSON — no sanitisation needed

    return raw_text, f'OpenRouter ({model.split("/")[-1]})'


def _call_openrouter_secondary(prompt: str) -> tuple[str, str]:
    """
    Tier-2 fallback: Call OpenRouter using the SECONDARY key + Gemma 4 model.
    Keeps Tier-2 quota separate from Tier-3 (Nemotron).
    Returns (response_text, model_label) or raises on failure.
    """
    api_key = getattr(settings, 'OPENROUTER_SECONDARY_KEY', '').strip()
    model   = getattr(settings, 'OPENROUTER_SECONDARY_MODEL', _OPENROUTER_SECONDARY_MODEL)
    base    = getattr(settings, 'OPENROUTER_BASE_URL', _OPENROUTER_BASE_URL)

    if not api_key:
        raise RuntimeError('[OpenRouter Tier-2] OPENROUTER_SECONDARY_KEY is not configured.')

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type':  'application/json',
        'HTTP-Referer':  'https://resumexpert.app',
        'X-Title':       'ResumeXpert',
    }
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': _OPENROUTER_SYSTEM_PROMPT},
            {'role': 'user',   'content': prompt},
        ],
    }
    response = requests.post(
        f'{base}/chat/completions',
        headers=headers,
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    data     = response.json()
    raw_text = data['choices'][0]['message']['content'].strip()

    # Apply the same phone sanitisation
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict):
            for key in ('phone', 'phone_number', 'contact_number', 'mobile'):
                if key in parsed:
                    parsed[key] = _sanitise_phone(str(parsed[key]))
            raw_text = json.dumps(parsed)
    except (json.JSONDecodeError, TypeError):
        pass

    return raw_text, f'Gemma 4 via OpenRouter ({model.split("/")[-1]})'

# ===========================================================================
# SRE AI ROUTER  — Intelligent LLM Middleware
# ===========================================================================
class SreAIRouter:
    """
    Sre AI — Smart routing middleware that dispatches each AI task to the
    optimal model based on task_type, optimising for accuracy, speed, and
    token cost.

    Task types
    ----------
    'vision'     Scanned PDF / image OCR
                 Route: Gemini Vision → Gemma-4 Vision (OR) → Llama 3.2-11B Vision (OR)

    'formatting' ATS resume rewrite & analysis (deep text reasoning)
                 Route: Llama 3.3-70B (OR) → Gemma-4 (OR) → Gemini
                 Rationale: Llama 3.3-70B scores highest on instruction-following
                 benchmarks for structured JSON / text tasks and is free.

    'research'   Real-time company intel, scratch resume from JD
                 Route: Gemini Flash ONLY (has web grounding / real-time knowledge)
                 Falls back gracefully with a warning if Gemini is unavailable.

    'general'    Exam MCQ generation and miscellaneous tasks
                 Route: Gemini → Gemma-4 (OR) → Llama 3.3-70B (OR)

    All routes return (response_text: str, model_label: str).
    """

    VISION     = 'vision'
    FORMATTING = 'formatting'
    RESEARCH   = 'research'
    GENERAL    = 'general'

    # ── Shared OpenRouter helper ──────────────────────────────────────────────
    @staticmethod
    def _or_post(api_key: str, model: str, messages: list,
                 timeout: int = 60) -> str:
        """POST to OpenRouter /chat/completions; returns raw content string."""
        base = getattr(settings, 'OPENROUTER_BASE_URL', _OPENROUTER_BASE_URL)
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type':  'application/json',
            'HTTP-Referer':  'https://resumeexpert-2eiv.onrender.com',
            'X-Title':       'Anti Gravity Resume Analyzer',
        }
        resp = requests.post(
            f'{base}/chat/completions',
            headers=headers,
            json={'model': model, 'messages': messages},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content'].strip()

    # ── FORMATTING route  (Gemini → Cascading Fallback Array) ───────────────
    def route_formatting(self, prompt: str) -> tuple[str, str]:
        """
        Deep text reasoning: ATS analysis, resume rewriting.
        Priority: 
          1. Gemini 1.5 Flash (Primary)
          2. Cascading Fallback Array on OpenRouter (Llama-3, etc)
        """
        # ① Gemini (Primary for fast throughput)
        client = _get_client()
        if client:
            print('[Sre AI ▶ FORMATTING] Attempting direct Gemini API (gemini-1.5-flash)...')
            for model in [MODEL_NAME] + FALLBACKS:
                try:
                    resp  = client.models.generate_content(model=model,
                                                           contents=prompt)
                    label = f'Gemini ({model.split("/")[-1]})'
                    print(f'[Sre AI ✓] Formatting succeeded with {label}.')
                    return resp.text.strip(), label
                except Exception as e:
                    logger.warning(f'[Sre AI] Gemini {model} failed: {str(e)[:200]}')

        # ② OpenRouter Cascading Fallback Array
        or_key1 = getattr(settings, 'OPENROUTER_API_KEY', '').strip()
        or_key2 = getattr(settings, 'OPENROUTER_SECONDARY_KEY', '').strip()
        or_key = or_key1 if or_key1.startswith('sk-or-v1') else (or_key2 if or_key2.startswith('sk-or-v1') else (or_key1 or or_key2))

        fallback_models = [
            'meta-llama/llama-3.3-70b-instruct:free',
            'openrouter/free'
        ]
        
        messages = [
            {'role': 'system', 'content': _OPENROUTER_SYSTEM_PROMPT},
            {'role': 'user',   'content': prompt},
        ]

        if or_key:
            print('[Sre AI ▶ FORMATTING] Gemini failed/exhausted. Initiating OpenRouter Fallback Array...')
            for model_name in fallback_models:
                print(f'[Sre AI ▶ FORMATTING] Trying model: {model_name}...')
                try:
                    raw = self._or_post(or_key, model_name, messages)
                    label = f'OpenRouter ({model_name.split("/")[-1]})'
                    print(f'[Sre AI ✓] Formatting succeeded with {label}.')
                    return raw, label
                except requests.exceptions.RequestException as e:
                    err_msg = str(e.response.text) if hasattr(e, 'response') and e.response else str(e)
                    logger.warning(f'[Sre AI] OpenRouter Model {model_name} failed: {err_msg[:200]}... Moving to next.')
                except Exception as e:
                    logger.warning(f'[Sre AI] OpenRouter Model {model_name} failed: {str(e)[:200]}... Moving to next.')
        else:
            print('[Sre AI ▶ FORMATTING] No OpenRouter key configured, skipping Fallback Array.')

        raise RuntimeError(
            '[Sre AI] All FORMATTING backends exhausted. '
            'Both Gemini API and OpenRouter models failed.'
        )

    # ── RESEARCH route  (Gemini → Cascading Fallback Array) ───────────────
    def route_research(self, prompt: str) -> tuple[str, str]:
        """
        Real-time research / company intel / scratch resume generation.
        Priority: 
          1. Gemini 1.5 Flash (Primary, web-grounded)
          2. Cascading Fallback Array on OpenRouter (Gemma-2, Llama-3)
        """
        # ① Gemini (Primary for web-grounded intel)
        client = _get_client()
        if client:
            print('[Sre AI ▶ RESEARCH] Routing to Gemini (web-grounded)...')
            for model in [MODEL_NAME] + FALLBACKS:
                try:
                    resp  = client.models.generate_content(model=model,
                                                           contents=prompt)
                    label = f'Gemini ({model.split("/")[-1]}) [research]'
                    print(f'[Sre AI ✓] Research succeeded with {label}.')
                    return resp.text.strip(), label
                except Exception as e:
                    msg = str(e)
                    if '429' in msg or '404' in msg or '503' in msg:
                        logger.warning(f'[Sre AI] Gemini {model} quota/unavailable: {msg[:80]}')
                        continue
                    logger.warning(f'[Sre AI] Gemini {model} research error: {msg[:80]}')
                    continue

        # ② OpenRouter Cascading Fallback Array
        or_key1 = getattr(settings, 'OPENROUTER_API_KEY', '').strip()
        or_key2 = getattr(settings, 'OPENROUTER_SECONDARY_KEY', '').strip()
        or_key = or_key1 if or_key1.startswith('sk-or-v1') else (or_key2 if or_key2.startswith('sk-or-v1') else (or_key1 or or_key2))
        
        fallback_models = [
            'meta-llama/llama-3.1-8b-instruct:free',
            'google/gemma-2-9b-it:free'
        ]
        
        messages = [
            {'role': 'system', 'content': _OPENROUTER_SYSTEM_PROMPT},
            {'role': 'user',   'content': prompt},
        ]

        if or_key:
            print('[Sre AI ▶ RESEARCH] Gemini failed/exhausted. Initiating OpenRouter Fallback Array...')
            for model_name in fallback_models:
                print(f'[Sre AI ▶ RESEARCH] Trying model: {model_name}...')
                try:
                    raw = self._or_post(or_key, model_name, messages)
                    label = f'OpenRouter ({model_name.split("/")[-1]}) [research]'
                    print(f'[Sre AI ✓] Research succeeded with {label}.')
                    return raw, label
                except requests.exceptions.RequestException as e:
                    err_msg = str(e.response.text) if hasattr(e, 'response') and e.response else str(e)
                    logger.warning(f'[Sre AI] OpenRouter Model {model_name} failed: {err_msg[:200]}... Moving to next.')
                except Exception as e:
                    logger.warning(f'[Sre AI] OpenRouter Model {model_name} failed: {str(e)[:200]}... Moving to next.')
        else:
            print('[Sre AI ▶ RESEARCH] No OpenRouter key configured, skipping Fallback Array.')

        raise RuntimeError(
            '[Sre AI] All RESEARCH backends exhausted. '
            'Both Gemini API and OpenRouter models failed.'
        )

    # ── GENERAL route  (Gemini → Gemma-4 → Llama — current proven order) ────
    def route_general(self, prompt: str) -> tuple[str, str]:
        """
        General tasks: exam MCQ generation, misc AI calls.
        Current proven order: Gemini → Gemma-4 → Llama 3.3-70B.
        """
        client = _get_client()

        # ① Gemini
        if client:
            print('[Sre AI ▶ GENERAL] Routing to Gemini...')
            for model in [MODEL_NAME] + FALLBACKS:
                try:
                    resp  = client.models.generate_content(model=model,
                                                           contents=prompt)
                    label = f'Gemini ({model.split("/")[-1]})'
                    print(f'[Sre AI ✓] General succeeded with {label}.')
                    return resp.text.strip(), label
                except Exception as e:
                    msg = str(e)
                    if '429' in msg or '404' in msg or '503' in msg:
                        logger.warning(f'[Sre AI] Gemini {model} unavailable: {msg[:80]}')
                        continue
                    logger.warning(f'[Sre AI] Gemini {model} error: {e}')
                    continue

        # ② Gemma-4
        or_key1 = getattr(settings, 'OPENROUTER_API_KEY', '').strip()
        or_key2 = getattr(settings, 'OPENROUTER_SECONDARY_KEY', '').strip()
        best_or_key = or_key1 if or_key1.startswith('sk-or-v1') else (or_key2 if or_key2.startswith('sk-or-v1') else (or_key1 or or_key2))
        
        t2_key   = best_or_key
        t2_model = getattr(settings, 'OPENROUTER_SECONDARY_MODEL',
                           _OPENROUTER_SECONDARY_MODEL)
        if t2_key:
            print(f'[Sre AI ▶ GENERAL] Falling back to Gemma-4...')
            try:
                msgs = [
                    {'role': 'system', 'content': _OPENROUTER_SYSTEM_PROMPT},
                    {'role': 'user',   'content': prompt},
                ]
                raw   = self._or_post(t2_key, t2_model, msgs)
                label = f'Gemma-4 via OpenRouter ({t2_model.split("/")[-1]})'
                print(f'[Sre AI ✓] General succeeded with {label}.')
                return raw, label
            except Exception as e:
                logger.warning(f'[Sre AI] Gemma-4 general failed: {e}')

        # ③ Llama 3.3-70B
        t3_key   = best_or_key
        t3_model = getattr(settings, 'OPENROUTER_MODEL', _OPENROUTER_MODEL)
        if t3_key:
            print(f'[Sre AI ▶ GENERAL] Falling back to Llama 3.3-70B...')
            try:
                msgs = [
                    {'role': 'system', 'content': _OPENROUTER_SYSTEM_PROMPT},
                    {'role': 'user',   'content': prompt},
                ]
                raw   = self._or_post(t3_key, t3_model, msgs)
                label = f'Llama 3.3-70B via OpenRouter ({t3_model.split("/")[-1]})'
                print(f'[Sre AI ✓] General succeeded with {label}.')
                return raw, label
            except Exception as e:
                logger.error(f'[Sre AI] Llama 3.3-70B general failed: {e}')

        raise RuntimeError(
            '[Sre AI] All GENERAL backends exhausted.'
        )

    # ── Public dispatch method ────────────────────────────────────────────────
    def route(self, task_type: str, prompt: str,
              image_bytes: bytes = None,
              mime_type: str = None) -> tuple[str, str]:
        """
        Main dispatch — call this instead of _generate() everywhere.

        Parameters
        ----------
        task_type  : 'vision' | 'formatting' | 'research' | 'general'
        prompt     : full prompt string
        image_bytes: raw image bytes (vision only)
        mime_type  : MIME type of image (vision only)
        """
        print(f'[Sre AI] Task received → type={task_type!r}')
        if task_type == self.VISION:
            # Vision is handled entirely by analyze_resume_image_with_gemini();
            # this branch is a safety net for direct router calls.
            raise NotImplementedError(
                '[Sre AI] Call analyze_resume_image_with_gemini() directly for vision tasks.'
            )
        elif task_type == self.FORMATTING:
            return self.route_formatting(prompt)
        elif task_type == self.RESEARCH:
            return self.route_research(prompt)
        else:
            return self.route_general(prompt)


# Module-level singleton — import and use this everywhere
_sre_router = SreAIRouter()


# ---------------------------------------------------------------------------
# Legacy _generate() — now proxies through Sre AI Router
# ---------------------------------------------------------------------------
def _generate(client, prompt: str,
              task_type: str = SreAIRouter.GENERAL) -> tuple[str, str]:
    """
    Proxy to Sre AI Router.
    `client` is accepted for API compatibility but the router manages
    its own Gemini client via _get_client().
    """
    return _sre_router.route(task_type, prompt)


def is_gemini_available() -> bool:
    """Return True if Gemini is configured."""
    return _get_client() is not None


# ---------------------------------------------------------------------------
# PDF → JPEG pre-processor (page 1 only, compressed, < 1 MB target)
# ---------------------------------------------------------------------------
def convert_pdf_to_jpeg(pdf_path: str, dpi: int = 150) -> bytes | None:
    """
    Convert the FIRST page of a PDF to a compressed JPEG in memory.
    Returns raw JPEG bytes, or None if both libraries are unavailable.

    DPI=150 targets ~600×800px — small enough for fast API upload (<500 KB
    for most resumes) while retaining all text legibility for OCR.

    Strategy:
      1. PyMuPDF (fitz)  — fastest, no Poppler dependency
      2. pdf2image       — fallback, needs Poppler on PATH
    """
    import io

    # ── Strategy 1: PyMuPDF ──────────────────────────────────────────────────
    try:
        import fitz  # PyMuPDF
        doc  = fitz.open(pdf_path)
        page = doc.load_page(0)
        mat  = fitz.Matrix(dpi / 72, dpi / 72)   # 72 DPI is PDF native
        pix  = page.get_pixmap(matrix=mat, alpha=False)
        img_bytes = pix.tobytes('jpeg')
        doc.close()
        kb = len(img_bytes) // 1024
        print(f'[PDFConvert] Page-1 JPEG via PyMuPDF: {kb} KB at {dpi} DPI.')
        return img_bytes
    except ImportError:
        print('[PDFConvert] PyMuPDF not installed — trying pdf2image.')
    except Exception as e:
        print(f'[PDFConvert] PyMuPDF failed: {e} — trying pdf2image.')

    # ── Strategy 2: pdf2image ────────────────────────────────────────────────
    try:
        from pdf2image import convert_from_path
        import PIL.Image
        pages = convert_from_path(pdf_path, dpi=dpi, first_page=1, last_page=1)
        if not pages:
            return None
        buf = io.BytesIO()
        pages[0].save(buf, format='JPEG', quality=75, optimize=True)
        img_bytes = buf.getvalue()
        kb = len(img_bytes) // 1024
        print(f'[PDFConvert] Page-1 JPEG via pdf2image: {kb} KB at {dpi} DPI.')
        return img_bytes
    except ImportError:
        print('[PDFConvert] pdf2image not installed. Cannot pre-process PDF.')
    except Exception as e:
        print(f'[PDFConvert] pdf2image failed: {e}')

    return None


# ---------------------------------------------------------------------------
# Multimodal: Analyse a resume IMAGE or SCANNED PDF (OCR + Analysis)
# ---------------------------------------------------------------------------
def analyze_resume_image_with_gemini(image_path: str, job_description: str) -> dict:
    """
    Analyse a resume IMAGE or SCANNED PDF using Vision AI.

    For scanned PDFs:
      → Convert page-1 to a compressed JPEG first (~150 DPI, <1 MB)
      → Send the JPEG to Vision AI (never send the raw 20 MB PDF)

    For uploaded images (.jpg/.jpeg/.png):
      → Send raw bytes directly

    Tier chain:
      Vision-1  Gemini Flash Vision    (google.genai)
      Vision-2  Gemma 4 via OpenRouter (secondary key)
      Vision-3  Nemotron via OpenRouter (primary key)

    Returns the same dict structure as analyze_resume_with_gemini().
    """
    import mimetypes
    import base64
    import io
    import requests as _req

    client    = _get_client()
    mime_type, _ = mimetypes.guess_type(image_path)
    mime_type = mime_type or 'image/jpeg'
    is_pdf    = mime_type == 'application/pdf'

    # ── Pre-process: PDF → compressed JPEG ───────────────────────────────────
    if is_pdf:
        print(f'[Vision] Scanned PDF detected — converting page-1 to JPEG for Vision AI...')
        jpeg_bytes = convert_pdf_to_jpeg(image_path, dpi=150)
        if jpeg_bytes:
            image_bytes = jpeg_bytes
            mime_type   = 'image/jpeg'
            kb = len(image_bytes) // 1024
            print(f'[Vision] Using pre-processed JPEG ({kb} KB) instead of raw PDF.')
        else:
            # Pre-processing unavailable — try sending raw PDF (may timeout on large files)
            print('[Vision] PDF pre-processing unavailable — sending raw PDF bytes (may be slow).')
            try:
                with open(image_path, 'rb') as f:
                    image_bytes = f.read()
            except Exception as exc:
                logger.error(f'[Vision] Could not read PDF {image_path}: {exc}')
                return {}
    else:
        try:
            with open(image_path, 'rb') as f:
                image_bytes = f.read()
            kb = len(image_bytes) // 1024
            print(f'[Vision] Image file loaded: {kb} KB, mime={mime_type}.')
        except Exception as exc:
            logger.error(f'[Vision] Could not read file {image_path}: {exc}')
            return {}

    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    doc_label = 'SCANNED PDF (page 1)' if is_pdf else 'IMAGE'

    vision_prompt = f"""You are 'Sri AI,' an expert ATS resume coach.
The user has uploaded a {doc_label} of their resume.
Perform high-accuracy OCR on this resume image and return the data in the requested JSON format.

Step 1 — OCR: Extract ALL text visible in the image, preserving structure (name, contact, summary, skills, experience, education, projects, certifications, etc.).
Step 2 — ATS Analysis: Using the extracted text, analyse the resume against the job description below.

Job Description:
\"\"\"{job_description[:1500]}\"\"\"

STRICT RULES:
- Phone Number must ONLY contain numeric digits and formatting chars (+, -, spaces). Date ranges like "2020-2022" are NOT phone numbers.
- If a field is not found, use "Not Provided".
- Return ONLY valid JSON, no markdown fences, no extra text.

JSON Schema:
{{
  "ocr_text": "Full text extracted from the resume image",
  "ai_summary": "2-3 sentences: candidate fit, strongest skills, key gaps.",
  "benchmark_comparison": "2-3 sentences comparing against world-class resume benchmarks.",
  "job_fit_score": <integer 0-100>,
  "ai_suggestions": ["Suggestion 1", "Suggestion 2", "Suggestion 3", "Suggestion 4", "Suggestion 5"],
  "interview_questions": ["Question 1", "Question 2", "Question 3", "Question 4", "Question 5"]
}}"""

    def _parse_vision_response(raw: str, label: str) -> dict:
        raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
        raw = re.sub(r'\s*```$', '', raw)
        data      = json.loads(raw, strict=False)
        ocr_text  = data.get('ocr_text', '')
        summary   = data.get('ai_summary', '')
        benchmark = data.get('benchmark_comparison', '')
        if benchmark:
            summary += (
                f"<br><br><strong style='color:#0f766e;'>"
                f"<i class='bi bi-globe me-1'></i>Global Benchmark Comparison:</strong> {benchmark}"
            )
        return {
            'ocr_text':            ocr_text,
            'ai_summary':          summary,
            'ai_suggestions':      data.get('ai_suggestions', []),
            'interview_questions': data.get('interview_questions', []),
            'job_fit_score':       int(data.get('job_fit_score', 0)),
            'active_model':        label,
        }

    # ── VISION TIER 1: Gemini Flash Vision ────────────────────────────────────
    if client:
        print('[AI STATUS] Vision Tier-1: Attempting Gemini Vision...')
        for model in [MODEL_NAME] + FALLBACKS:
            try:
                from google.genai import types as genai_types
                response = client.models.generate_content(
                    model=model,
                    contents=[
                        genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                        vision_prompt,
                    ],
                )
                label = f'Gemini Vision ({model.split("/")[-1]})'
                result = _parse_vision_response(response.text, label)
                print(f'[AI STATUS] Vision Tier-1 succeeded with {label}.')
                return result
            except Exception as exc:
                msg = str(exc)
                if '429' in msg or '404' in msg or '503' in msg:
                    logger.warning(f'[Vision Tier-1] {model} unavailable ({msg[:80]}), trying next…')
                    continue
                logger.warning(f'[Vision Tier-1] {model} error: {exc}')
                continue

    # ── VISION TIER 2: Gemma 4 via OpenRouter (secondary key) ────────────────
    print('[AI STATUS] Vision Tier-1 Failed. Attempting Vision Tier-2 (Gemma 4 via OpenRouter)...')
    t2_api_key = getattr(settings, 'OPENROUTER_SECONDARY_KEY', '').strip()
    t2_model   = getattr(settings, 'OPENROUTER_SECONDARY_MODEL', _OPENROUTER_SECONDARY_MODEL)
    t2_base    = getattr(settings, 'OPENROUTER_BASE_URL', _OPENROUTER_BASE_URL)

    if t2_api_key:
        try:
            t2_headers = {
                'Authorization': f'Bearer {t2_api_key}',
                'Content-Type':  'application/json',
                'HTTP-Referer':  'https://resumexpert.app',
                'X-Title':       'ResumeXpert',
            }
            t2_payload = {
                'model': t2_model,
                'messages': [{
                    'role': 'user',
                    'content': [
                        {'type': 'image_url', 'image_url': {'url': f'data:{mime_type};base64,{image_b64}'}},
                        {'type': 'text', 'text': vision_prompt},
                    ],
                }],
            }
            resp = _req.post(
                f'{t2_base}/chat/completions',
                headers=t2_headers,
                json=t2_payload,
                timeout=60,
            )
            resp.raise_for_status()
            raw   = resp.json()['choices'][0]['message']['content']
            label = f'Gemma 4 Vision via OpenRouter ({t2_model.split("/")[-1]})'
            result = _parse_vision_response(raw, label)
            print(f'[AI STATUS] Vision Tier-2 succeeded with {label}.')
            return result
        except _req.exceptions.Timeout:
            logger.warning('[Vision Tier-2] Connection timeout (>60s) — switching to Tier-3.')
        except Exception as t2_exc:
            logger.warning(f'[Vision Tier-2] Failed: {t2_exc}')
    else:
        print('[Vision Tier-2] OPENROUTER_SECONDARY_KEY not configured — skipping.')

    # ── VISION TIER 3: Nemotron via OpenRouter (primary key) ─────────────────
    print('[AI STATUS] Vision Tier-2 Failed. Attempting Vision Tier-3 (Nemotron via OpenRouter)...')
    t3_api_key = getattr(settings, 'OPENROUTER_API_KEY', '').strip()
    t3_model   = getattr(settings, 'OPENROUTER_MODEL', _OPENROUTER_MODEL)
    t3_base    = getattr(settings, 'OPENROUTER_BASE_URL', _OPENROUTER_BASE_URL)

    if t3_api_key:
        try:
            t3_headers = {
                'Authorization': f'Bearer {t3_api_key}',
                'Content-Type':  'application/json',
                'HTTP-Referer':  'https://resumexpert.app',
                'X-Title':       'ResumeXpert',
            }
            t3_payload = {
                'model': t3_model,
                'messages': [{
                    'role': 'user',
                    'content': [
                        {'type': 'image_url', 'image_url': {'url': f'data:{mime_type};base64,{image_b64}'}},
                        {'type': 'text', 'text': vision_prompt},
                    ],
                }],
            }
            resp = _req.post(
                f'{t3_base}/chat/completions',
                headers=t3_headers,
                json=t3_payload,
                timeout=60,
            )
            resp.raise_for_status()
            raw   = resp.json()['choices'][0]['message']['content']
            label = f'OpenRouter Vision ({t3_model.split("/")[-1]})'
            result = _parse_vision_response(raw, label)
            print(f'[AI STATUS] Vision Tier-3 succeeded with {label}.')
            return result
        except _req.exceptions.Timeout:
            logger.error('[Vision Tier-3] Connection timeout (>60s).')
            raise TimeoutError(
                'Vision AI timed out (>60 s). The document may be too complex. '
                'Try a clearer scan or a smaller image.'
            )
        except Exception as t3_exc:
            logger.error(f'[Vision Tier-3] Failed: {t3_exc}')

    logger.error('[Vision] All vision tiers failed.')
    return {}




# ---------------------------------------------------------------------------
# Resume Analysis
# ---------------------------------------------------------------------------

def analyze_resume_with_gemini(resume_text: str, job_description: str) -> dict:
    """
    Analyse resume vs job description using Gemini.
    Returns dict with ai_summary, ai_suggestions, job_fit_score.
    Returns {} on failure.
    """
    client = _get_client()
    if client is None:
        return {}

    prompt = f"""You are 'Sri AI,' a proactive, analytical, and self-improving AI integrated into the ResumeXpert platform. Your mission is to 'lift' users' careers by identifying and removing the 'gravity' (weaknesses/errors) from their resumes and job applications.
You are acting as an expert ATS resume coach and HR consultant.

Analyse the following resume against the job description and respond with ONLY valid JSON (no markdown, no extra text outside the JSON).
Additionally, comprehensively compare this resume against top resumes from diverse sectors, including global CEOs (like Amazon, Jeff Bezos, Mark Zuckerberg) and highly skilled non-IT professionals. Provide real-time, automated feedback for continuous improvement.
Also, generate 5 tailored technical/HR questions that the user might face in an interview for this specific role based on their resume and the JD.

Resume:
\"\"\"
{resume_text[:4000]}
\"\"\"

Job Description:
\"\"\"
{job_description[:1500]}
\"\"\"

Respond with this exact JSON format:
{{
  "ai_summary": "2-3 sentence paragraph describing how well the candidate fits this role, mentioning their strongest relevant skills and biggest gaps.",
  "benchmark_comparison": "A 2-3 sentence paragraph comparing the candidate's resume style, structure, and impact against world-class benchmarks (e.g. global CEOs and top non-IT professionals) and suggesting high-level continuous improvement.",
  "job_fit_score": <integer 0-100 representing overall fit>,
  "ai_suggestions": [
    "Specific actionable suggestion 1",
    "Specific actionable suggestion 2",
    "Specific actionable suggestion 3",
    "Specific actionable suggestion 4",
    "Specific actionable suggestion 5"
  ],
  "interview_questions": [
    "Question 1",
    "Question 2",
    "Question 3",
    "Question 4",
    "Question 5"
  ]
}}"""

    try:
        raw, active_model = _generate(client, prompt, task_type=SreAIRouter.FORMATTING)

        # Strip markdown code fences if present
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        data = json.loads(raw, strict=False)
        
        summary = data.get('ai_summary', '')
        benchmark = data.get('benchmark_comparison', '')
        if benchmark:
            summary += f"<br><br><strong style='color:#0f766e;'><i class='bi bi-globe me-1'></i>Global Benchmark Comparison:</strong> {benchmark}"

        return {
            'ai_summary':          summary,
            'ai_suggestions':      data.get('ai_suggestions', []),
            'interview_questions': data.get('interview_questions', []),
            'job_fit_score':       int(data.get('job_fit_score', 0)),
            'active_model':        active_model,
        }
    except Exception as exc:
        logger.warning(f"[Gemini] analyze_resume_with_gemini failed: {exc}")
        return {}


# ---------------------------------------------------------------------------
# Dynamic Exam Question Generation
# ---------------------------------------------------------------------------
def generate_exam_questions_with_gemini(skills: list, num_questions: int = 5, difficulty: str = "Intermediate") -> list:
    """
    Generate fresh MCQ questions for the given skills using Gemini.
    Returns list of question dicts matching exam_generator.py format.
    Returns [] on failure.
    """
    client = _get_client()
    if client is None or not skills:
        return []

    skills_str = ', '.join(skills[:6])

    prompt = f"""You are 'Sri AI,' a proactive, analytical, and self-improving AI integrated into the ResumeXpert platform. Your mission is to 'lift' users' careers by identifying and removing the 'gravity' (weaknesses/errors) from their resumes and job applications.
You are acting as a technical interviewer creating a skill assessment quiz.

Generate exactly {num_questions} multiple-choice questions for these skills: {skills_str}.
The difficulty level should be: {difficulty}.

Respond with ONLY valid JSON — no markdown, no explanation.
Use this exact format:
[
  {{
    "skill": "skill name",
    "question": "The question text?",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "correct_index": <0-3 integer, 0=A 1=B 2=C 3=D>,
    "explanation": "Brief explanation of the correct answer."
  }}
]"""

    try:
        raw, active_model = _generate(client, prompt, task_type=SreAIRouter.GENERAL)

        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        questions = json.loads(raw)
        validated = []
        for q in questions:
            if all(k in q for k in ('skill', 'question', 'options', 'correct_index')):
                if isinstance(q['options'], list) and len(q['options']) == 4:
                    validated.append({
                        'skill':         q['skill'],
                        'question':      q['question'],
                        'options':       q['options'],
                        'correct_index': int(q['correct_index']),
                        'explanation':   q.get('explanation', ''),
                    })
        return validated

    except Exception as exc:
        logger.warning(f"[Gemini] generate_exam_questions_with_gemini failed: {exc}")
        return []


# ---------------------------------------------------------------------------
# AI Resume Rewriter
# ---------------------------------------------------------------------------
def rewrite_resume_with_gemini(
    resume_text: str,
    job_description: str,
    missing_skills: list,
    suggestions: list,
    exam_results: str = "",
    target_industry: str = "",
) -> dict:
    """
    Rewrite the candidate's resume using Gemini AI to better match the JD (3-Pass Verification).
    Returns dict with:
        rewritten_resume  – full plain-text rewritten resume
        improvement_notes – bullet list of key changes made
    Returns {} on failure.
    """
    client = _get_client()
    if client is None:
        return {}

    missing_str    = ', '.join(missing_skills[:8]) if missing_skills else 'None identified'
    suggestions_str = '\n'.join(f'- {s}' for s in suggestions[:6]) if suggestions else '- Tailor content to the JD'
    exam_context   = f"\n\nSkill Test Validations:\n{exam_results}" if exam_results else ""

    # PASS 1: Generate Draft
    prompt_pass_1 = f"""You are 'Sri AI,' a proactive, analytical, and self-improving AI.
You are acting as an expert ATS (Applicant Tracking System) specialist.

Generate a comprehensive initial draft of a rewritten resume that maximises ATS score for the given job description.
RULES:
1. Keep factual information accurate (no fake jobs/degrees).
2. Use strong action verbs and weave in high-frequency JD keywords.
3. Incorporate and heavily highlight the 'Skill Test Validations' in the summary and skills sections.

Original Resume:
{resume_text[:4000]}

Job Description:
{job_description[:1500]}
{exam_context}

Output ONLY the plain-text draft resume.
"""
    try:
        draft_text, active_model = _generate(client, prompt_pass_1, task_type=SreAIRouter.FORMATTING)
        
        # PASS 2: Strict Verification
        industry_audit = f"\nSince the target industry is '{target_industry}', aggressively audit the resume for industry-specific compliance, standards, certifications, and technical paradigms relevant to this sector." if target_industry else ""
        
        prompt_pass_2 = f"""You are 'Sri AI,' an aggressive ATS auditor.
Critique the following draft resume against the job description and skill test validations.
{industry_audit}

Job Description:
{job_description[:1500]}
{exam_context}

Draft Resume:
{draft_text}

Identify:
1. Missing critical keywords from the JD.
2. Formatting inconsistencies.
3. Hallucinations or errors.
4. Unused skill test validations.

Output ONLY a plain-text list of critical verification issues.
"""
        verification_notes, _ = _generate(client, prompt_pass_2, task_type=SreAIRouter.FORMATTING)

        # PASS 3: Final Refinement
        prompt_pass_3 = f"""You are 'Sri AI,' the final resume polisher.
Refine the draft resume below by resolving ALL the verification issues identified by the auditor.

Draft Resume:
{draft_text}

Verification Issues to Fix:
{verification_notes}

Respond with this EXACT JSON format:
{{
  "rewritten_resume": "FULL plain-text finalized rewritten resume here. Use newlines and section headers like SUMMARY, SKILLS, EXPERIENCE, EDUCATION, PROJECTS. No markdown symbols like ** or ##.",
  "skills": ["Skill1", "Skill2", "Skill3"],
  "improvement_notes": [
    "Resolved hallucination X",
    "Added missing keyword Y",
    "Highlighted validated skill Z"
  ]
}}"""
        raw, _ = _generate(client, prompt_pass_3, task_type=SreAIRouter.FORMATTING)

        # Strip markdown code fences if present
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        data = json.loads(raw, strict=False)
        
        # Skill bug fix: ensure it's a list, not chopped into characters
        skills_extracted = data.get('skills', [])
        if isinstance(skills_extracted, str):
            skills_extracted = [s.strip() for s in skills_extracted.split(',') if s.strip()]
            
        return {
            'rewritten_resume':  data.get('rewritten_resume', ''),
            'skills':            skills_extracted,
            'improvement_notes': data.get('improvement_notes', []),
            'active_model':      active_model,
        }
    except Exception as exc:
        logger.warning(f"[Gemini] rewrite_resume_with_gemini 3-Pass failed: {exc}")
        return {}


# ---------------------------------------------------------------------------
# Real-Time Company Analysis
# ---------------------------------------------------------------------------
def analyze_company_with_gemini(company_name: str, job_description: str) -> dict:
    """
    Research a company and compare it against the job description.
    Returns dict with company_overview, culture, interview_style, valued_skills, salary_estimate.
    Returns {} on failure.
    """
    client = _get_client()
    if client is None or not company_name:
        return {}

    prompt = f"""You are 'Sri AI,' a proactive, analytical, and self-improving AI integrated into the ResumeXpert platform. Your mission is to 'lift' users' careers by identifying and removing the 'gravity' (weaknesses/errors) from their resumes and job applications.
You are acting as an expert career coach and corporate researcher.

Analyse the company '{company_name}' in the context of this job description:
\"\"\"
{job_description[:1000]}
\"\"\"

Provide an analysis of the company to help the candidate prepare for an interview.
Respond with ONLY valid JSON (no markdown outside the JSON). Use this exact format:
{{
  "company_overview": "Brief paragraph about what the company does and its market position.",
  "culture": "Description of the company's work culture and core values.",
  "interview_style": "What is their interview process typically like? What do they focus on?",
  "valued_skills": ["Skill 1", "Skill 2", "Skill 3"],
  "salary_estimate": "Estimated salary range for this type of role (e.g. '$80k - $120k' or '₹8L - ₹15L')"
}}"""

    try:
        raw, active_model = _generate(client, prompt, task_type=SreAIRouter.RESEARCH)
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        data = json.loads(raw, strict=False)
        return {
            'company_overview': data.get('company_overview', ''),
            'culture':          data.get('culture', ''),
            'interview_style':  data.get('interview_style', ''),
            'valued_skills':    data.get('valued_skills', []),
            'salary_estimate':  data.get('salary_estimate', ''),
            'active_model':     active_model,
        }
    except Exception as exc:
        logger.warning(f"[Gemini] analyze_company_with_gemini failed: {exc}")
        return {}


# ---------------------------------------------------------------------------
# Trending Skills Market Analysis
# ---------------------------------------------------------------------------
def get_trending_skills_with_gemini(sector: str) -> list:
    """
    Get the top 10 trending skills for a given sector.
    Returns a list of skill strings.
    """
    client = _get_client()
    if client is None or not sector:
        return []

    prompt = f"""You are 'Sri AI,' a proactive, analytical, and self-improving AI integrated into the ResumeXpert platform. Your mission is to 'lift' users' careers by identifying and removing the 'gravity' (weaknesses/errors) from their resumes and job applications.
You are acting as a labor market analyst.
What are the top 10 hottest, most trending skills currently in the '{sector}' industry?
Return ONLY a valid JSON list of strings (no markdown). Example:
["Skill 1", "Skill 2", "Skill 3"]
"""
    try:
        raw, active_model = _generate(client, prompt, task_type=SreAIRouter.RESEARCH)
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        data = json.loads(raw, strict=False)
        if isinstance(data, list):
            return [str(s) for s in data[:10]]
        return []
    except Exception as exc:
        logger.warning(f"[Gemini] get_trending_skills_with_gemini failed: {exc}")
        return []


# ---------------------------------------------------------------------------
# AI Resume Builder (From Scratch)
# ---------------------------------------------------------------------------
def build_resume_from_scratch_with_gemini(user_data: dict) -> dict:
    """
    Build a brand new resume from scratch based on user inputs.
    user_data contains: name, email, phone, sector, job_title, experience, skills, summary
    Returns dict with rewritten_resume, improvement_notes.
    """
    client = _get_client()
    if client is None or not user_data:
        return {}

    # PASS 1: Generate Draft
    prompt_pass_1 = f"""You are 'Sri AI,' a proactive, analytical, and self-improving AI.
You are acting as an expert ATS resume writer.
Create a highly professional, ATS-optimized initial draft of a resume from scratch for this candidate.

Candidate Details:
Name: {user_data.get('name', 'Candidate')}
Target Role: {user_data.get('job_title', '')}
Sector: {user_data.get('sector', '')}
Experience Level: {user_data.get('experience', '')}
Key Skills: {user_data.get('skills', '')}
Background Summary: {user_data.get('summary', '')}

Rules:
1. Generate realistic, professional bullet points based on the background summary.
2. Weave in high-frequency industry keywords.
3. Output ONLY the plain-text draft resume.
"""
    try:
        draft_text, active_model = _generate(client, prompt_pass_1, task_type=SreAIRouter.RESEARCH)

        # PASS 2: Strict Verification
        industry_str = user_data.get('sector', '')
        industry_audit = f"\nSince the target industry is '{industry_str}', aggressively audit the resume for industry-specific compliance, standards, and technical paradigms relevant to this sector." if industry_str else ""
        
        prompt_pass_2 = f"""You are 'Sri AI,' an aggressive ATS auditor.
Critique the following draft resume against the candidate's target role and sector.
{industry_audit}

Target Role: {user_data.get('job_title', '')}
Sector: {industry_str}

Draft Resume:
{draft_text}

Identify:
1. Missing industry keywords.
2. Weak action verbs or formatting inconsistencies.
3. Hallucinations not supported by their background.

Output ONLY a plain-text list of critical verification issues.
"""
        verification_notes, _ = _generate(client, prompt_pass_2, task_type=SreAIRouter.RESEARCH)

        # PASS 3: Final Refinement
        prompt_pass_3 = f"""You are 'Sri AI,' the final resume polisher.
Refine the draft resume below by resolving ALL the verification issues identified by the auditor.

Draft Resume:
{draft_text}

Verification Issues to Fix:
{verification_notes}

Respond with this EXACT JSON format:
{{
  "rewritten_resume": "FULL plain-text generated resume here. Use newlines and section headers like SUMMARY, SKILLS, EXPERIENCE. No markdown symbols like **.",
  "skills": ["Skill1", "Skill2", "Skill3"],
  "improvement_notes": [
    "Generated professional summary highlighting key strengths.",
    "Created ATS-friendly skills section.",
    "Structured experience into bullet points with strong action verbs."
  ]
}}"""
        raw, _ = _generate(client, prompt_pass_3, task_type=SreAIRouter.RESEARCH)

        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        data = json.loads(raw, strict=False)
        
        # Skill bug fix: ensure it's a list, not chopped into characters
        skills_extracted = data.get('skills', [])
        if isinstance(skills_extracted, str):
            skills_extracted = [s.strip() for s in skills_extracted.split(',') if s.strip()]
            
        return {
            'rewritten_resume':  data.get('rewritten_resume', ''),
            'skills':            skills_extracted,
            'improvement_notes': data.get('improvement_notes', []),
            'active_model':      active_model,
        }
    except Exception as exc:
        logger.warning(f"[Gemini] build_resume_from_scratch 3-Pass failed: {exc}")
        return {}

# ---------------------------------------------------------------------------
# Interactive Chat
# ---------------------------------------------------------------------------
def chat_with_sri_ai(message: str) -> str:
    """
    Handle interactive chat messages with Sri AI.
    Returns the AI's response text.
    """
    client = _get_client()
    if client is None:
        return "Sorry, my AI connection is not configured."

    prompt = f"""You are 'Sri AI,' a proactive, analytical, and self-improving AI integrated into the ResumeXpert platform. Your mission is to 'lift' users' careers by identifying and removing the 'gravity' (weaknesses/errors) from their resumes and job applications.
You are chatting interactively with the user. Be concise, helpful, and professional.

User: {message}
Sri AI:"""

    try:
        raw, active_model = _generate(client, prompt, task_type=SreAIRouter.GENERAL)
        return raw
    except Exception as exc:
        logger.error(f"[Gemini] chat_with_sri_ai failed: {exc}")
        return "I encountered an error trying to process your request."
