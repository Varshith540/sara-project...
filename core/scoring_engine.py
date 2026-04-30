"""
ResumeXpert – Scoring Engine
Hybrid ATS score: Skill Match (50%) + Cosine Similarity (30%) + Completeness (20%)
"""

from .nlp_processor import (
    extract_skills,
    extract_job_skills,
    get_cosine_similarity,
    get_missing_skills,
    get_matched_skills,
)


# ---------------------------------------------------------------------------
# Section completeness check
# ---------------------------------------------------------------------------
IMPORTANT_SECTIONS = {
    'education':    ('education', 'university', 'degree', 'bachelor', 'master', 'b.tech', 'b.e', 'm.tech'),
    'experience':   ('experience', 'worked', 'internship', 'company', 'organization', 'employer'),
    'skills':       ('skill', 'proficient', 'familiar', 'knowledge', 'expertise', 'tools'),
    'projects':     ('project', 'built', 'developed', 'created', 'implemented', 'designed'),
    'contact':      ('@', 'email', 'phone', 'linkedin', 'github', 'contact'),
}

SECTION_WEIGHTS = {
    'education':  4,
    'experience': 5,
    'skills':     4,
    'projects':   4,
    'contact':    3,
}


def _completeness_score(text: str) -> tuple[float, list]:
    """
    Check which sections are present and return a 0-20 completeness score
    along with a list of missing-section suggestions.
    """
    text_lower = text.lower()
    total_weight = sum(SECTION_WEIGHTS.values())
    earned = 0
    missing_suggestions = []

    for section, keywords in IMPORTANT_SECTIONS.items():
        found = any(kw in text_lower for kw in keywords)
        if found:
            earned += SECTION_WEIGHTS[section]
        else:
            missing_suggestions.append(_section_suggestion(section))

    # Scale to 0-20
    score = (earned / total_weight) * 20
    return round(score, 2), missing_suggestions


def _section_suggestion(section: str) -> str:
    messages = {
        'education':  "Add an Education section with your degree, university, and year.",
        'experience': "Include work experience or internship details.",
        'skills':     "Add a dedicated Skills section with your technical competencies.",
        'projects':   "Showcase your Projects — they greatly boost your ATS score.",
        'contact':    "Include contact info: email, phone, LinkedIn, and GitHub.",
    }
    return messages.get(section, f"Add a {section.title()} section.")


# ---------------------------------------------------------------------------
# Keyword density bonus
# ---------------------------------------------------------------------------
def _keyword_density_bonus(resume_text: str, job_description: str) -> float:
    """
    Small bonus (up to 5 points) for having a high density of
    job-description keywords in the resume.
    """
    if not job_description.strip():
        return 0.0
    jd_words = set(job_description.lower().split())
    resume_words = resume_text.lower().split()
    if not resume_words:
        return 0.0
    hits = sum(1 for w in resume_words if w in jd_words)
    density = hits / len(resume_words)
    # Cap bonus at 5 points when density >= 0.15
    bonus = min(density / 0.15 * 5, 5)
    return round(bonus, 2)


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------
def calculate_score(resume_text: str, job_description: str) -> dict:
    """
    Compute the full ATS analysis and return a result dict.

    Scoring breakdown
    -----------------
    • Skill Match Score  → 50% weight
    • Cosine Similarity  → 30% weight
    • Completeness       → up to 20 points
    • Keyword bonus      → up to 5 bonus points (can push score past 100, capped)
    """

    # --- Skill extraction ---------------------------------------------------
    resume_skills = extract_skills(resume_text)
    job_skills    = extract_job_skills(job_description)
    matched       = get_matched_skills(resume_skills, job_skills)
    missing       = get_missing_skills(resume_skills, job_skills)

    # --- Skill match score (0-100 raw, weighted 50%) ------------------------
    if job_skills:
        skill_raw   = (len(matched) / len(job_skills)) * 100
    else:
        skill_raw   = 50.0          # neutral when no JD skills detected
    skill_component = skill_raw * 0.50

    # --- Cosine similarity (0-100 raw, weighted 30%) ------------------------
    cosine_raw       = get_cosine_similarity(resume_text, job_description)
    cosine_component = cosine_raw * 0.30

    # --- Completeness (0-20) ------------------------------------------------
    completeness_score, completeness_suggestions = _completeness_score(resume_text)

    # --- Keyword density bonus (0-5) ----------------------------------------
    bonus = _keyword_density_bonus(resume_text, job_description)

    # --- Total ATS score ----------------------------------------------------
    total = skill_component + cosine_component + completeness_score + bonus
    total = round(min(total, 100), 2)

    # --- Build improvement suggestions --------------------------------------
    suggestions = _build_suggestions(
        missing_skills        = missing,
        resume_text           = resume_text,
        skill_match_raw       = skill_raw,
        cosine_raw            = cosine_raw,
        completeness_sug      = completeness_suggestions,
        job_skills_count      = len(job_skills),
    )

    return {
        'ats_score':         total,
        'skill_match_score': round(skill_raw, 2),
        'cosine_score':      round(cosine_raw, 2),
        'matched_skills':    matched,
        'missing_skills':    missing,
        'resume_skills':     resume_skills,
        'suggestions':       suggestions,
    }


