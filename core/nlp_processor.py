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
    # Programming / Software
    "python", "java", "javascript", "typescript", "C", "c++", "c#",
    "ruby", "php", "swift", "kotlin", "go", "rust", "scala", "R",
    "matlab", "perl", "bash", "shell", "powershell", "html", "css",
    "react", "angular", "vue", "node.js", "django", "flask", "fastapi",
    "spring boot", "laravel", "next.js", "docker", "kubernetes", "aws",
    "azure", "gcp", "linux", "git", "github", "sql", "mysql", "postgresql",
    "mongodb", "redis", "elasticsearch",
    "machine learning", "deep learning", "artificial intelligence", "nlp",
    "computer vision", "tensorflow", "pytorch", "pandas", "numpy",

    # Healthcare / Medical
    "nursing", "patient care", "clinical research", "pharmacology", "emr",
    "cpr", "bls", "acls", "vital signs", "phlebotomy", "medical billing",
    "icd-10", "hipaa", "triage", "infection control", "anatomy", "physiology",
    "healthcare management", "public health", "epidemiology",

    # Law / Legal
    "contract law", "litigation", "legal research", "compliance", "gdpr",
    "corporate law", "intellectual property", "family law", "criminal law",
    "legal drafting", "mediation", "arbitration", "case management", "due diligence",
    "legal advice", "paralegal", "court procedures",

    # Finance / Accounting
    "accounting", "cpa", "financial modelling", "ifrs", "bloomberg",
    "taxation", "auditing", "financial analysis", "budgeting", "forecasting",
    "payroll", "accounts payable", "accounts receivable", "reconciliation",
    "erp", "sap", "quickbooks", "risk management", "investment banking", "valuation",

    # Marketing / Sales
    "seo", "sem", "google analytics", "brand management", "content strategy",
    "digital marketing", "social media marketing", "email marketing", "crm",
    "salesforce", "lead generation", "b2b sales", "b2c sales", "market research",
    "copywriting", "public relations", "event management",

    # Education / Teaching
    "curriculum design", "pedagogy", "lesson planning", "lms", "cbse",
    "icse", "special education", "classroom management", "student evaluation",
    "e-learning", "instructional design", "mentoring", "tutoring", "higher education",

    # Engineering (Non-IT)
    "autocad", "solidworks", "structural analysis", "plc", "hvac",
    "civil engineering", "mechanical engineering", "electrical engineering",
    "manufacturing", "quality control", "six sigma", "cad/cam", "matlab",
    "project estimation", "safety protocols",

    # HR / Admin
    "recruitment", "hrms", "performance management", "pf", "esi",
    "employee relations", "talent acquisition", "onboarding", "payroll processing",
    "labor laws", "conflict resolution", "office administration", "data entry",
    "scheduling", "executive support",

    # Design
    "figma", "adobe xd", "photoshop", "illustrator", "ui/ux",
    "typography", "graphic design", "wireframing", "prototyping", "color theory",
    "interaction design", "inDesign", "video editing", "premiere pro", "after effects",

    # Supply Chain / Operations
    "logistics", "inventory management", "procurement", "vendor management", "supply chain",
    "supply chain management", "warehouse management", "shipping", "freight forwarding",
    "operations management", "quality assurance", "materials management",

    # Hospitality
    "front office", "food & beverage", "revenue management", "pms", "guest services",
    "event planning", "housekeeping management", "hotel management", "catering",
    "customer service", "reservation systems",
    
    # Generic Soft Skills
    "agile", "scrum", "kanban", "jira", "project management", "leadership",
    "communication", "teamwork", "problem solving", "critical thinking",
    "time management", "presentation",
}

# Skill aliases (maps alternate names → canonical name)
SKILL_ALIASES = {
    "reactjs": "react", "vuejs": "vue", "nodejs": "node.js",
    "sklearn": "scikit-learn", "ml": "machine learning", "dl": "deep learning",
    "ai": "artificial intelligence", "cv": "computer vision", "js": "javascript",
    "ts": "typescript", "k8s": "kubernetes", "tf": "tensorflow",
    "py": "python", "postgres": "postgresql", "mongo": "mongodb",
    "hr": "recruitment", "ui": "ui/ux", "ux": "ui/ux", "pr": "public relations",
}

