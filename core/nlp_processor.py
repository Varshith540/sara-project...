"""
ResumeXpert – NLP Processor
Handles skill extraction, TF-IDF cosine similarity, and keyword analysis.
"""

import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ---------------------------------------------------------------------------
# Master skill dictionary – grouped by domain
# ---------------------------------------------------------------------------
SKILLS_DB = {
    # Programming Languages
    "python", "java", "javascript", "typescript", "c", "c++", "c#",
    "ruby", "php", "swift", "kotlin", "go", "rust", "scala", "r",
    "matlab", "perl", "bash", "shell", "powershell",

    # Web Development
    "html", "css", "react", "reactjs", "angular", "vue", "vuejs",
    "nodejs", "node.js", "express", "expressjs", "django", "flask",
    "fastapi", "spring", "spring boot", "laravel", "asp.net",
    "rest api", "restful", "graphql", "websocket", "bootstrap",
    "tailwind", "sass", "less", "jquery", "next.js", "nuxt.js",

    # Data Science / ML / AI
    "machine learning", "deep learning", "artificial intelligence",
    "natural language processing", "nlp", "computer vision",
    "neural network", "tensorflow", "keras", "pytorch", "scikit-learn",
    "sklearn", "pandas", "numpy", "matplotlib", "seaborn", "plotly",
    "opencv", "xgboost", "lightgbm", "bert", "gpt", "transformers",
    "hugging face", "reinforcement learning", "data analysis",
    "data science", "feature engineering", "model deployment",

    # Databases
    "sql", "mysql", "postgresql", "sqlite", "mongodb", "redis",
    "cassandra", "oracle", "firebase", "dynamodb", "elasticsearch",
    "nosql", "database design", "orm",

    # Cloud & DevOps
    "aws", "azure", "google cloud", "gcp", "docker", "kubernetes",
    "jenkins", "ci/cd", "github actions", "terraform", "ansible",
    "linux", "unix", "git", "github", "gitlab", "bitbucket",
    "nginx", "apache", "heroku", "vercel", "netlify",

    # Data Engineering
    "hadoop", "spark", "kafka", "airflow", "etl", "data pipeline",
    "bigquery", "snowflake", "dbt", "tableau", "power bi",
    "excel", "looker", "data warehouse",

    # Mobile
    "android", "ios", "react native", "flutter", "dart",
    "mobile development", "xamarin",

    # Security
    "cybersecurity", "penetration testing", "ethical hacking",
    "network security", "cryptography", "oauth", "jwt",

    # Project / Soft Skills
    "agile", "scrum", "kanban", "jira", "confluence", "trello",
    "project management", "leadership", "communication", "teamwork",
    "problem solving", "critical thinking",

    # Domain specific
    "blockchain", "iot", "embedded systems", "robotics",
    "image processing", "data visualization", "statistics",
    "hypothesis testing", "regression", "classification", "clustering",
}

# Skill aliases (maps alternate names → canonical name)
SKILL_ALIASES = {
    "reactjs": "react",
    "vuejs": "vue",
    "nodejs": "node.js",
    "sklearn": "scikit-learn",
    "ml": "machine learning",
    "dl": "deep learning",
    "ai": "artificial intelligence",
    "cv": "computer vision",
    "js": "javascript",
    "ts": "typescript",
    "k8s": "kubernetes",
    "tf": "tensorflow",
    "py": "python",
    "postgres": "postgresql",
    "mongo": "mongodb",
}


# ---------------------------------------------------------------------------
# Core extraction function
# ---------------------------------------------------------------------------
def extract_skills(text: str) -> list:
    """
    Extract a deduplicated list of skills from free-form text.
    Uses both exact match and alias resolution.
    """
    text_lower = text.lower()
    found = set()

    # Sort by length descending so multi-word skills match before sub-words
    for skill in sorted(SKILLS_DB, key=len, reverse=True):
        pattern = r'\b' + re.escape(skill) + r'\b'
        if re.search(pattern, text_lower):
            # Resolve alias
            canonical = SKILL_ALIASES.get(skill, skill)
            found.add(canonical)

    return sorted(found)


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------
def get_cosine_similarity(resume_text: str, job_description: str) -> float:
    """
    Compute TF-IDF cosine similarity between the resume and job description.
    Returns a percentage (0-100).
    """
    if not resume_text.strip() or not job_description.strip():
        return 0.0
    try:
        vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 2))
        tfidf_matrix = vectorizer.fit_transform([resume_text, job_description])
        score = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        return round(float(score) * 100, 2)
    except Exception as e:
        print(f"[NLPProcessor] Cosine similarity error: {e}")
        return 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def extract_job_skills(job_description: str) -> list:
    """Extract skills mentioned in a job description."""
    return extract_skills(job_description)


def get_missing_skills(resume_skills: list, job_skills: list) -> list:
    """Return skills required by job but absent from resume."""
    return sorted(set(job_skills) - set(resume_skills))


def get_matched_skills(resume_skills: list, job_skills: list) -> list:
    """Return skills common to resume and job description."""
    return sorted(set(resume_skills) & set(job_skills))


def get_skill_categories(skills: list) -> dict:
    """
    Group a flat list of skills into broad categories for display.
    """
    categories = {
        "Programming Languages": {
            "python", "java", "javascript", "typescript", "c", "c++", "c#",
            "ruby", "php", "swift", "kotlin", "go", "rust", "scala", "r",
            "matlab", "bash", "shell",
        },
        "Web Development": {
            "html", "css", "react", "angular", "vue", "node.js", "django",
            "flask", "fastapi", "spring boot", "rest api", "graphql",
            "bootstrap", "tailwind", "jquery", "next.js",
        },
        "Data Science & AI": {
            "machine learning", "deep learning", "artificial intelligence",
            "nlp", "computer vision", "tensorflow", "keras", "pytorch",
            "scikit-learn", "pandas", "numpy", "data analysis", "data science",
            "xgboost", "bert", "transformers",
        },
        "Databases": {
            "sql", "mysql", "postgresql", "sqlite", "mongodb", "redis",
            "oracle", "firebase", "dynamodb", "nosql",
        },
        "Cloud & DevOps": {
            "aws", "azure", "gcp", "docker", "kubernetes", "git",
            "github", "ci/cd", "linux", "terraform", "jenkins",
        },
        "Tools & Others": set(),   # Catch-all
    }

    result = {cat: [] for cat in categories}
    for skill in skills:
        placed = False
        for cat, cat_skills in categories.items():
            if cat == "Tools & Others":
                continue
            if skill in cat_skills:
                result[cat].append(skill)
                placed = True
                break
        if not placed:
            result["Tools & Others"].append(skill)

    # Remove empty categories
    return {k: v for k, v in result.items() if v}
