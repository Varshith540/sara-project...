"""
ResumeXpert – Gemini AI Service
Uses the new google-genai SDK (google.genai).
Falls back gracefully when the API key is missing or any call fails.
"""

import json
import re
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

MODEL_NAME  = 'models/gemini-2.0-flash-lite'   # primary — best free-tier limits
FALLBACKS  = ['models/gemini-flash-latest', 'models/gemini-2.0-flash']

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


def _generate(client, prompt: str) -> str:
    """Try MODEL_NAME then each FALLBACK on 429/404; raise on other errors."""
    for model in [MODEL_NAME] + FALLBACKS:
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            return response.text.strip()
        except Exception as exc:
            msg = str(exc)
            if '429' in msg or '404' in msg:
                logger.warning(f"[Gemini] {model} unavailable ({msg[:80]}), trying next…")
                continue
            raise
    raise RuntimeError("All Gemini models exhausted / rate-limited.")


def is_gemini_available() -> bool:
    """Return True if Gemini is configured."""
    return _get_client() is not None


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

    prompt = f"""You are an expert ATS resume coach and HR consultant.

Analyse the following resume against the job description and respond with ONLY valid JSON (no markdown, no extra text outside the JSON).

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
  "job_fit_score": <integer 0-100 representing overall fit>,
  "ai_suggestions": [
    "Specific actionable suggestion 1",
    "Specific actionable suggestion 2",
    "Specific actionable suggestion 3",
    "Specific actionable suggestion 4",
    "Specific actionable suggestion 5"
  ]
}}"""

    try:
        raw = _generate(client, prompt)

        # Strip markdown code fences if present
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        data = json.loads(raw)
        return {
            'ai_summary':     data.get('ai_summary', ''),
            'ai_suggestions': data.get('ai_suggestions', []),
            'job_fit_score':  int(data.get('job_fit_score', 0)),
        }
    except Exception as exc:
        logger.warning(f"[Gemini] analyze_resume_with_gemini failed: {exc}")
        return {}


# ---------------------------------------------------------------------------
# Dynamic Exam Question Generation
# ---------------------------------------------------------------------------
def generate_exam_questions_with_gemini(skills: list, num_questions: int = 5) -> list:
    """
    Generate fresh MCQ questions for the given skills using Gemini.
    Returns list of question dicts matching exam_generator.py format.
    Returns [] on failure.
    """
    client = _get_client()
    if client is None or not skills:
        return []

    skills_str = ', '.join(skills[:6])

    prompt = f"""You are a technical interviewer creating a skill assessment quiz.

Generate exactly {num_questions} multiple-choice questions for these skills: {skills_str}

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
        raw = _generate(client, prompt)

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
) -> dict:
    """
    Rewrite the candidate's resume using Gemini AI to better match the JD.
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

    prompt = f"""You are an expert resume writer and ATS specialist.

Rewrite the candidate's resume below to maximise its ATS score for the given job description.

RULES:
1. Keep all factual information accurate — do NOT invent fake jobs, degrees, or companies.
2. Rewrite bullet points using strong action verbs and measurable outcomes where possible.
3. Naturally incorporate missing skills ({missing_str}) ONLY if they are genuinely implied by the candidate's experience.
4. Add or strengthen these sections if missing: Summary, Skills, Experience, Education, Projects.
5. Mirror key phrases and keywords from the job description.
6. Keep it to 1–2 pages worth of content.
7. Return ONLY valid JSON — no markdown outside the JSON.

Original Resume:
\"\"\"
{resume_text[:4000]}
\"\"\"

Job Description:
\"\"\"
{job_description[:1500]}
\"\"\"

Improvement suggestions to apply:
{suggestions_str}

Respond with this EXACT JSON format:
{{
  "rewritten_resume": "FULL plain-text rewritten resume here. Use newlines and section headers like SUMMARY, SKILLS, EXPERIENCE, EDUCATION, PROJECTS. No markdown symbols like ** or ##.",
  "improvement_notes": [
    "Key change made 1",
    "Key change made 2",
    "Key change made 3",
    "Key change made 4",
    "Key change made 5"
  ]
}}"""

    try:
        raw = _generate(client, prompt)

        # Strip markdown code fences if present
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        data = json.loads(raw)
        return {
            'rewritten_resume':  data.get('rewritten_resume', ''),
            'improvement_notes': data.get('improvement_notes', []),
        }
    except Exception as exc:
        logger.warning(f"[Gemini] rewrite_resume_with_gemini failed: {exc}")
        return {}
