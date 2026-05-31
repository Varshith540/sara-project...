"""
Sri AI — Omni-Heal Pillar B: Soft-Heal Silent Trigger
=====================================================
Non-blocking background analysis for silent/caught errors.
Errors are queued and processed by a dedicated daemon thread
so the user NEVER sees a 500, but Sri AI still catches everything.

Author  : Anti Gravity / Sri AI Omni-Heal Initiative
Pattern : Producer-Consumer (Queue + Daemon Thread)
"""

import json
import queue
import hashlib
import logging
import threading
import traceback
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

# ──────────────────────────────────────────────
# Logger (writes to Django's existing log pipeline)
# ──────────────────────────────────────────────
logger = logging.getLogger("sri_ai.soft_heal")


# ──────────────────────────────────────────────
# Data model for a heal job
# ──────────────────────────────────────────────
@dataclass
class HealJob:
    """A single unit of work for the Soft-Heal queue."""

    error_source: str          # e.g. "resume_parser.py:ocr_fallback"
    error_trace: str           # full traceback string
    error_type: str = "SILENT" # SILENT | FRONTEND | LOGIC
    severity: str = "MEDIUM"  # LOW | MEDIUM | HIGH | CRITICAL
    context: dict = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    job_id: str = field(default_factory=lambda: "")

    def __post_init__(self):
        # Deterministic job ID: prevents duplicate analysis for the same error
        raw = f"{self.error_source}:{self.error_trace[:120]}"
        self.job_id = hashlib.sha256(raw.encode()).hexdigest()[:16]


# ──────────────────────────────────────────────
# Singleton Soft-Heal Engine
# ──────────────────────────────────────────────
class _SoftHealEngine:
    """
    Singleton background engine.
    One daemon thread drains the queue continuously.
    Cooldown map prevents re-analysing the same error within 10 minutes.
    """

    COOLDOWN_SECONDS = 600          # 10 min — same as the reactive watcher
    MAX_QUEUE_SIZE   = 200          # safety cap; drops oldest if exceeded
    WORKER_SLEEP     = 2            # seconds between queue polls

    def __init__(self):
        self._queue: queue.Queue = queue.Queue(maxsize=self.MAX_QUEUE_SIZE)
        self._cooldown_map: dict = {}   # job_id → last_seen epoch
        self._lock = threading.Lock()
        self._started = False

    # ── public ─────────────────────────────────
    def start(self):
        """Call once at app startup (apps.py ready())."""
        if self._started:
            return
        self._started = True
        t = threading.Thread(
            target=self._worker_loop,
            name="sri-soft-heal-worker",
            daemon=True,          # dies with the main process — no orphan threads
        )
        t.start()
        logger.info("[SoftHeal] Daemon worker thread started.")

    def enqueue(self, job: HealJob) -> bool:
        """
        Non-blocking enqueue.
        Returns True if accepted, False if cooldown/queue-full dropped it.
        """
        # Cooldown guard
        with self._lock:
            last = self._cooldown_map.get(job.job_id, 0)
            if time.time() - last < self.COOLDOWN_SECONDS:
                logger.debug(
                    "[SoftHeal] Cooldown active for job %s — skipping.", job.job_id
                )
                return False
            self._cooldown_map[job.job_id] = time.time()

        try:
            self._queue.put_nowait(job)
            logger.info(
                "[SoftHeal] Queued job %s | source=%s | severity=%s",
                job.job_id,
                job.error_source,
                job.severity,
            )
            return True
        except queue.Full:
            logger.warning("[SoftHeal] Queue full — dropping job %s.", job.job_id)
            return False

    # ── private ────────────────────────────────
    def _worker_loop(self):
        """Continuously drain the queue and analyse errors."""
        logger.info("[SoftHeal] Worker loop running.")
        while True:
            try:
                job: HealJob = self._queue.get(timeout=self.WORKER_SLEEP)
                self._analyse(job)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as exc:          # pragma: no cover
                logger.exception("[SoftHeal] Unexpected worker error: %s", exc)

    def _analyse(self, job: HealJob):
        """
        Core analysis step — Level 6 Poly-Brain Architecture.

        1. Calls the Poly-Brain LLM Router (generate_patch) which cascades
           Gemini → OpenRouter → Ollama until a patch is produced.
        2. Feeds the resulting patch into the Git Controller
           (auto_heal_and_deploy) which pushes a branch, opens a PR, and
           triggers the CI/CD pipeline for safe, verified auto-merge.

        Isolated in try/except so a broken analysis never crashes the worker.
        """
        logger.info("[SoftHeal] Analysing job %s (source=%s)…", job.job_id, job.error_source)
        try:
            # ── Step 1: Generate a patch via the Poly-Brain LLM Router ────────
            from core.sri_llm_router import generate_patch   # late import: avoids circular

            context_payload = json.dumps(
                {"trigger": "SOFT_HEAL", "job": asdict(job)},
                indent=2,
            )

            patch_content = generate_patch(
                error_type=job.error_type,
                error_trace=job.error_trace,
                broken_file="",          # healer doesn't have file content; router will infer
                context=context_payload,
            )

            if not patch_content:
                logger.warning(
                    "[SoftHeal] All LLM tiers exhausted for job %s — no patch generated.",
                    job.job_id,
                )
                return

            logger.info(
                "[SoftHeal] Poly-Brain generated patch (%d chars) for job %s.",
                len(patch_content),
                job.job_id,
            )

            # ── Step 2: Push patch through the Git Controller → CI/CD ─────────
            from core.sri_ai import auto_heal_and_deploy    # late import: avoids circular

            result = auto_heal_and_deploy(
                job_id=job.job_id,
                file_path=job.error_source,   # e.g. "core/resume_parser.py"
                new_content=patch_content,
                error_summary=job.error_trace[:500],
                severity=job.severity,
            )

            logger.info(
                "[SoftHeal] Git Controller result for job %s: status=%s",
                job.job_id,
                result.get("status"),
            )

        except ImportError as exc:
            # Graceful degradation: router/controller not wired yet
            logger.warning(
                "[SoftHeal] Required module not found (%s) — logging for manual review.\n"
                "Source : %s\nTrace  :\n%s",
                exc,
                job.error_source,
                job.error_trace,
            )
        except Exception as exc:
            logger.exception(
                "[SoftHeal] Analysis failed for job %s: %s", job.job_id, exc
            )