# Sector identification keywords
SECTORS = {
    "IT / Software": ["software", "developer", "programmer", "data scientist", "web development", "devops", "cloud", "backend", "frontend", "full stack", "ai engineer"],
    "Healthcare": ["doctor", "nurse", "hospital", "clinic", "clinical", "patient", "medical", "healthcare", "surgeon", "pharmacist"],
    "Law & Legal": ["lawyer", "attorney", "legal", "court", "law firm", "litigation", "paralegal", "judge", "advocate"],
    "Finance": ["accountant", "finance", "banking", "investment", "audit", "tax", "cpa", "financial analyst", "wealth management"],
    "Marketing": ["marketing", "sales", "seo", "brand", "digital marketing", "advertising", "pr", "public relations"],
    "Education": ["teacher", "professor", "school", "university", "education", "student", "faculty", "tutor", "instructor"],
    "Engineering": ["civil engineer", "mechanical engineer", "electrical engineer", "manufacturing", "construction", "hvac", "autocad"],
    "Human Resources": ["hr", "human resources", "recruiter", "talent acquisition", "payroll", "employee", "onboarding"],
    "Design": ["designer", "ui/ux", "graphic designer", "art director", "creative", "figma", "photoshop"],
    "Supply Chain": ["supply chain", "logistics", "warehouse", "procurement", "inventory", "vendor", "freight"],
    "Hospitality": ["hotel", "restaurant", "hospitality", "chef", "front desk", "guest", "resort", "catering"]
}

def detect_sector(text: str) -> str:
    """Identify the likely sector based on keywords in the text."""
    text_lower = text.lower()
    scores = {sector: 0 for sector in SECTORS}
    
    for sector, keywords in SECTORS.items():
        for keyword in keywords:
            if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower):
                scores[sector] += 1
                
    best_sector = max(scores, key=scores.get)
    if scores[best_sector] == 0:
        return "General / Unspecified"
    return best_sector


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
        if len(skill) == 1:
            # Case-sensitive match for single-letter skills like 'C' or 'R'
            pattern = r'\b' + re.escape(skill.upper()) + r'\b'
            if re.search(pattern, text):
                canonical = SKILL_ALIASES.get(skill, skill)
                found.add(canonical)
        else:
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
        "IT & Technology": {
            "python", "java", "javascript", "typescript", "C", "c++", "c#",
            "ruby", "php", "swift", "kotlin", "go", "rust", "scala", "R",
            "html", "css", "react", "angular", "vue", "node.js", "django",
            "aws", "docker", "kubernetes", "sql", "mysql", "machine learning",
            "artificial intelligence", "nlp", "tensorflow", "git", "linux"
        },
        "Healthcare & Medical": {
            "nursing", "patient care", "clinical research", "pharmacology", "emr",
            "cpr", "bls", "acls", "vital signs", "phlebotomy", "medical billing",
            "hipaa", "triage", "infection control", "healthcare management",
            "anatomy", "physiology", "epidemiology", "public health", "icd-10"
        },
        "Finance & Accounting": {
            "accounting", "cpa", "financial modelling", "ifrs", "bloomberg",
            "taxation", "auditing", "financial analysis", "budgeting", "forecasting",
            "payroll", "erp", "sap", "quickbooks", "risk management", "valuation"
        },
        "Marketing & Sales": {
            "seo", "sem", "google analytics", "brand management", "content strategy",
            "digital marketing", "social media marketing", "email marketing", "crm",
            "salesforce", "lead generation", "b2b sales", "b2c sales", "copywriting"
        },
        "Design & Creative": {
            "figma", "adobe xd", "photoshop", "illustrator", "ui/ux",
            "typography", "graphic design", "wireframing", "prototyping",
            "video editing", "premiere pro", "after effects", "inDesign"
        },
        "Business & HR": {
            "recruitment", "hrms", "performance management", "pf", "esi",
            "talent acquisition", "onboarding", "labor laws", "conflict resolution",
            "office administration", "agile", "scrum", "project management",
            "leadership", "communication"
        },
        "Engineering & Operations": {
            "autocad", "solidworks", "structural analysis", "plc", "hvac",
            "civil engineering", "mechanical engineering", "electrical engineering",
            "quality control", "six sigma", "logistics", "inventory management",
            "procurement", "supply chain"
        },
        "Other Skills": set()
    }

    result = {cat: [] for cat in categories}
    for skill in skills:
        placed = False
        for cat, cat_skills in categories.items():
            if cat == "Other Skills":
                continue
            if skill in cat_skills:
                result[cat].append(skill)
                placed = True
                break
        if not placed:
            result["Other Skills"].append(skill)

    # Remove empty categories
    return {k: v for k, v in result.items() if v}