# ---------------------------------------------------------------------------
# Suggestion builder
# ---------------------------------------------------------------------------
def _build_suggestions(
    missing_skills:   list,
    resume_text:      str,
    skill_match_raw:  float,
    cosine_raw:       float,
    completeness_sug: list,
    job_skills_count: int = 1,
) -> list:
    suggestions = []
    text_lower = resume_text.lower()

    # 1. Missing skills
    if job_skills_count == 0:
        suggestions.append(
            "⚠️ We couldn't detect any technical skills in the job description. "
            "Ensure you provided a complete description to get accurate skill matching."
        )
    elif missing_skills:
        top_missing = ", ".join(missing_skills[:6])
        suggestions.append(
            f"🔧 Add these in-demand skills to your resume: {top_missing}."
        )

    # 2. Low skill match
    if job_skills_count > 0 and skill_match_raw < 40:
        suggestions.append(
            "📌 Tailor your resume specifically to the job description — "
            "mirror the exact skill names the employer uses."
        )

    # 3. Low cosine similarity
    if cosine_raw < 30:
        suggestions.append(
            "📝 Rephrase your experience bullet points using language "
            "from the job description to improve relevance."
        )

    # 4. Section completeness
    suggestions.extend(completeness_sug)

    # 5. Resume length
    word_count = len(resume_text.split())
    if word_count < 150:
        suggestions.append(
            "📄 Your resume seems too brief. Aim for at least 400-600 words "
            "to give enough context to ATS systems."
        )
    elif word_count > 1200:
        suggestions.append(
            "✂️ Your resume may be too long. Keep it concise — 1 page for "
            "freshers, 2 pages for experienced professionals."
        )

    # 6. Quantified achievements
    has_numbers = any(char.isdigit() for char in resume_text)
    if not has_numbers:
        suggestions.append(
            "📊 Add quantified achievements (e.g. 'Improved performance by 30%', "
            "'Handled 10,000+ records') to stand out."
        )

    # 7. Action verbs
    action_verbs = ['developed', 'built', 'designed', 'implemented', 'led',
                    'managed', 'created', 'optimized', 'delivered', 'achieved']
    if not any(v in text_lower for v in action_verbs):
        suggestions.append(
            "💬 Start bullet points with strong action verbs like Developed, "
            "Built, Led, Optimized, or Implemented."
        )

    # 8. GitHub / Portfolio
    if 'github' not in text_lower and 'portfolio' not in text_lower:
        suggestions.append(
            "🔗 Add your GitHub profile or portfolio link — recruiters love "
            "seeing your actual work."
        )

    # 9. Certifications
    if 'certif' not in text_lower:
        suggestions.append(
            "🏅 Consider adding relevant certifications "
            "(e.g. AWS, Google, Coursera, Udemy) to boost credibility."
        )

    return suggestions