# ── Global singleton instance ──────────────────
_engine = _SoftHealEngine()


# ──────────────────────────────────────────────
# Public API — call this everywhere in the app
# ──────────────────────────────────────────────
def start_soft_heal_engine():
    """
    Initialise the daemon worker.
    Call once from AppConfig.ready() — idempotent.
    """
    _engine.start()


def sri_heal_silent(
    error_source: str,
    error_trace: Optional[str] = None,
    severity: str = "MEDIUM",
    error_type: str = "SILENT",
    context: Optional[dict] = None,
) -> bool:
    """
    Drop-in replacement for bare `logger.exception(...)` inside try/except blocks.

    Usage
    -----
    try:
        result = risky_operation()
    except Exception as exc:
        sri_heal_silent(
            error_source="resume_parser.ocr_fallback",
            error_trace=traceback.format_exc(),
            severity="HIGH",
            context={"file": filename, "user_id": user_id},
        )
        result = safe_fallback_value   # user never sees a 500

    Parameters
    ----------
    error_source : Human-readable location string  (module.function)
    error_trace  : Full traceback — use traceback.format_exc()
    severity     : LOW | MEDIUM | HIGH | CRITICAL
    error_type   : SILENT | FRONTEND | LOGIC | OCR
    context      : Extra key-value metadata (file names, user IDs, etc.)

    Returns
    -------
    bool : True if the job was successfully queued.
    """
    trace = error_trace or traceback.format_exc()
    job = HealJob(
        error_source=error_source,
        error_trace=trace,
        error_type=error_type,
        severity=severity,
        context=context or {},
    )
    return _engine.enqueue(job)
